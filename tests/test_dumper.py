"""Tests for dump collection, budgets and summaries."""

from __future__ import annotations

import importlib.util
import json
import re
import unittest
from unittest import mock

from git_context_dump.dumper import (
    DumpOptions,
    build_dump,
    estimate_tokens,
    generate_dump,
    get_language_tag,
)
from git_context_dump.gitutil import GitError
from git_context_dump.ignore import IgnoreFilter
from git_context_dump.walker import SKIP_BUDGET, SKIP_TOO_LARGE
from tests.helpers import TempDirTestCase


class DumperTests(TempDirTestCase):
    def setUp(self) -> None:
        super().setUp()
        self.write("src/main.py", "print('hello')  \n\n\n")
        self.write("data.json", '{"ok": true}\n')
        self.write("binary.bin", data=b"\x00\x01\x02")
        self.write("dist/bundle.js", "ignored")
        self.ignore_filter = IgnoreFilter(self.root)

    def options(self, **overrides: object) -> DumpOptions:
        return DumpOptions(root=self.root, git_mode="off", **overrides)  # type: ignore[arg-type]

    def test_compat_exports(self) -> None:
        self.assertEqual(estimate_tokens("abcdefghij"), 3)
        self.assertEqual(get_language_tag("x.py"), "python")

    def test_generate_dump_contains_metadata_tree_contents_and_summary(self) -> None:
        dump = generate_dump(self.root, self.ignore_filter)
        self.assertIn("# Git Context Dump", dump)
        self.assertRegex(dump, r"- Generated: \d{4}-\d{2}-\d{2}T[^\n]+\+00:00")
        self.assertIn(f"- Repository: {self.root.name}", dump)
        self.assertNotIn(str(self.root), dump)  # no absolute local paths
        self.assertIn("## Directory Structure", dump)
        self.assertIn("### File: src/main.py\n\n```python\nprint('hello')\n\n```", dump)
        self.assertIn('### File: data.json\n\n```json\n{"ok": true}\n```', dump)
        self.assertNotIn("### File: binary.bin", dump)
        self.assertIn("- `binary.bin`: binary", dump)
        self.assertNotIn("bundle.js", dump)

    def test_summary_counts_describe_the_final_text(self) -> None:
        result = build_dump(self.options())
        characters = int(re.search(r"Total characters: (\d+)", result.text).group(1))  # type: ignore[union-attr]
        tokens = int(re.search(r"Estimated tokens: (\d+)", result.text).group(1))  # type: ignore[union-attr]
        self.assertEqual(characters, len(result.text))
        self.assertEqual(tokens, estimate_tokens(result.text))
        self.assertEqual(result.tokens, tokens)
        self.assertEqual(result.characters, characters)

    def test_tree_only_skips_file_contents(self) -> None:
        dump = generate_dump(self.root, self.ignore_filter, tree_only=True)
        self.assertIn("main.py", dump)
        self.assertNotIn("## File Contents", dump)
        self.assertNotIn("### File:", dump)
        self.assertIn("## Summary", dump)

    def test_nested_fence_in_markdown_file(self) -> None:
        self.write("README.md", "Use:\n```bash\nls\n```\n")
        dump = build_dump(self.options()).text
        self.assertIn("````markdown\nUse:\n```bash\nls\n```\n````", dump)

    def test_output_file_is_not_dumped_into_itself(self) -> None:
        output = self.root / "reports" / "dump.md"
        first = build_dump(self.options(output_path=output))
        output.parent.mkdir()
        output.write_text(first.text, encoding="utf-8")
        second = build_dump(self.options(output_path=output))
        self.assertNotIn("dump.md", second.text)

    def test_max_file_size_skips_large_files(self) -> None:
        self.write("big.txt", "x" * 2048)
        result = build_dump(self.options(max_file_size=1024))
        self.assertIn(("big.txt", SKIP_TOO_LARGE), result.skipped)
        self.assertNotIn("### File: big.txt", result.text)
        self.assertIn("big.txt", result.text)  # still visible in the tree

    def test_fit_budget_drops_largest_files(self) -> None:
        self.write("huge.py", "y = 1\n" * 2000)
        unbounded = build_dump(self.options())
        self.assertGreater(unbounded.tokens, 1000)
        result = build_dump(self.options(max_tokens=1000, fit_budget=True))
        self.assertLessEqual(result.tokens, 1000)
        self.assertIn(("huge.py", SKIP_BUDGET), result.skipped)
        self.assertIn("### File: src/main.py", result.text)

    def test_budget_is_only_a_warning_without_fit(self) -> None:
        self.write("huge.py", "y = 1\n" * 2000)
        result = build_dump(self.options(max_tokens=10))
        self.assertIn("### File: huge.py", result.text)

    def test_largest_files_table(self) -> None:
        self.write("huge.py", "y = 1\n" * 50)
        text = build_dump(self.options(top_files=1)).text
        self.assertRegex(
            text,
            r"### Largest Files\n\n\| File \| Tokens \|\n\| --- \| ---: \|\n"
            r"\| `huge.py` \| \d+ \|$|\n\n",
        )

    def test_include_and_exclude_options(self) -> None:
        result = build_dump(self.options(include=["*.py"], exclude=["src/"]))
        self.assertEqual(result.files, [])
        result = build_dump(self.options(include=["*.json"]))
        self.assertEqual([entry.path for entry in result.files], ["data.json"])

    def test_secret_findings_reported_for_included_files_only(self) -> None:
        self.write("config.py", 'API_KEY = "abcd1234efgh5678ijkl"\n')
        self.write("ignored/.gitignore", "*\n")
        result = build_dump(self.options())
        self.assertEqual(
            [(item.path, item.line) for item in result.secret_findings], [("config.py", 1)]
        )
        result = build_dump(self.options(scan_secrets=False))
        self.assertEqual(result.secret_findings, [])

    def test_secret_files_are_left_out(self) -> None:
        self.write(".env", "TOKEN=secret")
        self.write(".env.example", "TOKEN=")
        text = build_dump(self.options()).text
        self.assertNotIn("TOKEN=secret", text)
        self.assertIn("### File: .env.example", text)

    def test_xml_and_json_formats(self) -> None:
        xml_text = build_dump(self.options(output_format="xml")).text
        self.assertTrue(xml_text.startswith("<?xml"))
        payload = json.loads(build_dump(self.options(output_format="json")).text)
        self.assertEqual(payload["summary"]["files"], 2)
        self.assertEqual(
            payload["summary"]["characters"],
            len(build_dump(self.options(output_format="json")).text),
        )

    def test_invalid_settings_raise_value_error(self) -> None:
        with self.assertRaises(ValueError):
            build_dump(self.options(output_format="yaml"))
        with self.assertRaises(ValueError):
            build_dump(DumpOptions(root=self.root, git_mode="sometimes"))
        with self.assertRaises(ValueError):
            build_dump(self.options(tokenizer="words"))
        with self.assertRaises(ValueError):
            build_dump(DumpOptions(root=self.root / "missing"))

    def test_git_modes_outside_a_repository(self) -> None:
        with mock.patch("git_context_dump.gitutil.is_work_tree", return_value=False):
            with self.assertRaises(GitError):
                build_dump(DumpOptions(root=self.root, git_mode="on"))
            with self.assertRaises(GitError):
                build_dump(DumpOptions(root=self.root, changes="diff"))
            result = build_dump(DumpOptions(root=self.root))
        self.assertFalse(result.used_git)

    @unittest.skipIf(importlib.util.find_spec("tiktoken") is not None, "tiktoken installed")
    def test_tiktoken_without_extra_gives_helpful_error(self) -> None:
        with self.assertRaisesRegex(ValueError, "git-context-dump\\[tiktoken\\]"):
            build_dump(self.options(tokenizer="tiktoken"))


if __name__ == "__main__":
    unittest.main()
