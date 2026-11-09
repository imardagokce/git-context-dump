"""Ignore files and directories when creating a repository context dump."""

from __future__ import annotations

import fnmatch
from pathlib import Path


_DEFAULT_PATTERNS: tuple[str, ...] = (
    ".git/",
    ".venv/",
    "venv/",
    "__pycache__/",
    "*.pyc",
    "node_modules/",
    "dist/",
    "build/",
    ".DS_Store",
    "*.png",
    "*.jpg",
    "*.zip",
    "*.pdf",
    "*.exe",
    "context.md",
)


class IgnoreFilter:
    """Apply built-in exclusions and rules from a repository's root .gitignore."""

    def __init__(self, root: Path) -> None:
        self.root: Path = root.resolve()
        self._rules: list[tuple[str, bool, bool, bool]] = []
        for pattern in _DEFAULT_PATTERNS:
            self._add_rule(pattern)
        self.load_gitignore()

    def load_gitignore(self) -> None:
        """Load root .gitignore rules, ignoring blank lines and comments."""
        gitignore = self.root / ".gitignore"
        if not gitignore.is_file():
            return
        for raw_line in gitignore.read_text(encoding="utf-8").splitlines():
            line = raw_line.strip()
            if not line or line.startswith("#"):
                continue
            self._add_rule(line)

    def _add_rule(self, raw_pattern: str) -> None:
        negated = raw_pattern.startswith("!")
        pattern = raw_pattern[1:] if negated else raw_pattern
        if not pattern:
            return
        anchored = pattern.startswith("/")
        directory_only = pattern.endswith("/")
        pattern = pattern.strip("/")
        pattern = pattern.lstrip("/")
        if pattern:
            self._rules.append((pattern, negated, directory_only, anchored))

    @staticmethod
    def _matches(
        pattern: str, path: str, directory_only: bool, anchored: bool, target_is_dir: bool
    ) -> bool:
        parts = path.split("/")
        candidates = ["/".join(parts[:index]) for index in range(1, len(parts) + 1)]
        for index, candidate in enumerate(candidates):
            is_directory = candidate != path or target_is_dir
            if directory_only and not is_directory:
                continue
            if anchored or "/" in pattern:
                if fnmatch.fnmatchcase(candidate, pattern):
                    return True
            elif fnmatch.fnmatchcase(candidate.rsplit("/", 1)[-1], pattern):
                return True
        return False

    def is_ignored(self, path: Path) -> bool:
        """Return whether *path* is excluded; ignored directories prune descendants."""
        absolute = path if path.is_absolute() else self.root / path
        try:
            relative = absolute.resolve().relative_to(self.root).as_posix()
        except ValueError:
            return False
        if relative in ("", "."):
            return False

        ignored = False
        for pattern, negated, directory_only, anchored in self._rules:
            if self._matches(pattern, relative, directory_only, anchored, absolute.is_dir()):
                ignored = not negated
        return ignored
