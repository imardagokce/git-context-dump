"""Walk a directory once, render its tree, and read file contents safely."""

from __future__ import annotations

import os
from collections.abc import Iterable
from dataclasses import dataclass, field
from pathlib import Path

from git_context_dump.ignore import IgnoreFilter, is_link

# Reasons a file can be left out of the dump's contents.
SKIP_BINARY = "binary"
SKIP_TOO_LARGE = "too large"
SKIP_UNREADABLE = "unreadable"
SKIP_UNDECODABLE = "not UTF-8/UTF-16 text"
SKIP_OUTSIDE_ROOT = "link outside target directory"
SKIP_BUDGET = "token budget"

_UTF16_BOMS = (b"\xff\xfe", b"\xfe\xff")

_Tree = dict[str, "_Tree"]


@dataclass
class WalkResult:
    """Files found by :func:`walk`, plus what could not be visited."""

    files: list[str] = field(default_factory=list)  # root-relative POSIX paths
    skipped: list[tuple[str, str]] = field(default_factory=list)  # (path, reason)


def walk(root_dir: Path, ignore_filter: IgnoreFilter) -> WalkResult:
    """Visit the tree once, pruning ignored directories and unsafe symlinks."""
    root = root_dir.resolve()
    result = WalkResult()

    def visit(directory: Path, prefix: str) -> None:
        try:
            with os.scandir(directory) as iterator:
                entries = sorted(iterator, key=lambda entry: entry.name)
        except OSError:
            if prefix:
                result.skipped.append((prefix.rstrip("/"), SKIP_UNREADABLE))
            return
        for entry in entries:
            relative = prefix + entry.name
            try:
                link = is_link(Path(entry.path))
                is_dir = entry.is_dir()  # follows links, so a link to a directory counts
            except OSError:
                result.skipped.append((relative, SKIP_UNREADABLE))
                continue
            if ignore_filter.matches(relative, is_dir):
                continue
            if link:
                if ignore_filter.escapes_root(Path(entry.path)):
                    result.skipped.append((relative, SKIP_OUTSIDE_ROOT))
                    continue
                if is_dir:
                    continue  # never follow directory links: avoids cycles and duplicates
            if is_dir:
                visit(Path(entry.path), relative + "/")
            elif entry.is_file() and ignore_filter.wants_file(relative):
                result.files.append(relative)

    visit(root, "")
    result.files.sort()
    return result


def render_tree(paths: Iterable[str]) -> str:
    """Render root-relative POSIX paths as an ASCII tree."""
    tree: _Tree = {}
    for path in paths:
        node = tree
        for part in path.split("/"):
            node = node.setdefault(part, {})
    lines: list[str] = []

    def emit(node: _Tree, prefix: str) -> None:
        names = sorted(node)
        for index, name in enumerate(names):
            final = index == len(names) - 1
            lines.append(f"{prefix}{'└── ' if final else '├── '}{name}")
            emit(node[name], prefix + ("    " if final else "│   "))

    emit(tree, "")
    return "\n".join(lines)


def collect_files(root_dir: Path, ignore_filter: IgnoreFilter) -> list[Path]:
    """Return sorted, root-relative paths for all non-ignored regular files."""
    return [Path(path) for path in walk(root_dir, ignore_filter).files]


def build_tree(root_dir: Path, ignore_filter: IgnoreFilter) -> str:
    """Build an ASCII tree of the repository's non-ignored files."""
    return render_tree(walk(root_dir, ignore_filter).files)


@dataclass(frozen=True)
class FileRead:
    """Outcome of reading one file: its text, or why it was skipped."""

    content: str | None
    reason: str | None = None


def read_text_file(file_path: Path, max_bytes: int | None = None) -> FileRead:
    """Read a text file, decoding UTF-8 (BOM stripped) or BOM-marked UTF-16."""
    try:
        if max_bytes is not None and file_path.stat().st_size > max_bytes:
            return FileRead(None, SKIP_TOO_LARGE)
        data = file_path.read_bytes()
    except OSError:
        return FileRead(None, SKIP_UNREADABLE)
    if data.startswith(_UTF16_BOMS):
        try:
            text = data.decode("utf-16")
        except UnicodeDecodeError:
            return FileRead(None, SKIP_UNDECODABLE)
    elif b"\0" in data:
        return FileRead(None, SKIP_BINARY)
    else:
        try:
            text = data.decode("utf-8-sig")
        except UnicodeDecodeError:
            return FileRead(None, SKIP_UNDECODABLE)
    if "\0" in text:
        return FileRead(None, SKIP_BINARY)
    return FileRead(text.replace("\r\n", "\n").replace("\r", "\n"))


def read_file_content(file_path: Path) -> str | None:
    """Read text safely, returning ``None`` for binary or unreadable files."""
    return read_text_file(file_path).content
