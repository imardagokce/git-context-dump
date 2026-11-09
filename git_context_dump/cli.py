"""Command-line interface for generating repository context dumps."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from git_context_dump.dumper import estimate_tokens, generate_dump
from git_context_dump.ignore import IgnoreFilter


def _build_argument_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="git-context-dump",
        description="Create a Markdown snapshot of a Git working directory.",
    )
    parser.add_argument(
        "-d",
        "--dir",
        type=Path,
        default=Path.cwd(),
        help="target directory (default: current working directory)",
    )
    parser.add_argument(
        "-o",
        "--out",
        default="context.md",
        help="output Markdown path, or '-' to write to standard output",
    )
    parser.add_argument(
        "--tree-only",
        action="store_true",
        help="include the directory tree without file contents",
    )
    parser.add_argument(
        "--max-tokens",
        type=int,
        default=32_000,
        help="warn when the estimated token count exceeds this value (default: 32000)",
    )
    return parser


def main() -> int:
    """Run the command-line application and return its process exit code."""
    args = _build_argument_parser().parse_args()
    target_dir: Path = args.dir
    if not target_dir.is_dir():
        print(f"Error: target directory does not exist: {target_dir}", file=sys.stderr)
        return 1
    if args.max_tokens < 0:
        print("Error: --max-tokens must be zero or greater", file=sys.stderr)
        return 1

    try:
        ignore_filter = IgnoreFilter(target_dir)
        dump = generate_dump(target_dir, ignore_filter, tree_only=args.tree_only)
        token_count = estimate_tokens(dump)
        if token_count > args.max_tokens:
            print(
                f"Warning: dump is approximately {token_count} tokens, exceeding "
                f"the {args.max_tokens}-token threshold.",
                file=sys.stderr,
            )
        if args.out == "-":
            sys.stdout.write(dump)
            if not dump.endswith("\n"):
                sys.stdout.write("\n")
        else:
            output_path = Path(args.out)
            output_path.write_text(dump + "\n", encoding="utf-8")
    except (OSError, UnicodeError, ValueError) as error:
        print(f"Error: unable to generate context dump: {error}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
