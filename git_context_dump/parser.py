"""Deprecated alias for :mod:`git_context_dump.walker` (renamed in 1.1.0)."""

from __future__ import annotations

import warnings

from git_context_dump.render import clean_whitespace
from git_context_dump.walker import build_tree, collect_files, read_file_content

warnings.warn(
    "git_context_dump.parser is deprecated; import from git_context_dump.walker "
    "(and clean_whitespace from git_context_dump.render) instead",
    DeprecationWarning,
    stacklevel=2,
)

__all__ = ["build_tree", "clean_whitespace", "collect_files", "read_file_content"]
