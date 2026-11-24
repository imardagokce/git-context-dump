"""Render a collected dump as Markdown, XML or JSON."""

from __future__ import annotations

import json
import re
from collections import Counter
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import PurePath, PurePosixPath
from xml.sax.saxutils import quoteattr

from git_context_dump.gitutil import RepoInfo

FORMATS = ("markdown", "xml", "json")
FORMAT_EXTENSIONS = {"markdown": "md", "xml": "xml", "json": "json"}

_LANGUAGE_TAGS: dict[str, str] = {
    ".bat": "batch",
    ".c": "c",
    ".cc": "cpp",
    ".cfg": "ini",
    ".clj": "clojure",
    ".cpp": "cpp",
    ".cs": "csharp",
    ".css": "css",
    ".dart": "dart",
    ".ex": "elixir",
    ".exs": "elixir",
    ".go": "go",
    ".gradle": "groovy",
    ".graphql": "graphql",
    ".h": "c",
    ".hpp": "cpp",
    ".hs": "haskell",
    ".html": "html",
    ".ini": "ini",
    ".java": "java",
    ".js": "javascript",
    ".json": "json",
    ".jsx": "jsx",
    ".kt": "kotlin",
    ".kts": "kotlin",
    ".less": "less",
    ".lua": "lua",
    ".m": "objectivec",
    ".md": "markdown",
    ".mjs": "javascript",
    ".cjs": "javascript",
    ".php": "php",
    ".pl": "perl",
    ".proto": "protobuf",
    ".ps1": "powershell",
    ".py": "python",
    ".r": "r",
    ".rb": "ruby",
    ".rs": "rust",
    ".scala": "scala",
    ".scss": "scss",
    ".sh": "bash",
    ".sql": "sql",
    ".svelte": "svelte",
    ".swift": "swift",
    ".tf": "hcl",
    ".toml": "toml",
    ".ts": "typescript",
    ".tsx": "tsx",
    ".vue": "vue",
    ".xml": "xml",
    ".yaml": "yaml",
    ".yml": "yaml",
    ".zig": "zig",
    ".zsh": "zsh",
}

_FILENAME_TAGS: dict[str, str] = {
    "dockerfile": "dockerfile",
    "makefile": "makefile",
    "cmakelists.txt": "cmake",
    "gemfile": "ruby",
    "rakefile": "ruby",
    "jenkinsfile": "groovy",
}

_BACKTICK_RUN = re.compile(r"`+")
_INVALID_XML_CHARS = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f￾￿]")


def get_language_tag(path: PurePath | str) -> str:
    """Return the Markdown code fence identifier for a file name or extension."""
    pure = PurePosixPath(str(path).replace("\\", "/"))
    by_name = _FILENAME_TAGS.get(pure.name.lower())
    if by_name:
        return by_name
    return _LANGUAGE_TAGS.get(pure.suffix.lower(), "")


def clean_whitespace(content: str) -> str:
    """Trim line endings and reduce runs of blank lines to at most one."""
    cleaned_lines: list[str] = []
    blank_run = 0
    for line in content.splitlines():
        trimmed = line.rstrip()
        if not trimmed:
            blank_run += 1
            if blank_run <= 1:
                cleaned_lines.append("")
        else:
            blank_run = 0
            cleaned_lines.append(trimmed)
    return "\n".join(cleaned_lines)


def fence_for(content: str) -> str:
    """Return a backtick fence longer than any backtick run inside *content*."""
    longest = max((len(run) for run in _BACKTICK_RUN.findall(content)), default=0)
    return "`" * max(3, longest + 1)


@dataclass
class FileEntry:
    """One file whose contents are part of the dump."""

    path: str
    language: str
    content: str
    tokens: int


@dataclass
class DumpDocument:
    """Everything a renderer needs, independent of the output format."""

    generated: str
    repository: str
    tree: str
    tree_paths: int
    tree_only: bool
    tokenizer_label: str
    repo: RepoInfo | None = None
    scope: str | None = None
    files: list[FileEntry] = field(default_factory=list)
    skipped: list[tuple[str, str]] = field(default_factory=list)
    top_files: int = 10
    max_listed_skips: int = 50


def _skip_breakdown(skipped: list[tuple[str, str]]) -> str:
    counts = Counter(reason for _, reason in skipped)
    return ", ".join(f"{reason}: {count}" for reason, count in sorted(counts.items()))


def _largest(document: DumpDocument) -> list[FileEntry]:
    ranked = sorted(document.files, key=lambda entry: (-entry.tokens, entry.path))
    return ranked[: document.top_files]


# ------------------------------------------------------------------ markdown
def render_markdown(document: DumpDocument, characters: int, tokens: int) -> str:
    """Render *document* as Markdown with collision-free code fences."""
    lines = ["# Git Context Dump", "", f"- Generated: {document.generated}"]
    lines.append(f"- Repository: {document.repository}")
    if document.repo is not None:
        if document.repo.branch:
            lines.append(f"- Branch: {document.repo.branch}")
        if document.repo.commit:
            dirty = " (with uncommitted changes)" if document.repo.dirty else ""
            lines.append(f"- Commit: {document.repo.commit}{dirty}")
    if document.scope:
        lines.append(f"- Scope: {document.scope}")

    tree = document.tree or "(no files)"
    tree_fence = fence_for(tree)
    lines += ["", "## Directory Structure", "", f"{tree_fence}text", tree, tree_fence]

    if not document.tree_only:
        lines += ["", "## File Contents"]
        for entry in document.files:
            fence = fence_for(entry.content)
            lines += [
                "",
                f"### File: {entry.path}",
                "",
                f"{fence}{entry.language}",
                entry.content,
                fence,
            ]

    lines += ["", "## Summary", ""]
    if document.tree_only:
        lines.append(f"- Files in tree: {document.tree_paths}")
    else:
        lines.append(f"- Files included: {len(document.files)}")
    if document.skipped:
        lines.append(
            f"- Files skipped: {len(document.skipped)} ({_skip_breakdown(document.skipped)})"
        )
    lines.append(f"- Total characters: {characters}")
    lines.append(f"- Estimated tokens: {tokens} ({document.tokenizer_label})")

    largest = _largest(document)
    if largest:
        lines += ["", "### Largest Files", "", "| File | Tokens |", "| --- | ---: |"]
        lines += [f"| `{entry.path}` | {entry.tokens} |" for entry in largest]
    if document.skipped:
        lines += ["", "### Skipped Files", ""]
        listed = document.skipped[: document.max_listed_skips]
        lines += [f"- `{path}`: {reason}" for path, reason in listed]
        remaining = len(document.skipped) - len(listed)
        if remaining > 0:
            lines.append(f"- … and {remaining} more")
    return "\n".join(lines)


# ----------------------------------------------------------------------- xml
def _cdata(text: str) -> str:
    safe = _INVALID_XML_CHARS.sub("�", text)
    return "<![CDATA[" + safe.replace("]]>", "]]]]><![CDATA[>") + "]]>"


def _attr(value: object) -> str:
    return quoteattr(_INVALID_XML_CHARS.sub("�", str(value)))


def render_xml(document: DumpDocument, characters: int, tokens: int) -> str:
    """Render *document* as XML; file contents are wrapped in CDATA sections."""
    attributes = {"generated": document.generated, "repository": document.repository}
    if document.repo is not None:
        if document.repo.branch:
            attributes["branch"] = document.repo.branch
        if document.repo.commit:
            attributes["commit"] = document.repo.commit
            attributes["dirty"] = str(document.repo.dirty).lower()
    if document.scope:
        attributes["scope"] = document.scope
    opening = " ".join(f"{key}={_attr(value)}" for key, value in attributes.items())
    lines = [
        '<?xml version="1.0" encoding="UTF-8"?>',
        f"<context_dump {opening}>",
        f"<directory_structure>{_cdata(document.tree)}</directory_structure>",
    ]
    if not document.tree_only:
        lines.append("<files>")
        for entry in document.files:
            lines.append(
                f"<file path={_attr(entry.path)} language={_attr(entry.language)} "
                f"tokens={_attr(entry.tokens)}>{_cdata(chr(10) + entry.content + chr(10))}</file>"
            )
        lines.append("</files>")
    if document.skipped:
        lines.append("<skipped>")
        lines += [
            f"<file path={_attr(path)} reason={_attr(reason)}/>"
            for path, reason in document.skipped
        ]
        lines.append("</skipped>")
    included = document.tree_paths if document.tree_only else len(document.files)
    lines.append(
        f"<summary files={_attr(included)} skipped={_attr(len(document.skipped))} "
        f"characters={_attr(characters)} tokens={_attr(tokens)} "
        f"tokenizer={_attr(document.tokenizer_label)}/>"
    )
    lines.append("</context_dump>")
    return "\n".join(lines)


# ---------------------------------------------------------------------- json
def render_json(document: DumpDocument, characters: int, tokens: int) -> str:
    """Render *document* as a JSON object."""
    payload: dict[str, object] = {
        "generated": document.generated,
        "repository": document.repository,
        "branch": document.repo.branch if document.repo else None,
        "commit": document.repo.commit if document.repo else None,
        "dirty": document.repo.dirty if document.repo else None,
        "scope": document.scope,
        "tree": document.tree,
        "files": []
        if document.tree_only
        else [
            {
                "path": entry.path,
                "language": entry.language,
                "tokens": entry.tokens,
                "content": entry.content,
            }
            for entry in document.files
        ],
        "skipped": [{"path": path, "reason": reason} for path, reason in document.skipped],
        "summary": {
            "files": document.tree_paths if document.tree_only else len(document.files),
            "skipped": len(document.skipped),
            "characters": characters,
            "tokens": tokens,
            "tokenizer": document.tokenizer_label,
        },
    }
    return json.dumps(payload, ensure_ascii=False, indent=2)


RENDERERS: dict[str, Callable[[DumpDocument, int, int], str]] = {
    "markdown": render_markdown,
    "xml": render_xml,
    "json": render_json,
}
