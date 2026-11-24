"""Tests for the command-line interface."""

from __future__ import annotations

import io
import os
import subprocess
import sys
import unittest
from contextlib import redirect_stderr, redirect_stdout
from io import StringIO
from pathlib import Path
from unittest import mock

from git_context_dump import __version__
from git_context_dump.cli import main, parse_size
from git_context_dump.clipboard import ClipboardError
from tests.helpers import TempDirTestCase

PROJECT_ROOT = Path(__file__).resolve().parents[1]


class CliTests(TempDirTestCase):
    def setUp(self) -> None:
        super().setUp()
        self.write("example.py", "print('hello')\n")

    def run_cli(self, *args: str) -> tuple[int, str, str]:
        stdout, stderr = StringIO(), StringIO()
        with redirect_stdout(stdout), redirect_stderr(stderr):
            exit_code = main(["--no-git", *args])
        return exit_code, stdout.getvalue(), stderr.getvalue()

    def test_arguments_create_output_file(self) -> None:
        output_path = self.root / "result.md"
        with mock.patch(
            "sys.argv",
            ["git-context-dump", "--dir", str(self.root), "--out", str(output_path), "--no-git"],
        ):
            exit_code = main()
        self.assertEqual(exit_code, 0)
        output = output_path.read_bytes().decode("utf-8")
        self.assertIn("## Directory Structure", output)
        self.assertIn("### File: example.py", output)
        self.assertIn("## Summary", output)
        self.assertNotIn("\r\n", output)
        self.assertTrue(output.endswith("\n"))

    def test_output_parent_directories_are_created(self) -> None:
        output_path = self.root / "out" / "nested" / "dump.md"
        exit_code, _, _ = self.run_cli("-d", str(self.root), "-o", str(output_path))
        self.assertEqual(exit_code, 0)
        self.assertTrue(output_path.is_file())

    def test_rerun_does_not_include_previous_output(self) -> None:
        output_path = self.root / "snapshot.md"
        for _ in range(2):
            exit_code, _, _ = self.run_cli("-d", str(self.root), "-o", str(output_path))
            self.assertEqual(exit_code, 0)
        self.assertNotIn("snapshot.md", output_path.read_text(encoding="utf-8"))

    def test_default_output_name_follows_format(self) -> None:
        cwd = Path.cwd()
        os.chdir(self.root)
        self.addCleanup(os.chdir, cwd)
        exit_code, _, _ = self.run_cli("--format", "json")
        self.assertEqual(exit_code, 0)
        self.assertTrue((self.root / "context.json").is_file())
        exit_code, _, _ = self.run_cli("--format", "json")
        self.assertNotIn('"context.json"', (self.root / "context.json").read_text("utf-8"))

    def test_dash_output_writes_to_stdout(self) -> None:
        exit_code, stdout, _ = self.run_cli("-d", str(self.root), "-o", "-")
        self.assertEqual(exit_code, 0)
        self.assertIn("# Git Context Dump", stdout)
        self.assertIn("### File: example.py", stdout)
        self.assertTrue(stdout.endswith("\n"))

    def test_closed_pipe_is_not_an_error(self) -> None:
        class ClosedPipe(io.StringIO):
            def write(self, text: str) -> int:
                raise BrokenPipeError(32, "Broken pipe")

        class InvalidPipe(io.StringIO):
            def write(self, text: str) -> int:
                raise OSError(22, "Invalid argument")  # how Windows reports it

        for stream in (ClosedPipe(), InvalidPipe()):
            with (
                self.subTest(stream=type(stream).__name__),
                mock.patch.object(sys, "stdout", stream),
                redirect_stderr(StringIO()),
            ):
                self.assertEqual(main(["--no-git", "-d", str(self.root), "-o", "-"]), 0)

    def test_other_stdout_errors_are_reported(self) -> None:
        class FullDisk(io.StringIO):
            def write(self, text: str) -> int:
                raise OSError(28, "No space left on device")

        stderr = StringIO()
        with mock.patch.object(sys, "stdout", FullDisk()), redirect_stderr(stderr):
            self.assertEqual(main(["--no-git", "-d", str(self.root), "-o", "-"]), 1)
        self.assertIn("No space left", stderr.getvalue())

    def test_stdout_is_utf8_even_on_a_cp1252_console(self) -> None:
        raw = io.BytesIO()
        console = io.TextIOWrapper(raw, encoding="cp1252", errors="strict")
        with mock.patch.object(sys, "stdout", console), redirect_stderr(StringIO()):
            exit_code = main(["--no-git", "-d", str(self.root), "-o", "-"])
        self.assertEqual(exit_code, 0)
        self.assertIn("└── example.py", raw.getvalue().decode("utf-8"))

    def test_tree_only_option_omits_file_contents(self) -> None:
        exit_code, stdout, _ = self.run_cli("-d", str(self.root), "-o", "-", "--tree-only")
        self.assertEqual(exit_code, 0)
        self.assertIn("example.py", stdout)
        self.assertNotIn("## File Contents", stdout)

    def test_invalid_directory_returns_one_and_reports_error(self) -> None:
        exit_code, _, stderr = self.run_cli("--dir", str(self.root / "missing"))
        self.assertEqual(exit_code, 1)
        self.assertIn("target directory does not exist", stderr)

    def test_negative_max_tokens_is_rejected(self) -> None:
        exit_code, _, stderr = self.run_cli("-d", str(self.root), "--max-tokens", "-1")
        self.assertEqual(exit_code, 1)
        self.assertIn("--max-tokens", stderr)

    def test_token_threshold_emits_warning(self) -> None:
        exit_code, _, stderr = self.run_cli("-d", str(self.root), "-o", "-", "--max-tokens", "0")
        self.assertEqual(exit_code, 0)
        self.assertIn("Warning:", stderr)

    def test_fit_budget_flag(self) -> None:
        self.write("huge.py", "z = 1\n" * 3000)
        exit_code, stdout, stderr = self.run_cli(
            "-d", str(self.root), "-o", "-", "--max-tokens", "800", "--fit-budget", "-v"
        )
        self.assertEqual(exit_code, 0)
        self.assertNotIn("### File: huge.py", stdout)
        self.assertIn("Skipped: huge.py (token budget)", stderr)
        self.assertNotIn("exceeding", stderr)

    def test_formats(self) -> None:
        _, xml_out, _ = self.run_cli("-d", str(self.root), "-o", "-", "-f", "xml")
        self.assertTrue(xml_out.startswith("<?xml"))
        _, json_out, _ = self.run_cli("-d", str(self.root), "-o", "-", "--format", "json")
        self.assertTrue(json_out.startswith("{"))

    def test_include_exclude_and_size_flags(self) -> None:
        self.write("notes.md", "notes\n")
        self.write("big.py", "x" * 4096)
        _, stdout, stderr = self.run_cli(
            "-d",
            str(self.root),
            "-o",
            "-",
            "--include",
            "*.py",
            "--exclude",
            "example.py",
            "--max-file-size",
            "1k",
        )
        self.assertNotIn("notes.md", stdout)
        self.assertNotIn("### File: example.py", stdout)
        self.assertNotIn("### File: big.py", stdout)
        self.assertIn("1 file(s) skipped", stderr)

    def test_secret_warning_is_printed(self) -> None:
        self.write("settings.py", 'SECRET_KEY = "0123456789abcdefghij"\n')
        _, _, stderr = self.run_cli("-d", str(self.root), "-o", "-")
        self.assertIn("settings.py:1: possible hard-coded secret", stderr)
        self.assertNotIn("0123456789abcdefghij", stderr)

    def test_change_modes_need_git(self) -> None:
        exit_code, _, stderr = self.run_cli("-d", str(self.root), "--diff")
        self.assertEqual(exit_code, 1)
        self.assertIn("--no-git", stderr)
        stderr_buffer = StringIO()
        with (
            redirect_stderr(stderr_buffer),
            mock.patch("git_context_dump.gitutil.is_work_tree", return_value=False),
        ):
            exit_code = main(["-d", str(self.root), "--since", "v1", "-o", "-"])
        self.assertEqual(exit_code, 1)
        self.assertIn("needs a Git working tree", stderr_buffer.getvalue())

    def test_mutually_exclusive_change_flags(self) -> None:
        with redirect_stderr(StringIO()), self.assertRaises(SystemExit) as raised:
            main(["--diff", "--staged"])
        self.assertEqual(raised.exception.code, 2)

    def test_copy_flag(self) -> None:
        with mock.patch("git_context_dump.cli.copy_to_clipboard") as copy:
            exit_code, _, _ = self.run_cli("-d", str(self.root), "-o", "-", "--copy")
        self.assertEqual(exit_code, 0)
        self.assertIn("### File: example.py", copy.call_args.args[0])
        with mock.patch(
            "git_context_dump.cli.copy_to_clipboard", side_effect=ClipboardError("no tool")
        ):
            exit_code, _, stderr = self.run_cli("-d", str(self.root), "-o", "-", "--copy")
        self.assertEqual(exit_code, 1)
        self.assertIn("clipboard", stderr)

    def test_verbose_reports_source(self) -> None:
        self.write("blob.bin", data=b"\x00\x01")
        _, _, stderr = self.run_cli("-d", str(self.root), "-o", "-", "--verbose")
        self.assertIn("Skipped: blob.bin (binary)", stderr)
        self.assertIn("via file system walk", stderr)

    def test_version_flag(self) -> None:
        stdout = StringIO()
        with redirect_stdout(stdout), self.assertRaises(SystemExit) as raised:
            main(["--version"])
        self.assertEqual(raised.exception.code, 0)
        self.assertIn(__version__, stdout.getvalue())

    def test_parse_size(self) -> None:
        self.assertEqual(parse_size("500"), 500)
        self.assertEqual(parse_size("256k"), 256 * 1024)
        self.assertEqual(parse_size("1MB"), 1024**2)
        self.assertEqual(parse_size("0"), 0)
        with redirect_stderr(StringIO()), self.assertRaises(SystemExit):
            main(["--max-file-size", "lots"])

    def test_write_errors_are_reported(self) -> None:
        (self.root / "taken").write_text("file, not a directory", encoding="utf-8")
        exit_code, _, stderr = self.run_cli(
            "-d", str(self.root), "-o", str(self.root / "taken" / "x.md")
        )
        self.assertEqual(exit_code, 1)
        self.assertIn("unable to generate context dump", stderr)


class EntryPointTests(TempDirTestCase):
    """Run the real module in a subprocess, with the platform's default encodings."""

    def run_module(self, *args: str) -> subprocess.CompletedProcess[bytes]:
        environment = {
            key: value
            for key, value in os.environ.items()
            if key not in ("PYTHONIOENCODING", "PYTHONUTF8")
        }
        environment["PYTHONPATH"] = str(PROJECT_ROOT)
        return subprocess.run(
            [sys.executable, "-m", "git_context_dump.cli", *args],
            capture_output=True,
            env=environment,
            cwd=self.root,
            check=False,
        )

    def test_version(self) -> None:
        completed = self.run_module("--version")
        self.assertEqual(completed.returncode, 0, completed.stderr)
        self.assertIn(__version__.encode(), completed.stdout)

    def test_stdout_pipe_with_box_drawing_characters(self) -> None:
        self.write("ünïcode/şey.py", "print('ğ')\n")
        completed = self.run_module("-o", "-", "--no-git")
        self.assertEqual(completed.returncode, 0, completed.stderr)
        output = completed.stdout.decode("utf-8")
        self.assertIn("└── şey.py", output)
        self.assertIn("print('ğ')", output)


if __name__ == "__main__":
    unittest.main()
