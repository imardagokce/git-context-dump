"""Tests for the command-line interface."""

from contextlib import redirect_stderr, redirect_stdout
from io import StringIO
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from git_context_dump.cli import main


class CliTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary_directory = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary_directory.name)
        (self.root / "example.py").write_text("print('hello')\n", encoding="utf-8")

    def tearDown(self) -> None:
        self.temporary_directory.cleanup()

    def test_arguments_create_output_file(self) -> None:
        output_path = self.root / "result.md"
        with patch(
            "sys.argv",
            ["git-context-dump", "--dir", str(self.root), "--out", str(output_path)],
        ):
            exit_code = main()

        self.assertEqual(exit_code, 0)
        output = output_path.read_text(encoding="utf-8")
        self.assertIn("## Directory Structure", output)
        self.assertIn("### File: example.py", output)
        self.assertIn("## Summary", output)

    def test_dash_output_writes_to_stdout(self) -> None:
        stdout = StringIO()
        with (
            patch("sys.argv", ["git-context-dump", "-d", str(self.root), "-o", "-"]),
            redirect_stdout(stdout),
        ):
            exit_code = main()

        self.assertEqual(exit_code, 0)
        self.assertIn("# Git Context Dump", stdout.getvalue())
        self.assertIn("### File: example.py", stdout.getvalue())
        self.assertTrue(stdout.getvalue().endswith("\n"))

    def test_tree_only_option_omits_file_contents(self) -> None:
        output_path = self.root / "tree.md"
        with patch(
            "sys.argv",
            [
                "git-context-dump",
                "--dir",
                str(self.root),
                "--out",
                str(output_path),
                "--tree-only",
            ],
        ):
            exit_code = main()

        self.assertEqual(exit_code, 0)
        output = output_path.read_text(encoding="utf-8")
        self.assertIn("example.py", output)
        self.assertNotIn("## File Contents", output)

    def test_invalid_directory_returns_one_and_reports_error(self) -> None:
        stderr = StringIO()
        with (
            patch("sys.argv", ["git-context-dump", "--dir", str(self.root / "missing")]),
            redirect_stderr(stderr),
        ):
            exit_code = main()

        self.assertEqual(exit_code, 1)
        self.assertIn("target directory does not exist", stderr.getvalue())

    def test_token_threshold_emits_warning(self) -> None:
        stderr = StringIO()
        with (
            patch(
                "sys.argv",
                ["git-context-dump", "--dir", str(self.root), "--out", "-", "--max-tokens", "0"],
            ),
            redirect_stdout(StringIO()),
            redirect_stderr(stderr),
        ):
            exit_code = main()

        self.assertEqual(exit_code, 0)
        self.assertIn("Warning:", stderr.getvalue())


if __name__ == "__main__":
    unittest.main()
