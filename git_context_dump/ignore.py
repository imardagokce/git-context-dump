"""Decide which files and directories are left out of a repository context dump.

Patterns follow Git's ``gitignore`` rules: ``*`` and ``?`` never cross ``/``,
``**`` spans directories, a slash anywhere but the end anchors a pattern to the
directory of the file that defines it, a trailing slash matches directories
only, ``!`` re-includes, and a file can never be re-included when one of its
parent directories is excluded.

Rules are applied in increasing order of precedence (the last match wins):

1. built-in defaults (generated files, binaries, lockfiles, secrets)
2. ``core.excludesFile`` (the user's global Git excludes)
3. ``.git/info/exclude``
4. ``.gitignore`` files, from the root down to the file's own directory
5. ``.contextdumpignore`` in the root directory
6. extra exclusions passed in by the caller (``--exclude``)
7. forced exclusions such as the dump's own output file
"""

from __future__ import annotations

import os
import re
import stat
import subprocess
from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

CONTEXTDUMPIGNORE = ".contextdumpignore"

_SECRET_PATTERNS: tuple[str, ...] = (
    ".env",
    ".env.*",
    "!.env.example",
    "!.env.sample",
    "!.env.template",
    "*.pem",
    "*.key",
    "*.p12",
    "*.pfx",
    "*.jks",
    "*.keystore",
    "*.kdbx",
    "id_rsa*",
    "id_dsa*",
    "id_ecdsa*",
    "id_ed25519*",
    "credentials*.json",
    "service-account*.json",
    "secrets.json",
    "secrets.yml",
    "secrets.yaml",
    ".npmrc",
    ".pypirc",
    ".netrc",
    ".htpasswd",
    "*.tfstate",
    "*.tfstate.*",
    ".aws/",
    ".ssh/",
    ".gnupg/",
)

_GENERATED_PATTERNS: tuple[str, ...] = (
    ".git/",
    ".hg/",
    ".svn/",
    ".venv/",
    "venv/",
    "__pycache__/",
    "*.py[cod]",
    ".mypy_cache/",
    ".pytest_cache/",
    ".ruff_cache/",
    ".tox/",
    ".coverage",
    ".coverage.*",
    "htmlcov/",
    "*.egg-info/",
    "node_modules/",
    "dist/",
    "build/",
    ".DS_Store",
    "Thumbs.db",
    "context.md",
    "context.xml",
    "context.json",
)

_BINARY_PATTERNS: tuple[str, ...] = (
    # images
    "*.png",
    "*.jpg",
    "*.jpeg",
    "*.gif",
    "*.bmp",
    "*.webp",
    "*.ico",
    "*.tif",
    "*.tiff",
    "*.psd",
    "*.svg",
    # fonts
    "*.woff",
    "*.woff2",
    "*.ttf",
    "*.otf",
    "*.eot",
    # audio and video
    "*.mp3",
    "*.mp4",
    "*.m4a",
    "*.mov",
    "*.avi",
    "*.mkv",
    "*.wav",
    "*.flac",
    "*.ogg",
    "*.webm",
    # archives and packages
    "*.zip",
    "*.tar",
    "*.gz",
    "*.tgz",
    "*.bz2",
    "*.xz",
    "*.7z",
    "*.rar",
    "*.jar",
    "*.war",
    "*.whl",
    # compiled artefacts
    "*.exe",
    "*.dll",
    "*.so",
    "*.dylib",
    "*.a",
    "*.o",
    "*.obj",
    "*.lib",
    "*.class",
    "*.pyd",
    "*.wasm",
    # documents and databases
    "*.pdf",
    "*.doc",
    "*.docx",
    "*.xls",
    "*.xlsx",
    "*.ppt",
    "*.pptx",
    "*.sqlite",
    "*.sqlite3",
    "*.db",
    # minified bundles and source maps
    "*.min.js",
    "*.min.css",
    "*.map",
    # lockfiles: large, machine-written, rarely useful to a model
    "package-lock.json",
    "npm-shrinkwrap.json",
    "yarn.lock",
    "pnpm-lock.yaml",
    "bun.lockb",
    "poetry.lock",
    "Pipfile.lock",
    "uv.lock",
    "Cargo.lock",
    "composer.lock",
    "Gemfile.lock",
    "go.sum",
)

DEFAULT_PATTERNS: tuple[str, ...] = _GENERATED_PATTERNS + _BINARY_PATTERNS + _SECRET_PATTERNS
# Kept for backwards compatibility with code that imported the private name.
_DEFAULT_PATTERNS = DEFAULT_PATTERNS


@dataclass(frozen=True)
class Rule:
    """One compiled ignore pattern."""

    pattern: str
    regex: re.Pattern[str]
    negated: bool
    directory_only: bool
    anchored: bool
    base: str  # POSIX path of the directory the rule is relative to ("" = root)
    source: str

    def matches(self, relative: str, is_dir: bool) -> bool:
        """Return whether this rule matches *relative* (a root-relative POSIX path)."""
        if self.directory_only and not is_dir:
            return False
        if self.base:
            prefix = self.base + "/"
            if not relative.startswith(prefix):
                return False
            relative = relative[len(prefix) :]
        subject = relative if self.anchored else relative.rsplit("/", 1)[-1]
        return self.regex.fullmatch(subject) is not None


def translate_glob(glob: str) -> str:
    """Translate a gitignore glob into an equivalent regular expression body."""
    parts: list[str] = []
    index = 0
    length = len(glob)
    while index < length:
        char = glob[index]
        if char == "\\" and index + 1 < length:
            parts.append(re.escape(glob[index + 1]))
            index += 2
        elif char == "*":
            if glob.startswith("**", index):
                after = index + 2
                at_segment_start = index == 0 or glob[index - 1] == "/"
                if at_segment_start and after < length and glob[after] == "/":
                    parts.append("(?:.*/)?")  # leading or middle "**/"
                    index = after + 1
                    continue
                if at_segment_start and after == length:
                    parts.append(".*")  # trailing "/**" or a lone "**"
                    index = after
                    continue
                parts.append("[^/]*")  # any other "**" behaves like "*"
                index = after
                continue
            parts.append("[^/]*")
            index += 1
        elif char == "?":
            parts.append("[^/]")
            index += 1
        elif char == "[":
            end = index + 1
            if end < length and glob[end] in "!^":
                end += 1
            if end < length and glob[end] == "]":
                end += 1
            while end < length and glob[end] != "]":
                end += 1
            if end >= length:
                parts.append(re.escape(char))
                index += 1
                continue
            body = glob[index + 1 : end]
            if body[:1] in ("!", "^"):
                body = "^" + body[1:]
            body = body.replace("[", "\\[")
            parts.append(f"(?!/)[{body}]")
            index = end + 1
        else:
            parts.append(re.escape(char))
            index += 1
    return "".join(parts)


def _strip_trailing_spaces(line: str) -> str:
    """Remove trailing spaces unless they are escaped with a backslash."""
    while line.endswith(" ") and not line.endswith("\\ "):
        line = line[:-1]
    return line


def compile_rule(raw_line: str, base: str = "", source: str = "<default>") -> Rule | None:
    """Compile one gitignore line; return ``None`` for blanks and comments."""
    line = _strip_trailing_spaces(raw_line.rstrip("\r\n"))
    if not line or line.startswith("#"):
        return None
    negated = line.startswith("!")
    if negated:
        line = line[1:]
    directory_only = line.endswith("/") and not line.endswith("\\/")
    if directory_only:
        line = line.rstrip("/")
    anchored = "/" in line
    line = line.lstrip("/")
    if not line:
        return None
    try:
        regex = re.compile(translate_glob(line), re.DOTALL)
    except re.error:
        return None
    return Rule(
        pattern=raw_line.strip(),
        regex=regex,
        negated=negated,
        directory_only=directory_only,
        anchored=anchored,
        base=base,
        source=source,
    )


def _compile_lines(lines: Iterable[str], base: str, source: str) -> list[Rule]:
    rules: list[Rule] = []
    for line in lines:
        rule = compile_rule(line, base, source)
        if rule is not None:
            rules.append(rule)
    return rules


def _read_lines(path: Path) -> list[str]:
    try:
        return path.read_text(encoding="utf-8-sig", errors="replace").splitlines()
    except OSError:
        return []


@lru_cache(maxsize=1)
def _global_excludes_file() -> Path | None:
    """Locate the user's global Git excludes file (``core.excludesFile``)."""
    try:
        completed = subprocess.run(
            ["git", "config", "--get", "core.excludesFile"],
            capture_output=True,
            check=False,
            timeout=10,
        )
        configured = completed.stdout.decode("utf-8", "replace").strip()
    except (OSError, subprocess.SubprocessError):
        configured = ""
    if configured:
        return Path(os.path.expanduser(configured))
    config_home = os.environ.get("XDG_CONFIG_HOME") or os.path.join(
        os.path.expanduser("~"), ".config"
    )
    default = Path(config_home) / "git" / "ignore"
    return default if default.is_file() else None


def is_link(path: Path) -> bool:
    """Return whether *path* is a symlink or a Windows junction/reparse point."""
    if path.is_symlink():
        return True
    try:
        attributes = getattr(os.lstat(path), "st_file_attributes", 0)
    except OSError:
        return False
    return bool(attributes & stat.FILE_ATTRIBUTE_REPARSE_POINT)


def is_within(path: Path, root: Path) -> bool:
    """Return whether *path* is *root* or lies inside it."""
    try:
        path.relative_to(root)
    except ValueError:
        return False
    return True


class IgnoreFilter:
    """Apply built-in exclusions, Git ignore files and caller-supplied rules."""

    def __init__(
        self,
        root: Path,
        *,
        use_gitignore: bool = True,
        use_global_excludes: bool = True,
        extra_excludes: Sequence[str] = (),
        includes: Sequence[str] = (),
        default_patterns: Sequence[str] = DEFAULT_PATTERNS,
    ) -> None:
        self.root: Path = root.resolve()
        self.use_gitignore = use_gitignore
        self._defaults = _compile_lines(default_patterns, "", "<default>")
        self._repository_rules: list[Rule] = []
        if use_gitignore:
            if use_global_excludes:
                global_file = _global_excludes_file()
                if global_file is not None:
                    self._repository_rules += _compile_lines(
                        _read_lines(global_file), "", str(global_file)
                    )
            info_exclude = self.root / ".git" / "info" / "exclude"
            self._repository_rules += _compile_lines(
                _read_lines(info_exclude), "", ".git/info/exclude"
            )
        self._contextdump_rules = _compile_lines(
            _read_lines(self.root / CONTEXTDUMPIGNORE), "", CONTEXTDUMPIGNORE
        )
        self._extra_rules = _compile_lines(extra_excludes, "", "--exclude")
        self._include_rules = _compile_lines(includes, "", "--include")
        self._forced: set[str] = set()
        self._gitignore_cache: dict[str, list[Rule]] = {}
        self._link_cache: dict[str, bool] = {}

    # ------------------------------------------------------------------ rules
    def load_gitignore(self) -> None:
        """(Re)load ``.gitignore`` files; kept for backwards compatibility."""
        self._gitignore_cache.clear()

    def add_exclude(self, pattern: str) -> None:
        """Add an extra exclusion with the precedence of ``--exclude``."""
        self._extra_rules += _compile_lines([pattern], "", "--exclude")

    def force_ignore(self, path: Path) -> None:
        """Always exclude *path* (for example the dump's own output file)."""
        absolute = path if path.is_absolute() else Path.cwd() / path
        absolute = Path(os.path.abspath(absolute))
        for candidate in {absolute, absolute.resolve()}:
            if is_within(candidate, self.root):
                self._forced.add(candidate.relative_to(self.root).as_posix())

    def _gitignore_rules(self, directory: str) -> list[Rule]:
        cached = self._gitignore_cache.get(directory)
        if cached is None:
            folder = self.root / directory if directory else self.root
            source = f"{directory}/.gitignore" if directory else ".gitignore"
            cached = _compile_lines(_read_lines(folder / ".gitignore"), directory, source)
            self._gitignore_cache[directory] = cached
        return cached

    def _rules_for(self, relative: str) -> Iterable[Rule]:
        yield from self._defaults
        yield from self._repository_rules
        if self.use_gitignore:
            parts = relative.split("/")[:-1]
            yield from self._gitignore_rules("")
            for depth in range(1, len(parts) + 1):
                yield from self._gitignore_rules("/".join(parts[:depth]))
        yield from self._contextdump_rules
        yield from self._extra_rules

    # --------------------------------------------------------------- queries
    def matches(self, relative: str, is_dir: bool) -> bool:
        """Check *relative* against the rules, assuming its parents are not excluded.

        This is the cheap per-entry check used while walking a tree that is
        already pruned; use :meth:`is_ignored` for an arbitrary path.
        """
        if relative in self._forced:
            return True
        ignored = False
        for rule in self._rules_for(relative):
            if rule.matches(relative, is_dir):
                ignored = not rule.negated
        return ignored

    def wants_file(self, relative: str) -> bool:
        """Return whether a file passes the ``--include`` patterns (if any)."""
        if not self._include_rules:
            return True
        selected = False
        for rule in self._include_rules:
            if rule.matches(relative, False):
                selected = not rule.negated
        return selected

    def relative_path(self, path: Path) -> str | None:
        """Return *path* relative to the root, or ``None`` when it lies outside."""
        absolute = path if path.is_absolute() else self.root / path
        absolute = Path(os.path.abspath(absolute))
        if not is_within(absolute, self.root):
            resolved = absolute.resolve()
            if not is_within(resolved, self.root):
                return None
            absolute = resolved
        return absolute.relative_to(self.root).as_posix()

    def escapes_root(self, path: Path) -> bool:
        """Return whether *path* (e.g. a symlink) resolves outside the root."""
        absolute = path if path.is_absolute() else self.root / path
        try:
            return not is_within(absolute.resolve(), self.root)
        except (OSError, RuntimeError):
            return True

    def is_ignored(self, path: Path) -> bool:
        """Return whether *path* is excluded.

        Paths outside the root, and symlinks that resolve outside it, are
        always excluded. A path is also excluded when any parent directory is.
        """
        relative = self.relative_path(path)
        if relative is None:
            return True
        if relative in ("", "."):
            return False
        absolute = self.root / relative
        parts = relative.split("/")
        for depth in range(1, len(parts) + 1):
            if self._link_escapes("/".join(parts[:depth])):
                return True
        for depth in range(1, len(parts)):
            if self.matches("/".join(parts[:depth]), True):
                return True
        return self.matches(relative, absolute.is_dir())

    def _link_escapes(self, relative: str) -> bool:
        """Return whether *relative* is a link resolving outside the root (cached)."""
        cached = self._link_cache.get(relative)
        if cached is None:
            absolute = self.root / relative
            cached = is_link(absolute) and self.escapes_root(absolute)
            self._link_cache[relative] = cached
        return cached
