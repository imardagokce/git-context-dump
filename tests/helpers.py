"""Shared fixtures for the test-suite."""

from __future__ import annotations

import os
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest import mock


class TempDirTestCase(unittest.TestCase):
    """Give each test an empty temporary directory at ``self.root``."""

    def setUp(self) -> None:
        temporary_directory = tempfile.TemporaryDirectory()
        self.addCleanup(temporary_directory.cleanup)
        self.root = Path(temporary_directory.name).resolve()
        # Keep the user's own global Git excludes out of the tests.
        patcher = mock.patch("git_context_dump.ignore._global_excludes_file", return_value=None)
        patcher.start()
        self.addCleanup(patcher.stop)

    def write(self, relative: str, text: str = "", data: bytes | None = None) -> Path:
        """Create a file (and its parents) with LF newlines or raw bytes."""
        path = self.root / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data if data is not None else text.encode("utf-8"))
        return path

    def symlink_or_skip(self, link: Path, target: Path) -> None:
        """Create a symlink, skipping the test where the OS does not allow it."""
        try:
            os.symlink(target, link, target_is_directory=target.is_dir())
        except (OSError, NotImplementedError) as error:
            self.skipTest(f"symlinks unavailable: {error}")

    def directory_link_or_skip(self, link: Path, target: Path) -> None:
        """Link a directory: a symlink, or a junction on Windows without symlink rights."""
        try:
            os.symlink(target, link, target_is_directory=True)
            return
        except (OSError, NotImplementedError) as error:
            if os.name != "nt":
                self.skipTest(f"symlinks unavailable: {error}")
        completed = subprocess.run(
            ["cmd", "/c", "mklink", "/J", str(link), str(target)],
            capture_output=True,
            check=False,
        )
        if completed.returncode != 0:
            self.skipTest("neither symlinks nor junctions are available")


class GitRepoTestCase(TempDirTestCase):
    """A temporary directory initialised as a Git repository with isolated config."""

    def setUp(self) -> None:
        if shutil.which("git") is None:
            self.skipTest("git is not installed")
        super().setUp()
        config_dir = tempfile.TemporaryDirectory()
        self.addCleanup(config_dir.cleanup)
        empty_config = Path(config_dir.name) / "gitconfig"
        empty_config.write_text("", encoding="utf-8")
        environment = {
            "GIT_CONFIG_GLOBAL": str(empty_config),
            "GIT_CONFIG_NOSYSTEM": "1",
            "GIT_AUTHOR_NAME": "Test",
            "GIT_AUTHOR_EMAIL": "test@example.invalid",
            "GIT_COMMITTER_NAME": "Test",
            "GIT_COMMITTER_EMAIL": "test@example.invalid",
        }
        patcher = mock.patch.dict(os.environ, environment)
        patcher.start()
        self.addCleanup(patcher.stop)
        self.git("init", "-q", "-b", "main")

    def git(self, *args: str) -> str:
        completed = subprocess.run(
            ["git", *args],
            cwd=self.root,
            capture_output=True,
            check=True,
        )
        return completed.stdout.decode("utf-8", "replace").strip()

    def commit_all(self, message: str = "commit") -> None:
        self.git("add", "-A")
        self.git("commit", "-q", "-m", message)
