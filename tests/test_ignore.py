"""Tests for repository ignore rules."""

from __future__ import annotations

import unittest
from pathlib import Path
from unittest import mock

from git_context_dump.ignore import IgnoreFilter, compile_rule, translate_glob
from tests.helpers import TempDirTestCase


class IgnoreFilterTests(TempDirTestCase):
    def setUp(self) -> None:
        super().setUp()
        self.filter = IgnoreFilter(self.root)

    def gitignore(self, text: str, relative: str = ".gitignore") -> IgnoreFilter:
        self.write(relative, text)
        return IgnoreFilter(self.root)

    def assertIgnored(self, filter_: IgnoreFilter, *paths: str) -> None:
        for name in paths:
            with self.subTest(ignored=name):
                self.assertTrue(filter_.is_ignored(Path(name)), name)

    def assertKept(self, filter_: IgnoreFilter, *paths: str) -> None:
        for name in paths:
            with self.subTest(kept=name):
                self.assertFalse(filter_.is_ignored(Path(name)), name)

    # ------------------------------------------------------------- defaults
    def test_default_file_and_directory_exclusions(self) -> None:
        self.assertIgnored(
            self.filter,
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

    def test_expanded_binary_and_lockfile_defaults(self) -> None:
        self.assertIgnored(
            self.filter,
            "a.gif",
            "a.jpeg",
            "a.webp",
            "a.ico",
            "icons/a.svg",
            "fonts/a.woff2",
            "a.mp4",
            "a.gz",
            "lib/a.jar",
            "a.dll",
            "a.so",
            "package-lock.json",
            "web/yarn.lock",
            "poetry.lock",
            "static/app.min.js",
            "app.js.map",
        )

    def test_secret_files_are_excluded_by_default(self) -> None:
        self.assertIgnored(
            self.filter,
            ".env",
            ".env.local",
            "config/.env.production",
            "id_rsa",
            "keys/id_ed25519.pub",
            "server.pem",
            "tls/server.key",
            "cert.p12",
            "credentials.json",
            ".npmrc",
            ".netrc",
            "terraform.tfstate",
            ".ssh/config",
            ".aws/credentials",
        )

    def test_secret_templates_are_kept(self) -> None:
        self.assertKept(self.filter, ".env.example", "app/.env.sample", ".env.template")

    def test_unmatched_paths_are_kept(self) -> None:
        self.assertKept(
            self.filter, "src/main.py", "README.md", "nested/data.json", "docs/environment.md"
        )

    def test_contextdumpignore_can_reinclude_a_default(self) -> None:
        self.write(".contextdumpignore", "!yarn.lock\n*.generated.ts\n")
        filter_ = IgnoreFilter(self.root)
        self.assertKept(filter_, "yarn.lock")
        self.assertIgnored(filter_, "src/api.generated.ts")

    def test_custom_default_patterns(self) -> None:
        filter_ = IgnoreFilter(self.root, default_patterns=())
        self.assertKept(filter_, "image.png", ".env")

    # ------------------------------------------------------------ gitignore
    def test_root_gitignore_parses_comments_blanks_and_patterns(self) -> None:
        filter_ = self.gitignore("# generated files\n\n*.log\n/secret.txt\n/cache/\n")
        self.assertIgnored(filter_, "app.log", "nested/app.log", "secret.txt", "cache/item.bin")
        self.assertKept(filter_, "nested/secret.txt", "nested/cache/item.bin", "# generated files")

    def test_directory_rules_allow_early_pruning(self) -> None:
        (self.root / "generated").mkdir()
        filter_ = self.gitignore("/generated/\n")
        self.assertIgnored(filter_, "generated", "generated/deep/file.txt")
        self.assertKept(filter_, "other/generated/file.txt")

    def test_directory_only_rule_does_not_match_files(self) -> None:
        self.write("logs", "a file named logs")
        filter_ = self.gitignore("logs/\n")
        self.assertKept(filter_, "logs")
        self.assertIgnored(filter_, "sub/logs/x.txt")

    def test_single_star_does_not_cross_directories(self) -> None:
        filter_ = self.gitignore("*.tmp\nlogs/*/private/\n")
        self.assertIgnored(filter_, "nested/file.tmp", "logs/2026/private/secret.txt")
        self.assertKept(filter_, "logs/2026/public/secret.txt", "logs/a/b/private/s.txt")

    def test_double_star_patterns(self) -> None:
        filter_ = self.gitignore("**/foo.txt\na/**/b\nout/**\n**/tmp/**\n")
        self.assertIgnored(
            filter_,
            "foo.txt",
            "x/y/foo.txt",
            "a/b",
            "a/x/y/b",
            "out/file.txt",
            "out/deep/file.txt",
            "tmp/x",
            "src/tmp/x/y",
        )
        self.assertKept(filter_, "out", "x/a/b", "foo.txt.bak")

    def test_question_mark_and_character_classes(self) -> None:
        filter_ = self.gitignore("file?.txt\nlog[0-9].txt\nkeep[!a].md\n")
        self.assertIgnored(filter_, "file1.txt", "log7.txt", "keepb.md")
        self.assertKept(filter_, "file12.txt", "logx.txt", "keepa.md", "file/.txt")

    def test_escaped_hash_bang_and_trailing_spaces(self) -> None:
        filter_ = self.gitignore("\\#notcomment\n\\!bang\ntrailing.txt   \nspace\\ \n")
        self.assertIgnored(filter_, "#notcomment", "!bang", "trailing.txt")
        self.assertKept(filter_, "space", "notcomment", "bang")
        # Windows strips trailing spaces from paths, so check the rule directly.
        self.assertTrue(filter_.matches("space ", False))

    def test_negation_reincludes_a_matching_file(self) -> None:
        filter_ = self.gitignore("*.log\n!important.log\n")
        self.assertIgnored(filter_, "other.log")
        self.assertKept(filter_, "important.log")

    def test_file_inside_excluded_directory_cannot_be_reincluded(self) -> None:
        filter_ = self.gitignore("out/\n!out/keep.txt\n")
        self.assertIgnored(filter_, "out/keep.txt")

    def test_nested_gitignore_is_scoped_to_its_directory(self) -> None:
        self.write("sub/.gitignore", "secret.txt\n/local.cfg\n!keep.log\n")
        filter_ = self.gitignore("*.log\n")
        self.assertIgnored(filter_, "sub/secret.txt", "sub/deeper/secret.txt", "sub/local.cfg")
        self.assertKept(filter_, "secret.txt", "sub/deeper/local.cfg", "sub/keep.log")
        self.assertIgnored(filter_, "other/keep.log")

    def test_git_info_exclude_is_applied(self) -> None:
        self.write(".git/info/exclude", "*.scratch\n")
        filter_ = IgnoreFilter(self.root)
        self.assertIgnored(filter_, "notes.scratch")

    def test_global_excludes_file_is_applied(self) -> None:
        global_file = self.write("global-ignore", "*.orig\n")
        with mock.patch("git_context_dump.ignore._global_excludes_file", return_value=global_file):
            filter_ = IgnoreFilter(self.root)
        self.assertIgnored(filter_, "merge.orig")

    def test_gitignore_can_be_disabled(self) -> None:
        self.write(".git/info/exclude", "*.scratch\n")
        self.write(".gitignore", "*.log\n")
        filter_ = IgnoreFilter(self.root, use_gitignore=False)
        self.assertKept(filter_, "app.log", "notes.scratch")
        self.assertIgnored(filter_, "image.png")

    # -------------------------------------------------------- caller rules
    def test_extra_excludes_and_add_exclude(self) -> None:
        filter_ = IgnoreFilter(self.root, extra_excludes=["docs/"])
        filter_.add_exclude("*.csv")
        self.assertIgnored(filter_, "docs/index.md", "data/table.csv")
        self.assertKept(filter_, "src/docs.py")

    def test_includes_select_files(self) -> None:
        filter_ = IgnoreFilter(self.root, includes=["*.py", "docs/**"])
        self.assertTrue(filter_.wants_file("src/app.py"))
        self.assertTrue(filter_.wants_file("docs/guide/intro.md"))
        self.assertFalse(filter_.wants_file("README.md"))
        self.assertTrue(self.filter.wants_file("README.md"))

    def test_force_ignore_relative_and_absolute_paths(self) -> None:
        self.filter.force_ignore(self.root / "out" / "dump.md")
        self.assertIgnored(self.filter, "out/dump.md")
        self.assertKept(self.filter, "dump.md")
        self.filter.force_ignore(Path("/elsewhere/outside.md"))  # outside root: no effect
        self.assertKept(self.filter, "outside.md")

    # ---------------------------------------------------- root boundaries
    def test_paths_outside_root_are_ignored(self) -> None:
        self.assertTrue(self.filter.is_ignored(self.root.parent / "other.txt"))
        self.assertTrue(self.filter.is_ignored(Path("../escape.txt")))
        self.assertFalse(self.filter.is_ignored(self.root))

    def test_symlink_resolving_outside_root_is_ignored(self) -> None:
        outside_dir = self.root.parent / f"{self.root.name}-outside"
        outside_dir.mkdir()
        self.addCleanup(lambda: __import__("shutil").rmtree(outside_dir, ignore_errors=True))
        secret = outside_dir / "secret.txt"
        secret.write_text("TOPSECRET", encoding="utf-8")
        self.symlink_or_skip(self.root / "link.txt", secret)
        self.assertTrue(self.filter.is_ignored(self.root / "link.txt"))


class TranslateGlobTests(unittest.TestCase):
    def test_translation_examples(self) -> None:
        self.assertEqual(translate_glob("*.py"), "[^/]*\\.py")
        self.assertEqual(translate_glob("**/x"), "(?:.*/)?x")
        self.assertEqual(translate_glob("a/**"), "a/.*")

    def test_unterminated_class_is_literal(self) -> None:
        rule = compile_rule("file[.txt")
        assert rule is not None
        self.assertTrue(rule.matches("file[.txt", False))

    def test_blank_comment_and_bare_slash_lines_are_skipped(self) -> None:
        for line in ("", "   ", "# comment", "/", "!"):
            with self.subTest(line=line):
                self.assertIsNone(compile_rule(line))


if __name__ == "__main__":
    unittest.main()
