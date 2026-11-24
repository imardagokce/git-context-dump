"""Thin wrappers around the ``git`` command line used for Git-aware dumps."""

from __future__ import annotations

import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path

CHANGES_DIFF = "diff"
CHANGES_STAGED = "staged"
CHANGES_SINCE = "since"


class GitError(ValueError):
    """Raised when a Git operation the user asked for cannot be performed."""


@dataclass(frozen=True)
class RepoInfo:
    """Branch and commit of the repository being dumped."""

    branch: str | None
    commit: str | None
    dirty: bool


def git_available() -> bool:
    """Return whether a ``git`` executable is on ``PATH``."""
    return shutil.which("git") is not None


def _run(root: Path, *args: str) -> bytes | None:
    try:
        completed = subprocess.run(
            ["git", "-c", "core.quotepath=off", *args],
            cwd=root,
            capture_output=True,
            check=False,
            timeout=60,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    if completed.returncode != 0:
        return None
    return completed.stdout


def _text(root: Path, *args: str) -> str | None:
    output = _run(root, *args)
    return None if output is None else output.decode("utf-8", "replace").strip()


def _paths(root: Path, *args: str) -> list[str]:
    output = _run(root, *args)
    if output is None:
        raise GitError(f"git {' '.join(args)} failed in {root}")
    return [item.decode("utf-8", "surrogateescape") for item in output.split(b"\0") if item]


def is_work_tree(root: Path) -> bool:
    """Return whether *root* lies inside a Git working tree."""
    return git_available() and _text(root, "rev-parse", "--is-inside-work-tree") == "true"


def _has_head(root: Path) -> bool:
    return _run(root, "rev-parse", "--verify", "--quiet", "HEAD") is not None


def repo_info(root: Path) -> RepoInfo:
    """Return the current branch, short commit hash and dirty state."""
    has_head = _has_head(root)
    branch = _text(root, "symbolic-ref", "--short", "-q", "HEAD")
    if branch is None and has_head:
        branch = "(detached HEAD)"
    commit = _text(root, "rev-parse", "--short", "HEAD") if has_head else None
    status = _text(root, "status", "--porcelain", "--untracked-files=normal")
    return RepoInfo(branch=branch, commit=commit, dirty=bool(status))


def _existing_files(root: Path, paths: list[str]) -> list[str]:
    unique = sorted(set(paths))
    return [path for path in unique if (root / path).is_file()]


def list_files(root: Path) -> list[str]:
    """List tracked plus untracked, not-ignored files under *root*."""
    paths = _paths(root, "ls-files", "--cached", "--others", "--exclude-standard", "-z")
    return _existing_files(root, paths)


def _untracked(root: Path) -> list[str]:
    return _paths(root, "ls-files", "--others", "--exclude-standard", "-z")


def changed_files(root: Path, mode: str, ref: str | None = None) -> list[str]:
    """List files changed in the working tree, the index, or since *ref*.

    ``diff`` compares the working tree (including untracked files) with
    ``HEAD``; ``staged`` lists files staged for the next commit; ``since``
    compares the working tree (including untracked files) with *ref*.
    Deleted files are omitted because there is nothing left to show.
    """
    if mode == CHANGES_STAGED:
        paths = _paths(root, "diff", "--cached", "--name-only", "--relative", "-z")
    elif mode == CHANGES_DIFF:
        if _has_head(root):
            paths = _paths(root, "diff", "HEAD", "--name-only", "--relative", "-z")
        else:
            paths = _paths(root, "ls-files", "--cached", "-z")
        paths += _untracked(root)
    elif mode == CHANGES_SINCE:
        if not ref or ref.startswith("-"):
            raise GitError(f"invalid git reference: {ref!r}")
        if _run(root, "rev-parse", "--verify", "--quiet", f"{ref}^{{commit}}") is None:
            raise GitError(f"unknown git reference: {ref}")
        paths = _paths(root, "diff", ref, "--name-only", "--relative", "-z", "--")
        paths += _untracked(root)
    else:
        raise GitError(f"unknown change mode: {mode}")
    return _existing_files(root, paths)
