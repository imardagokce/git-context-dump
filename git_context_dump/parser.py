"""Collect repository files and render a compact directory tree."""

from __future__ import annotations

from pathlib import Path

from git_context_dump.ignore import IgnoreFilter


def collect_files(root_dir: Path, ignore_filter: IgnoreFilter) -> list[Path]:
    """Return sorted, root-relative paths for all non-ignored regular files."""
    root = root_dir.resolve()
    files: list[Path] = []

    def visit(directory: Path) -> None:
        try:
            entries = sorted(directory.iterdir(), key=lambda entry: entry.name)
        except OSError:
            return
        for entry in entries:
            if ignore_filter.is_ignored(entry):
                continue
            if entry.is_dir() and not entry.is_symlink():
                visit(entry)
            elif entry.is_file():
                files.append(entry.relative_to(root))

    visit(root)
    return sorted(files, key=lambda path: path.as_posix())


def build_tree(root_dir: Path, ignore_filter: IgnoreFilter) -> str:
    """Build an ASCII tree of the repository, pruning ignored sub-trees."""
    root = root_dir.resolve()
    lines: list[str] = []

    def visit(directory: Path, prefix: str) -> None:
        try:
            entries = sorted(directory.iterdir(), key=lambda entry: entry.name)
        except OSError:
            return
        visible = [entry for entry in entries if not ignore_filter.is_ignored(entry)]
        for index, entry in enumerate(visible):
            final = index == len(visible) - 1
            lines.append(f"{prefix}{'└── ' if final else '├── '}{entry.name}")
            if entry.is_dir() and not entry.is_symlink():
                visit(entry, prefix + ("    " if final else "│   "))

    visit(root, "")
    return "\n".join(lines)


def read_file_content(file_path: Path) -> str | None:
    """Read UTF-8 text safely, returning ``None`` for binary or unreadable files."""
    try:
        content = file_path.read_text(encoding="utf-8")
    except (UnicodeDecodeError, OSError):
        return None
    if "\0" in content:
        return None
    return content


def clean_whitespace(content: str) -> str:
    """Trim line endings and reduce runs of blank lines to at most one."""
    cleaned_lines: list[str] = []
    blank_run = 0
    for line in content.splitlines():
        trimmed = line.rstrip()
        if not trimmed:
            blank_run += 1
            if blank_run <= 1:
                cleaned_lines.append("")
        else:
            blank_run = 0
            cleaned_lines.append(trimmed)
    return "\n".join(cleaned_lines)
