"""Command-line interface for generating repository context dumps."""

from __future__ import annotations

import argparse
import contextlib
import errno
import os
import re
import sys
from collections.abc import Sequence
from pathlib import Path
from typing import TextIO

from git_context_dump import __version__, gitutil
from git_context_dump.clipboard import ClipboardError, copy_to_clipboard
from git_context_dump.dumper import DEFAULT_MAX_FILE_SIZE, DumpOptions, build_dump
from git_context_dump.render import FORMAT_EXTENSIONS, FORMATS
from git_context_dump.tokens import TOKENIZERS

_SIZE = re.compile(r"^\s*(\d+)\s*([kmg]?)b?\s*$", re.IGNORECASE)
_SIZE_UNITS = {"": 1, "k": 1024, "m": 1024**2, "g": 1024**3}
# Windows reports a closed pipe as EINVAL rather than EPIPE.
_PIPE_ERRNOS = {errno.EPIPE, errno.EINVAL}


def parse_size(value: str) -> int:
    """Parse sizes such as ``500``, ``256k`` or ``1MB`` into bytes."""
    match = _SIZE.match(value)
    if match is None:
        raise argparse.ArgumentTypeError(f"invalid size: {value!r} (examples: 500, 256k, 1m)")
    return int(match.group(1)) * _SIZE_UNITS[match.group(2).lower()]


def _build_argument_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="git-context-dump",
        description="Create a Markdown, XML or JSON snapshot of a Git working directory.",
    )
    parser.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    parser.add_argument(
        "-d",
        "--dir",
        type=Path,
        default=None,
        help="target directory (default: current working directory)",
    )
    parser.add_argument(
        "-o",
        "--out",
        default=None,
        help="output path, or '-' for standard output (default: context.md / .xml / .json)",
    )
    parser.add_argument(
        "-f",
        "--format",
        choices=FORMATS,
        default="markdown",
        help="output format (default: markdown)",
    )
    parser.add_argument(
        "--tree-only",
        action="store_true",
        help="include the directory tree without file contents",
    )

    selection = parser.add_argument_group("file selection")
    selection.add_argument(
        "--include",
        action="append",
        default=[],
        metavar="GLOB",
        help="only include files matching this gitignore-style glob (repeatable)",
    )
    selection.add_argument(
        "--exclude",
        action="append",
        default=[],
        metavar="GLOB",
        help="exclude paths matching this gitignore-style glob (repeatable)",
    )
    selection.add_argument(
        "--max-file-size",
        type=parse_size,
        default=DEFAULT_MAX_FILE_SIZE,
        metavar="SIZE",
        help="skip files larger than SIZE, e.g. 256k or 1m; 0 disables (default: 256k)",
    )
    selection.add_argument(
        "--no-git",
        action="store_true",
        help="walk the file system instead of asking git for the file list",
    )
    changes = selection.add_mutually_exclusive_group()
    changes.add_argument(
        "--diff",
        action="store_const",
        const=gitutil.CHANGES_DIFF,
        dest="changes",
        help="only files changed in the working tree (vs HEAD), plus untracked files",
    )
    changes.add_argument(
        "--staged",
        action="store_const",
        const=gitutil.CHANGES_STAGED,
        dest="changes",
        help="only files staged for the next commit",
    )
    changes.add_argument(
        "--since",
        metavar="REF",
        default=None,
        help="only files changed since the given commit, branch or tag",
    )

    budget = parser.add_argument_group("token budget")
    budget.add_argument(
        "--max-tokens",
        type=int,
        default=32_000,
        help="warn when the estimated token count exceeds this value (default: 32000)",
    )
    budget.add_argument(
        "--fit-budget",
        action="store_true",
        help="drop the largest files until the dump fits within --max-tokens",
    )
    budget.add_argument(
        "--tokenizer",
        choices=TOKENIZERS,
        default="heuristic",
        help="token counter; 'tiktoken' needs the optional extra (default: heuristic)",
    )

    output = parser.add_argument_group("output")
    output.add_argument("--copy", action="store_true", help="also copy the dump to the clipboard")
    output.add_argument(
        "-v",
        "--verbose",
        action="store_true",
        help="list every skipped file on standard error",
    )
    return parser


def _write_stdout(text: str) -> None:
    """Write UTF-8 regardless of the console code page (e.g. cp1252 on Windows).

    A reader that stops early (``| head``) is not an error: the rest of the
    output is discarded quietly instead of raising ``BrokenPipeError``.
    """
    buffer = getattr(sys.stdout, "buffer", None)
    try:
        if buffer is not None:
            sys.stdout.flush()
            buffer.write(text.encode("utf-8"))
            buffer.flush()
        else:
            sys.stdout.write(text)
    except OSError as error:
        if not isinstance(error, BrokenPipeError) and error.errno not in _PIPE_ERRNOS:
            raise
        with contextlib.suppress(OSError, ValueError, AttributeError):
            devnull = os.open(os.devnull, os.O_WRONLY)
            os.dup2(devnull, sys.stdout.fileno())


def _harden_stream(stream: TextIO) -> None:
    reconfigure = getattr(stream, "reconfigure", None)
    if reconfigure is not None:
        with contextlib.suppress(ValueError, OSError):
            reconfigure(errors="backslashreplace")


def _error(message: str) -> int:
    print(f"Error: {message}", file=sys.stderr)
    return 1


def main(argv: Sequence[str] | None = None) -> int:
    """Run the command-line application and return its process exit code."""
    _harden_stream(sys.stderr)
    args = _build_argument_parser().parse_args(argv)
    target_dir: Path = args.dir if args.dir is not None else Path.cwd()
    if not target_dir.is_dir():
        return _error(f"target directory does not exist: {target_dir}")
    if args.max_tokens < 0:
        return _error("--max-tokens must be zero or greater")

    changes = args.changes
    if args.since is not None:
        changes = gitutil.CHANGES_SINCE
    if changes and args.no_git:
        return _error("--diff, --staged and --since cannot be combined with --no-git")

    out = args.out if args.out is not None else f"context.{FORMAT_EXTENSIONS[args.format]}"
    output_path = None if out == "-" else Path(out)

    options = DumpOptions(
        root=target_dir,
        tree_only=args.tree_only,
        output_format=args.format,
        max_file_size=args.max_file_size or None,
        max_tokens=args.max_tokens,
        fit_budget=args.fit_budget,
        git_mode="off" if args.no_git else "auto",
        changes=changes,
        since_ref=args.since,
        include=args.include,
        exclude=args.exclude,
        output_path=output_path,
        tokenizer=args.tokenizer,
    )

    try:
        result = build_dump(options)
        dump = result.text if result.text.endswith("\n") else result.text + "\n"
        if output_path is None:
            _write_stdout(dump)
        else:
            output_path.parent.mkdir(parents=True, exist_ok=True)
            with output_path.open("w", encoding="utf-8", newline="\n") as handle:
                handle.write(dump)
        if args.copy:
            copy_to_clipboard(dump)
    except ClipboardError as error:
        return _error(f"unable to copy to the clipboard: {error}")
    except (OSError, UnicodeError, ValueError) as error:
        return _error(f"unable to generate context dump: {error}")

    for finding in result.secret_findings:
        print(f"Warning: {finding} (review before sharing)", file=sys.stderr)
    if result.skipped:
        if args.verbose:
            for path, reason in result.skipped:
                print(f"Skipped: {path} ({reason})", file=sys.stderr)
        else:
            print(
                f"Note: {len(result.skipped)} file(s) skipped; use --verbose to list them.",
                file=sys.stderr,
            )
    if result.tokens > args.max_tokens:
        print(
            f"Warning: dump is approximately {result.tokens} tokens, exceeding "
            f"the {args.max_tokens}-token threshold.",
            file=sys.stderr,
        )
    if args.verbose:
        source = "git" if result.used_git else "file system walk"
        print(
            f"Included {len(result.files)} file(s) via {source}; "
            f"~{result.tokens} tokens, {result.characters} characters.",
            file=sys.stderr,
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
