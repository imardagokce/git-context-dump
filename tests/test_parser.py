"""Tests for repository parsing and tree visualisation."""

from pathlib import Path
import tempfile
import unittest

from git_context_dump.ignore import IgnoreFilter
from git_context_dump.parser import (
    build_tree,
    clean_whitespace,
    collect_files,
    read_file_content,
)


class ParserTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary_directory = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary_directory.name)
        (self.root / "src").mkdir()
        (self.root / "src" / "main.py").write_text("print('hello')\n", encoding="utf-8")
        (self.root / "README.md").write_text("Project\n", encoding="utf-8")
        (self.root / "dist").mkdir()
        (self.root / "dist" / "bundle.js").write_text("ignored\n", encoding="utf-8")
        (self.root / "image.png").write_bytes(b"not really a png")
        self.ignore_filter = IgnoreFilter(self.root)

    def tearDown(self) -> None:
        self.temporary_directory.cleanup()

    def test_build_tree_uses_ascii_branches_and_prunes_ignored_paths(self) -> None:
        tree = build_tree(self.root, self.ignore_filter)
        self.assertEqual(tree, "├── README.md\n└── src\n    └── main.py")
        self.assertNotIn("dist", tree)
        self.assertNotIn("image.png", tree)

    def test_collect_files_returns_sorted_relative_paths(self) -> None:
        paths = collect_files(self.root, self.ignore_filter)
        self.assertEqual(paths, [Path("README.md"), Path("src/main.py")])
        self.assertTrue(all(not path.is_absolute() for path in paths))

    def test_collect_files_prunes_gitignored_directories(self) -> None:
        (self.root / ".gitignore").write_text("private/\n", encoding="utf-8")
        private = self.root / "private"
        private.mkdir()
        (private / "secret.txt").write_text("secret", encoding="utf-8")
        paths = collect_files(self.root, IgnoreFilter(self.root))
        self.assertNotIn(Path("private/secret.txt"), paths)

    def test_read_file_content_returns_text_and_skips_binary_data(self) -> None:
        self.assertEqual(read_file_content(self.root / "README.md"), "Project\n")
        binary_file = self.root / "binary.dat"
        binary_file.write_bytes(b"\xff\xfe\x00")
        self.assertIsNone(read_file_content(binary_file))
        nul_file = self.root / "nul.dat"
        nul_file.write_bytes(b"valid text\x00with nul")
        self.assertIsNone(read_file_content(nul_file))
        self.assertIsNone(read_file_content(self.root / "missing.txt"))

    def test_clean_whitespace_trims_lines_and_collapses_blank_runs(self) -> None:
        content = "first  \n\n\n\nsecond\t\n\nthird   "
        self.assertEqual(clean_whitespace(content), "first\n\nsecond\n\nthird")


if __name__ == "__main__":
    unittest.main()
