"""Tests for tokens, secret scanning and clipboard support."""

from __future__ import annotations

import subprocess
import unittest
from unittest import mock

from git_context_dump import clipboard
from git_context_dump.secret_scan import scan_text
from git_context_dump.tokens import estimate_tokens, get_token_counter


class TokenTests(unittest.TestCase):
    def test_estimate_tokens_uses_four_characters_per_token(self) -> None:
        self.assertEqual(estimate_tokens(""), 0)
        self.assertEqual(estimate_tokens("abcd"), 1)
        self.assertEqual(estimate_tokens("abcdefghij"), 3)

    def test_counter_lookup(self) -> None:
        self.assertIs(get_token_counter("heuristic"), estimate_tokens)
        with self.assertRaises(ValueError):
            get_token_counter("words")

    def test_tiktoken_counter_when_available(self) -> None:
        class FakeEncoding:
            def encode(self, text: str, disallowed_special: tuple[str, ...]) -> list[int]:
                return list(range(len(text.split())))

        fake_module = mock.Mock()
        fake_module.get_encoding.return_value = FakeEncoding()
        with mock.patch.dict("sys.modules", {"tiktoken": fake_module}):
            counter = get_token_counter("tiktoken")
        self.assertEqual(counter("one two three"), 3)
        fake_module.get_encoding.assert_called_once_with("cl100k_base")


class SecretScanTests(unittest.TestCase):
    def test_detects_common_credentials(self) -> None:
        samples = {
            "-----BEGIN RSA PRIVATE KEY-----": "private key",
            "-----BEGIN PRIVATE KEY-----": "private key",
            "aws = 'AKIAIOSFODNN7EXAMPLE'": "AWS access key",
            "token: ghp_" + "a" * 36: "GitHub token",
            "SLACK=xoxb-123456789012-abc": "Slack token",
            "stripe = 'sk_live_" + "a" * 24 + "'": "Stripe live key",
            "key = AIza" + "b" * 35: "Google API key",
            "ANTHROPIC_API_KEY=sk-ant-" + "c" * 30: "API key",
            'db_password = "hunter2hunter2hunter2"': "hard-coded secret",
            '"apiKey": "0123456789abcdef0123"': "hard-coded secret",
        }
        for line, kind in samples.items():
            with self.subTest(line=line):
                findings = scan_text("f.txt", "first\n" + line)
                self.assertEqual([(item.line, item.kind) for item in findings], [(2, kind)])

    def test_ignores_harmless_lines(self) -> None:
        text = "\n".join(
            [
                "password = os.environ['DB_PASSWORD']",
                'api_key = "${API_KEY}"',
                "token = get_token()",
                'secret = "short"',
                "# the AWS key goes in AKIA... format",
            ]
        )
        self.assertEqual(scan_text("f.py", text), [])

    def test_finding_string_never_contains_the_value(self) -> None:
        finding = scan_text("cfg.py", 'secret_key = "abcdefghijklmnop"')[0]
        self.assertEqual(str(finding), "cfg.py:1: possible hard-coded secret")


class ClipboardTests(unittest.TestCase):
    def test_windows_uses_clip_with_utf16(self) -> None:
        with (
            mock.patch.object(clipboard.sys, "platform", "win32"),
            mock.patch.object(clipboard.shutil, "which", return_value="clip"),
            mock.patch.object(clipboard.subprocess, "run") as run,
        ):
            clipboard.copy_to_clipboard("├── ş")
        command = run.call_args.args[0]
        data = run.call_args.kwargs["input"]
        self.assertEqual(command, ["clip"])
        self.assertEqual(data.decode("utf-16"), "├── ş")
        self.assertIn(data[:2], (b"\xff\xfe", b"\xfe\xff"))

    def test_linux_falls_back_through_tools(self) -> None:
        available = {"xsel"}
        with (
            mock.patch.object(clipboard.sys, "platform", "linux"),
            mock.patch.object(
                clipboard.shutil,
                "which",
                side_effect=lambda name: name if name in available else None,
            ),
            mock.patch.object(clipboard.subprocess, "run") as run,
        ):
            clipboard.copy_to_clipboard("hi")
        self.assertEqual(run.call_args.args[0], ["xsel", "--clipboard", "--input"])

    def test_macos_uses_pbcopy(self) -> None:
        with (
            mock.patch.object(clipboard.sys, "platform", "darwin"),
            mock.patch.object(clipboard.shutil, "which", return_value="/usr/bin/pbcopy"),
            mock.patch.object(clipboard.subprocess, "run") as run,
        ):
            clipboard.copy_to_clipboard("hi")
        self.assertEqual(run.call_args.args[0], ["pbcopy"])

    def test_errors(self) -> None:
        with (
            mock.patch.object(clipboard.sys, "platform", "linux"),
            mock.patch.object(clipboard.shutil, "which", return_value=None),
            self.assertRaises(clipboard.ClipboardError),
        ):
            clipboard.copy_to_clipboard("hi")
        with (
            mock.patch.object(clipboard.sys, "platform", "darwin"),
            mock.patch.object(clipboard.shutil, "which", return_value="/usr/bin/pbcopy"),
            mock.patch.object(
                clipboard.subprocess,
                "run",
                side_effect=subprocess.CalledProcessError(1, "pbcopy"),
            ),
            self.assertRaises(clipboard.ClipboardError),
        ):
            clipboard.copy_to_clipboard("hi")


if __name__ == "__main__":
    unittest.main()
