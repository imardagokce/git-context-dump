"""Tests for the Markdown, XML and JSON renderers."""

from __future__ import annotations

import json
import re
import unittest
import xml.etree.ElementTree as ElementTree
from pathlib import Path

from git_context_dump.gitutil import RepoInfo
from git_context_dump.render import (
    DumpDocument,
    FileEntry,
    clean_whitespace,
    fence_for,
    get_language_tag,
    render_json,
    render_markdown,
    render_xml,
)

NESTED = "Intro\n```bash\nls\n```\nA ```` run\nend ]]> \x01"


def make_document(**overrides: object) -> DumpDocument:
    values: dict[str, object] = {
        "generated": "2026-11-24T00:00:00+00:00",
        "repository": "demo",
        "tree": "├── README.md\n└── a.py",
        "tree_paths": 2,
        "tree_only": False,
        "tokenizer_label": "heuristic",
        "repo": RepoInfo(branch="main", commit="abc1234", dirty=True),
        "scope": "changes since v1",
        "files": [
            FileEntry("README.md", "markdown", NESTED, 30),
            FileEntry("a.py", "python", "print(1)", 2),
        ],
        "skipped": [("logo.bin", "binary")],
    }
    values.update(overrides)
    return DumpDocument(**values)  # type: ignore[arg-type]


class HelperTests(unittest.TestCase):
    def test_fence_is_longer_than_any_backtick_run(self) -> None:
        self.assertEqual(fence_for("plain"), "```")
        self.assertEqual(fence_for("```"), "````")
        self.assertEqual(fence_for(NESTED), "`````")

    def test_language_tags(self) -> None:
        expected = {
            "script.py": "python",
            "module.rs": "rust",
            "app.js": "javascript",
            "data.json": "json",
            "settings.toml": "toml",
            "README.md": "markdown",
            "docker/Dockerfile": "dockerfile",
            "Makefile": "makefile",
            "unknown.xyz": "",
            "NO_EXTENSION": "",
        }
        for filename, language in expected.items():
            with self.subTest(filename=filename):
                self.assertEqual(get_language_tag(Path(filename)), language)
                self.assertEqual(get_language_tag(filename), language)

    def test_clean_whitespace_trims_lines_and_collapses_blank_runs(self) -> None:
        self.assertEqual(
            clean_whitespace("first  \n\n\n\nsecond\t\n\nthird   "), "first\n\nsecond\n\nthird"
        )


class MarkdownTests(unittest.TestCase):
    def test_nested_fences_stay_balanced(self) -> None:
        text = render_markdown(make_document(), 100, 25)
        self.assertIn("### File: README.md\n\n`````markdown\n" + NESTED + "\n`````", text)
        # Every opening fence has a matching closing fence of the same length.
        open_fence: str | None = None
        for line in text.splitlines():
            match = re.match(r"^(`{3,})(\S*)$", line)
            if not match:
                continue
            if open_fence is None:
                open_fence = match.group(1)
            elif match.group(1) == open_fence and not match.group(2):
                open_fence = None
        self.assertIsNone(open_fence)

    def test_metadata_summary_and_tables(self) -> None:
        text = render_markdown(make_document(), 1234, 309)
        self.assertIn("- Repository: demo", text)
        self.assertIn("- Branch: main", text)
        self.assertIn("- Commit: abc1234 (with uncommitted changes)", text)
        self.assertIn("- Scope: changes since v1", text)
        self.assertIn("- Files included: 2", text)
        self.assertIn("- Files skipped: 1 (binary: 1)", text)
        self.assertIn("- Total characters: 1234", text)
        self.assertIn("- Estimated tokens: 309 (heuristic)", text)
        self.assertIn("| `README.md` | 30 |\n| `a.py` | 2 |", text)
        self.assertIn("- `logo.bin`: binary", text)

    def test_tree_only_and_empty_tree(self) -> None:
        text = render_markdown(make_document(tree_only=True, tree=""), 1, 1)
        self.assertNotIn("## File Contents", text)
        self.assertIn("(no files)", text)
        self.assertIn("- Files in tree: 2", text)

    def test_skipped_list_is_capped(self) -> None:
        skipped = [(f"f{index}.bin", "binary") for index in range(60)]
        text = render_markdown(make_document(skipped=skipped, max_listed_skips=50), 1, 1)
        self.assertIn("and 10 more", text)


class XmlJsonTests(unittest.TestCase):
    def test_xml_is_well_formed_and_preserves_content(self) -> None:
        text = render_xml(make_document(), 10, 3)
        root = ElementTree.fromstring(text.encode("utf-8"))
        self.assertEqual(root.tag, "context_dump")
        self.assertEqual(root.get("branch"), "main")
        files = root.findall("./files/file")
        self.assertEqual([item.get("path") for item in files], ["README.md", "a.py"])
        content = files[0].text or ""
        self.assertIn("]]>", content)
        self.assertIn("```bash", content)
        self.assertNotIn("\x01", content)
        summary = root.find("summary")
        assert summary is not None
        self.assertEqual(summary.get("tokens"), "3")
        self.assertEqual(root.find("./skipped/file").get("reason"), "binary")  # type: ignore[union-attr]

    def test_xml_tree_only(self) -> None:
        text = render_xml(make_document(tree_only=True, repo=None, scope=None, skipped=[]), 1, 1)
        root = ElementTree.fromstring(text.encode("utf-8"))
        self.assertIsNone(root.find("files"))
        self.assertIsNone(root.get("branch"))

    def test_json_round_trips(self) -> None:
        payload = json.loads(render_json(make_document(), 10, 3))
        self.assertEqual(payload["branch"], "main")
        self.assertEqual(payload["files"][0]["content"], NESTED)
        self.assertEqual(
            payload["summary"],
            {"files": 2, "skipped": 1, "characters": 10, "tokens": 3, "tokenizer": "heuristic"},
        )
        tree_only = json.loads(render_json(make_document(tree_only=True, repo=None), 1, 1))
        self.assertEqual(tree_only["files"], [])
        self.assertIsNone(tree_only["commit"])


if __name__ == "__main__":
    unittest.main()
