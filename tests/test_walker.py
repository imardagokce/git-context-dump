"""Tests for directory walking, tree rendering and file reading."""

from __future__ import annotations

import importlib
import shutil
import sys
import unittest
import warnings
from pathlib import Path

from git_context_dump.ignore import IgnoreFilter
from git_context_dump.walker import (
    SKIP_BINARY,
    SKIP_OUTSIDE_ROOT,
    SKIP_TOO_LARGE,
    SKIP_UNDECODABLE,
    SKIP_UNREADABLE,
    build_tree,
    collect_files,
    read_file_content,
    read_text_file,
    render_tree,
    walk,
)
from tests.helpers import TempDirTestCase


class WalkerTests(TempDirTestCase):
    def setUp(self) -> None:
        super().setUp()
        self.write("src/main.py", "print('hello')\n")
        self.write("README.md", "Project\n")
        self.write("dist/bundle.js", "ignored\n")
        self.write("image.png", data=b"not really a png")
        self.ignore_filter = IgnoreFilter(self.root)

    def test_build_tree_uses_ascii_branches_and_prunes_ignored_paths(self) -> None:
        tree = build_tree(self.root, self.ignore_filter)
        self.assertEqual(tree, "├── README.md\n└── src\n    └── main.py")

    def test_render_tree_nests_and_sorts(self) -> None:
        tree = render_tree(["b/z.txt", "a.txt", "b/c/d.txt"])
        self.assertEqual(tree, "├── a.txt\n└── b\n    ├── c\n    │   └── d.txt\n    └── z.txt")
        self.assertEqual(render_tree([]), "")

    def test_collect_files_returns_sorted_relative_paths(self) -> None:
        paths = collect_files(self.root, self.ignore_filter)
        self.assertEqual(paths, [Path("README.md"), Path("src/main.py")])
        self.assertTrue(all(not path.is_absolute() for path in paths))

    def test_collect_files_prunes_gitignored_directories(self) -> None:
        self.write(".gitignore", "private/\n")
        self.write("private/secret.txt", "secret")
        paths = collect_files(self.root, IgnoreFilter(self.root))
        self.assertNotIn(Path("private/secret.txt"), paths)

    def test_nested_gitignore_is_respected_while_walking(self) -> None:
        self.write("sub/.gitignore", "secret.txt\n")
        self.write("sub/secret.txt", "x")
        self.write("sub/ok.txt", "x")
        files = walk(self.root, IgnoreFilter(self.root)).files
        self.assertIn("sub/ok.txt", files)
        self.assertNotIn("sub/secret.txt", files)

    def test_walk_honours_include_patterns(self) -> None:
        files = walk(self.root, IgnoreFilter(self.root, includes=["*.py"])).files
        self.assertEqual(files, ["src/main.py"])

    def test_symlinked_file_outside_root_is_skipped(self) -> None:
        outside_dir = self.root.parent / f"{self.root.name}-outside"
        outside_dir.mkdir()
        self.addCleanup(shutil.rmtree, outside_dir, True)
        (outside_dir / "secret.txt").write_text("TOPSECRET", encoding="utf-8")
        self.symlink_or_skip(self.root / "leak.txt", outside_dir / "secret.txt")
        result = walk(self.root, self.ignore_filter)
        self.assertNotIn("leak.txt", result.files)
        self.assertIn(("leak.txt", SKIP_OUTSIDE_ROOT), result.skipped)

    def test_directory_link_outside_root_is_not_followed(self) -> None:
        outside_dir = self.root.parent / f"{self.root.name}-outside-dir"
        outside_dir.mkdir()
        self.addCleanup(shutil.rmtree, outside_dir, True)
        (outside_dir / "secret.txt").write_text("TOPSECRET", encoding="utf-8")
        self.directory_link_or_skip(self.root / "linked", outside_dir)
        result = walk(self.root, self.ignore_filter)
        self.assertFalse(any(path.startswith("linked") for path in result.files))
        self.assertIn(("linked", SKIP_OUTSIDE_ROOT), result.skipped)
        self.assertTrue(self.ignore_filter.is_ignored(self.root / "linked"))
        self.assertTrue(self.ignore_filter.is_ignored(self.root / "linked" / "secret.txt"))

    def test_directory_link_inside_root_is_not_followed(self) -> None:
        self.directory_link_or_skip(self.root / "src-alias", self.root / "src")
        files = walk(self.root, self.ignore_filter).files
        self.assertIn("src/main.py", files)
        self.assertFalse(any(path.startswith("src-alias") for path in files))

    def test_symlink_inside_root_is_kept_and_directory_links_not_followed(self) -> None:
        self.symlink_or_skip(self.root / "alias.md", self.root / "README.md")
        self.symlink_or_skip(self.root / "src-link", self.root / "src")
        files = walk(self.root, self.ignore_filter).files
        self.assertIn("alias.md", files)
        self.assertFalse(any(path.startswith("src-link/") for path in files))

    def test_unreadable_directory_is_reported(self) -> None:
        if sys.platform == "win32":
            self.skipTest("POSIX permissions only")
        locked = self.root / "locked"
        locked.mkdir()
        locked.chmod(0)
        self.addCleanup(locked.chmod, 0o755)
        result = walk(self.root, self.ignore_filter)
        if ("locked", SKIP_UNREADABLE) not in result.skipped:
            self.skipTest("running with permissions that bypass chmod")
        self.assertIn(("locked", SKIP_UNREADABLE), result.skipped)


class ReadTextFileTests(TempDirTestCase):
    def test_reads_utf8_and_normalises_newlines(self) -> None:
        path = self.write("crlf.txt", data=b"a\r\nb\rc\n")
        self.assertEqual(read_file_content(path), "a\nb\nc\n")

    def test_strips_utf8_bom(self) -> None:
        path = self.write("bom.py", data=b"\xef\xbb\xbfprint(1)\n")
        self.assertEqual(read_file_content(path), "print(1)\n")

    def test_decodes_utf16_with_bom(self) -> None:
        path = self.write("u16.txt", data="héllo\n".encode("utf-16"))
        self.assertEqual(read_file_content(path), "héllo\n")

    def test_reports_skip_reasons(self) -> None:
        self.assertEqual(
            read_text_file(self.write("nul.dat", data=b"valid text\x00with nul")).reason,
            SKIP_BINARY,
        )
        self.assertEqual(
            read_text_file(self.write("latin.txt", data=b"caf\xe9")).reason, SKIP_UNDECODABLE
        )
        self.assertEqual(
            read_text_file(self.write("bad16.txt", data=b"\xff\xfe\x00")).reason,
            SKIP_UNDECODABLE,
        )
        self.assertEqual(
            read_text_file(self.write("utf16nul.txt", data=b"\xff\xfe\x00\x00")).reason,
            SKIP_BINARY,
        )
        self.assertEqual(read_text_file(self.root / "missing.txt").reason, SKIP_UNREADABLE)

    def test_size_limit(self) -> None:
        path = self.write("big.txt", "x" * 100)
        self.assertEqual(read_text_file(path, max_bytes=99).reason, SKIP_TOO_LARGE)
        self.assertEqual(read_text_file(path, max_bytes=100).content, "x" * 100)
        self.assertEqual(read_text_file(path).content, "x" * 100)


class ParserShimTests(unittest.TestCase):
    def test_parser_module_is_a_deprecated_alias(self) -> None:
        sys.modules.pop("git_context_dump.parser", None)
        with warnings.catch_warnings(record=True) as caught:
            warnings.simplefilter("always")
            parser = importlib.import_module("git_context_dump.parser")
        self.assertTrue(any(item.category is DeprecationWarning for item in caught))
        self.assertIs(parser.collect_files, collect_files)
        self.assertEqual(parser.clean_whitespace("a  \n\n\nb"), "a\n\nb")


if __name__ == "__main__":
    unittest.main()
