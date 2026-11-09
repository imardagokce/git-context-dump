"""Tests for Markdown dump generation and token estimation."""

from pathlib import Path
import re
import tempfile
import unittest

from git_context_dump.dumper import (
    estimate_tokens,
    generate_dump,
    get_language_tag,
)
from git_context_dump.ignore import IgnoreFilter


class DumperTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary_directory = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary_directory.name)
        (self.root / "src").mkdir()
        (self.root / "src" / "main.py").write_text(
            "print('hello')  \n\n\n", encoding="utf-8"
        )
        (self.root / "data.json").write_text('{"ok": true}\n', encoding="utf-8")
        (self.root / "binary.bin").write_bytes(b"\xff\xfe\x00")
        (self.root / "dist").mkdir()
        (self.root / "dist" / "bundle.js").write_text("ignored", encoding="utf-8")
        self.ignore_filter = IgnoreFilter(self.root)

    def tearDown(self) -> None:
        self.temporary_directory.cleanup()

    def test_estimate_tokens_uses_four_characters_per_token(self) -> None:
        self.assertEqual(estimate_tokens(""), 0)
        self.assertEqual(estimate_tokens("abcd"), 1)
        self.assertEqual(estimate_tokens("abcdefghij"), 3)

    def test_extension_to_language_mapping(self) -> None:
        expected = {
            "script.py": "python",
            "module.rs": "rust",
            "app.js": "javascript",
            "data.json": "json",
            "settings.toml": "toml",
            "README.md": "markdown",
            "unknown.xyz": "",
            "NO_EXTENSION": "",
        }
        for filename, language in expected.items():
            with self.subTest(filename=filename):
                self.assertEqual(get_language_tag(Path(filename)), language)

    def test_generate_dump_contains_metadata_tree_contents_and_summary(self) -> None:
        dump = generate_dump(self.root, self.ignore_filter)
        self.assertIn("# Git Context Dump", dump)
        self.assertRegex(dump, r"- Generated: \d{4}-\d{2}-\d{2}T[^\n]+\+00:00")
        self.assertIn(f"- Target directory: {self.root.resolve()}", dump)
        self.assertIn("## Directory Structure", dump)
        self.assertIn("main.py", dump)
        self.assertIn("## File Contents", dump)
        self.assertIn("### File: src/main.py\n\n```python\nprint('hello')\n\n```", dump)
        self.assertIn('### File: data.json\n\n```json\n{"ok": true}\n```', dump)
        self.assertNotIn("binary.bin", dump.split("## File Contents", 1)[1])
        self.assertNotIn("bundle.js", dump)
        self.assertRegex(dump, r"## Summary\n\n- Total characters: \d+\n- Estimated tokens: \d+$")
        summary = re.search(r"- Total characters: (\d+)\n- Estimated tokens: (\d+)$", dump)
        self.assertIsNotNone(summary)

    def test_tree_only_skips_file_contents(self) -> None:
        dump = generate_dump(self.root, self.ignore_filter, tree_only=True)
        self.assertIn("## Directory Structure", dump)
        self.assertIn("main.py", dump)
        self.assertNotIn("## File Contents", dump)
        self.assertNotIn("### File:", dump)
        self.assertIn("## Summary", dump)


if __name__ == "__main__":
    unittest.main()
