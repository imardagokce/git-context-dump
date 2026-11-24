"""Collect a repository's files and render them as a context dump."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path

from git_context_dump import gitutil
from git_context_dump.ignore import IgnoreFilter, is_link
from git_context_dump.render import (
    FORMATS,
    RENDERERS,
    DumpDocument,
    FileEntry,
    clean_whitespace,
    get_language_tag,
)
from git_context_dump.secret_scan import SecretFinding, scan_text
from git_context_dump.tokens import TokenCounter, estimate_tokens, get_token_counter
from git_context_dump.walker import (
    SKIP_BUDGET,
    SKIP_OUTSIDE_ROOT,
    read_text_file,
    render_tree,
    walk,
)

__all__ = [
    "DumpOptions",
    "DumpResult",
    "build_dump",
    "estimate_tokens",
    "generate_dump",
    "get_language_tag",
]

DEFAULT_MAX_FILE_SIZE = 256 * 1024
GIT_MODES = ("auto", "on", "off")


@dataclass
class DumpOptions:
    """Settings for one dump; the CLI maps its flags onto these fields."""

    root: Path
    tree_only: bool = False
    output_format: str = "markdown"
    max_file_size: int | None = DEFAULT_MAX_FILE_SIZE
    max_tokens: int | None = None
    fit_budget: bool = False
    git_mode: str = "auto"
    changes: str | None = None
    since_ref: str | None = None
    include: Sequence[str] = ()
    exclude: Sequence[str] = ()
    output_path: Path | None = None
    tokenizer: str = "heuristic"
    top_files: int = 10
    scan_secrets: bool = True


@dataclass
class DumpResult:
    """The rendered dump plus what was included, skipped and flagged."""

    text: str
    characters: int
    tokens: int
    files: list[FileEntry]
    skipped: list[tuple[str, str]]
    secret_findings: list[SecretFinding] = field(default_factory=list)
    used_git: bool = False
    repo: gitutil.RepoInfo | None = None


def _render(document: DumpDocument, output_format: str, counter: TokenCounter) -> tuple[str, int]:
    """Render until the character and token counts in the summary describe the text itself."""
    renderer = RENDERERS[output_format]
    characters = tokens = 0
    text = renderer(document, characters, tokens)
    for _ in range(8):
        new_characters, new_tokens = len(text), counter(text)
        if (new_characters, new_tokens) == (characters, tokens):
            break
        characters, tokens = new_characters, new_tokens
        text = renderer(document, characters, tokens)
    return text, counter(text)


def _scope_label(options: DumpOptions) -> str | None:
    if options.changes == gitutil.CHANGES_DIFF:
        return "uncommitted changes (working tree vs HEAD, plus untracked files)"
    if options.changes == gitutil.CHANGES_STAGED:
        return "staged changes (file contents read from the working tree)"
    if options.changes == gitutil.CHANGES_SINCE:
        return f"changes since {options.since_ref}"
    return None


def _select_paths(
    root: Path, options: DumpOptions, ignore_filter: IgnoreFilter, use_git: bool
) -> tuple[list[str], list[tuple[str, str]]]:
    if not use_git:
        walked = walk(root, ignore_filter)
        return walked.files, walked.skipped
    if options.changes:
        candidates = gitutil.changed_files(root, options.changes, options.since_ref)
    else:
        candidates = gitutil.list_files(root)
    paths: list[str] = []
    skipped: list[tuple[str, str]] = []
    for relative in candidates:
        absolute = root / relative
        if ignore_filter.is_ignored(absolute) or not ignore_filter.wants_file(relative):
            if is_link(absolute) and ignore_filter.escapes_root(absolute):
                skipped.append((relative, SKIP_OUTSIDE_ROOT))
            continue
        paths.append(relative)
    return paths, skipped


def _apply_budget(document: DumpDocument, options: DumpOptions, counter: TokenCounter) -> None:
    """Drop the largest files until the rendered dump fits ``max_tokens``."""
    if not options.fit_budget or options.max_tokens is None:
        return
    budget = options.max_tokens
    while document.files:
        _, tokens = _render(document, options.output_format, counter)
        if tokens <= budget:
            return
        overshoot = tokens - budget
        ranked = sorted(document.files, key=lambda entry: (-entry.tokens, entry.path))
        # Drop the smallest set of the largest files that covers the overshoot.
        removed = 0
        to_drop: set[str] = set()
        for entry in ranked:
            to_drop.add(entry.path)
            removed += entry.tokens
            if removed >= overshoot:
                break
        document.files = [entry for entry in document.files if entry.path not in to_drop]
        document.skipped += [(path, SKIP_BUDGET) for path in sorted(to_drop)]


def build_dump(options: DumpOptions, ignore_filter: IgnoreFilter | None = None) -> DumpResult:
    """Collect files according to *options* and render the dump."""
    if options.output_format not in FORMATS:
        raise ValueError(f"unknown format: {options.output_format}")
    if options.git_mode not in GIT_MODES:
        raise ValueError(f"unknown git mode: {options.git_mode}")
    root = options.root.resolve()
    if not root.is_dir():
        raise ValueError(f"target directory does not exist: {options.root}")
    counter = get_token_counter(options.tokenizer)

    in_repo = options.git_mode != "off" and gitutil.is_work_tree(root)
    if options.git_mode == "on" and not in_repo:
        raise gitutil.GitError(f"not a Git working tree: {root}")
    if options.changes and not in_repo:
        raise gitutil.GitError(f"--{options.changes} needs a Git working tree: {root}")
    use_git = in_repo

    if ignore_filter is None:
        ignore_filter = IgnoreFilter(
            root,
            use_gitignore=not use_git,
            extra_excludes=options.exclude,
            includes=options.include,
        )
    if options.output_path is not None:
        ignore_filter.force_ignore(options.output_path)

    paths, skipped = _select_paths(root, options, ignore_filter, use_git)

    files: list[FileEntry] = []
    findings: list[SecretFinding] = []
    if not options.tree_only:
        for relative in paths:
            read = read_text_file(root / relative, options.max_file_size)
            if read.content is None:
                skipped.append((relative, read.reason or "unreadable"))
                continue
            content = clean_whitespace(read.content)
            if options.scan_secrets:
                findings += scan_text(relative, content)
            files.append(FileEntry(relative, get_language_tag(relative), content, counter(content)))

    repo = gitutil.repo_info(root) if use_git else None
    tokenizer_label = (
        "heuristic, ~4 characters per token"
        if options.tokenizer == "heuristic"
        else "tiktoken cl100k_base"
    )
    document = DumpDocument(
        generated=datetime.now(timezone.utc).isoformat(timespec="seconds"),
        repository=root.name or str(root),
        tree=render_tree(paths),
        tree_paths=len(paths),
        tree_only=options.tree_only,
        tokenizer_label=tokenizer_label,
        repo=repo,
        scope=_scope_label(options),
        files=files,
        skipped=sorted(skipped),
        top_files=options.top_files,
    )
    _apply_budget(document, options, counter)
    text, tokens = _render(document, options.output_format, counter)
    kept = {entry.path for entry in document.files}
    return DumpResult(
        text=text,
        characters=len(text),
        tokens=tokens,
        files=document.files,
        skipped=document.skipped,
        secret_findings=[finding for finding in findings if finding.path in kept],
        used_git=use_git,
        repo=repo,
    )


def generate_dump(
    root_dir: Path, ignore_filter: IgnoreFilter | None = None, tree_only: bool = False
) -> str:
    """Generate a Markdown dump of *root_dir* (compatibility wrapper)."""
    options = DumpOptions(root=root_dir, tree_only=tree_only)
    return build_dump(options, ignore_filter).text
