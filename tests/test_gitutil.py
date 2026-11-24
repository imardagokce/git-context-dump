"""Tests for the Git-aware file listing and change modes."""

from __future__ import annotations

import unittest
from unittest import mock

from git_context_dump import gitutil
from git_context_dump.dumper import DumpOptions, build_dump
from tests.helpers import GitRepoTestCase, TempDirTestCase


class GitUtilTests(GitRepoTestCase):
    def setUp(self) -> None:
        super().setUp()
        self.write(".gitignore", "*.log\n")
        self.write("sub/.gitignore", "local.cfg\n")
        self.write("README.md", "hello\n")
        self.write("src/app.py", "print(1)\n")
        self.write("sub/local.cfg", "ignored by nested gitignore\n")
        self.write("debug.log", "ignored\n")
        self.commit_all("initial")

    def test_work_tree_detection(self) -> None:
        self.assertTrue(gitutil.is_work_tree(self.root))
        self.assertTrue(gitutil.is_work_tree(self.root / "src"))

    def test_list_files_uses_git_ignore_semantics(self) -> None:
        self.write("new.txt", "untracked\n")
        files = gitutil.list_files(self.root)
        self.assertEqual(
            files, [".gitignore", "README.md", "new.txt", "src/app.py", "sub/.gitignore"]
        )

    def test_list_files_from_subdirectory_is_relative(self) -> None:
        self.assertEqual(gitutil.list_files(self.root / "src"), ["app.py"])

    def test_force_added_ignored_file_is_listed(self) -> None:
        self.write("keep.log", "tracked on purpose\n")
        self.git("add", "-f", "keep.log")
        self.assertIn("keep.log", gitutil.list_files(self.root))

    def test_repo_info(self) -> None:
        info = gitutil.repo_info(self.root)
        self.assertEqual(info.branch, "main")
        self.assertEqual(info.commit, self.git("rev-parse", "--short", "HEAD"))
        self.assertFalse(info.dirty)
        self.write("README.md", "changed\n")
        self.assertTrue(gitutil.repo_info(self.root).dirty)

    def test_detached_head(self) -> None:
        self.git("checkout", "-q", "--detach")
        self.assertEqual(gitutil.repo_info(self.root).branch, "(detached HEAD)")

    def test_change_modes(self) -> None:
        self.git("tag", "v1")
        self.write("README.md", "changed\n")
        self.write("src/new.py", "x = 1\n")
        self.write("src/staged.py", "y = 2\n")
        self.git("add", "src/staged.py")
        self.assertEqual(
            gitutil.changed_files(self.root, gitutil.CHANGES_DIFF),
            ["README.md", "src/new.py", "src/staged.py"],
        )
        self.assertEqual(
            gitutil.changed_files(self.root, gitutil.CHANGES_STAGED), ["src/staged.py"]
        )
        self.commit_all("second")
        self.write("src/app.py", "print(2)\n")
        self.assertEqual(
            gitutil.changed_files(self.root, gitutil.CHANGES_SINCE, "v1"),
            ["README.md", "src/app.py", "src/new.py", "src/staged.py"],
        )

    def test_deleted_files_are_omitted(self) -> None:
        (self.root / "README.md").unlink()
        self.assertEqual(gitutil.changed_files(self.root, gitutil.CHANGES_DIFF), [])
        self.assertNotIn("README.md", gitutil.list_files(self.root))

    def test_invalid_references_are_rejected(self) -> None:
        for ref in ("does-not-exist", "--output=/tmp/x", "", None):
            with self.subTest(ref=ref), self.assertRaises(gitutil.GitError):
                gitutil.changed_files(self.root, gitutil.CHANGES_SINCE, ref)
        with self.assertRaises(gitutil.GitError):
            gitutil.changed_files(self.root, "bogus")

    def test_build_dump_uses_git_and_reports_branch(self) -> None:
        self.write("keep.log", "tracked on purpose\n")
        self.git("add", "-f", "keep.log")
        result = build_dump(DumpOptions(root=self.root))
        self.assertTrue(result.used_git)
        self.assertIn("- Branch: main", result.text)
        self.assertIn("- Commit: ", result.text)
        self.assertIn("### File: keep.log", result.text)
        self.assertNotIn("── local.cfg", result.text)
        self.assertNotIn("debug.log", result.text)

    def test_build_dump_still_applies_default_exclusions_in_git_mode(self) -> None:
        self.write(".env", "TOKEN=secret\n")
        self.write("logo.png", data=b"\x89PNG")
        self.commit_all("add secrets")
        text = build_dump(DumpOptions(root=self.root, exclude=["src/"])).text
        self.assertNotIn("TOKEN=secret", text)
        self.assertNotIn("logo.png", text)
        self.assertNotIn("app.py", text)

    def test_build_dump_diff_scope(self) -> None:
        self.write("src/app.py", "print(2)\n")
        result = build_dump(DumpOptions(root=self.root, changes=gitutil.CHANGES_DIFF))
        self.assertEqual([entry.path for entry in result.files], ["src/app.py"])
        self.assertIn("- Scope: uncommitted changes", result.text)
        since = build_dump(
            DumpOptions(root=self.root, changes=gitutil.CHANGES_SINCE, since_ref="HEAD")
        )
        self.assertIn("- Scope: changes since HEAD", since.text)

    def test_git_mode_off_walks_the_file_system(self) -> None:
        result = build_dump(DumpOptions(root=self.root, git_mode="off"))
        self.assertFalse(result.used_git)
        self.assertNotIn("- Branch:", result.text)
        self.assertNotIn("── local.cfg", result.text)


class EmptyRepositoryTests(GitRepoTestCase):
    def test_repository_without_commits(self) -> None:
        self.write("a.txt", "x\n")
        info = gitutil.repo_info(self.root)
        self.assertIsNone(info.commit)
        self.assertEqual(info.branch, "main")
        self.assertEqual(gitutil.changed_files(self.root, gitutil.CHANGES_DIFF), ["a.txt"])


class NoGitTests(TempDirTestCase):
    def test_without_git_executable(self) -> None:
        with mock.patch("git_context_dump.gitutil.shutil.which", return_value=None):
            self.assertFalse(gitutil.git_available())
            self.assertFalse(gitutil.is_work_tree(self.root))

    def test_git_command_failure_raises(self) -> None:
        with (
            mock.patch("git_context_dump.gitutil._run", return_value=None),
            self.assertRaises(gitutil.GitError),
        ):
            gitutil.list_files(self.root)

    def test_os_error_running_git_is_handled(self) -> None:
        with mock.patch("git_context_dump.gitutil.subprocess.run", side_effect=OSError("boom")):
            self.assertIsNone(gitutil._run(self.root, "status"))


if __name__ == "__main__":
    unittest.main()
