"""Tests for repository ignore rules."""

from pathlib import Path
import tempfile
import unittest

from git_context_dump.ignore import IgnoreFilter


class IgnoreFilterTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary_directory = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary_directory.name)
        self.filter = IgnoreFilter(self.root)

    def tearDown(self) -> None:
        self.temporary_directory.cleanup()

    def test_default_file_and_directory_exclusions(self) -> None:
        ignored_paths = (
            ".git/config",
            ".venv/lib/module.py",
            "venv/bin/python",
            "__pycache__/module.cpython-312.pyc",
            "module.pyc",
            "node_modules/package/index.js",
            "dist/app.js",
            "build/output.o",
            ".DS_Store",
            "image.png",
            "image.jpg",
            "archive.zip",
            "document.pdf",
            "program.exe",
            "context.md",
        )
        for name in ignored_paths:
            with self.subTest(path=name):
                self.assertTrue(self.filter.is_ignored(Path(name)))

    def test_unmatched_paths_are_kept(self) -> None:
        for name in ("src/main.py", "README.md", "assets/image.svg", "nested/data.json"):
            with self.subTest(path=name):
                self.assertFalse(self.filter.is_ignored(Path(name)))

    def test_root_gitignore_parses_comments_blanks_and_patterns(self) -> None:
        (self.root / ".gitignore").write_text(
            "# generated files\n\n*.log\n/secret.txt\n/cache/\n", encoding="utf-8"
        )
        filter_ = IgnoreFilter(self.root)
        self.assertTrue(filter_.is_ignored(Path("app.log")))
        self.assertTrue(filter_.is_ignored(Path("nested/app.log")))
        self.assertTrue(filter_.is_ignored(Path("secret.txt")))
        self.assertFalse(filter_.is_ignored(Path("nested/secret.txt")))
        self.assertTrue(filter_.is_ignored(Path("cache/item.bin")))
        self.assertFalse(filter_.is_ignored(Path("nested/cache/item.bin")))

    def test_directory_rules_allow_early_pruning(self) -> None:
        ignored_directory = self.root / "generated"
        ignored_directory.mkdir()
        (self.root / ".gitignore").write_text("/generated/\n", encoding="utf-8")
        filter_ = IgnoreFilter(self.root)

        self.assertTrue(filter_.is_ignored(Path("generated")))
        self.assertTrue(filter_.is_ignored(Path("generated/deep/file.txt")))
        self.assertFalse(filter_.is_ignored(Path("other/generated/file.txt")))

    def test_wildcards_and_nested_directory_patterns(self) -> None:
        (self.root / ".gitignore").write_text("*.tmp\nlogs/*/private/\n", encoding="utf-8")
        filter_ = IgnoreFilter(self.root)
        self.assertTrue(filter_.is_ignored(Path("nested/file.tmp")))
        self.assertTrue(filter_.is_ignored(Path("logs/2026/private/secret.txt")))
        self.assertFalse(filter_.is_ignored(Path("logs/2026/public/secret.txt")))

    def test_negation_reincludes_a_matching_file(self) -> None:
        (self.root / ".gitignore").write_text("*.log\n!important.log\n", encoding="utf-8")
        filter_ = IgnoreFilter(self.root)
        self.assertTrue(filter_.is_ignored(Path("other.log")))
        self.assertFalse(filter_.is_ignored(Path("important.log")))


if __name__ == "__main__":
    unittest.main()
