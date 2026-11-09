"""Render a Markdown context dump and estimate its token usage."""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

from git_context_dump.ignore import IgnoreFilter
from git_context_dump.parser import (
    build_tree,
    clean_whitespace,
    collect_files,
    read_file_content,
)


_LANGUAGE_TAGS: dict[str, str] = {
    ".c": "c",
    ".cc": "cpp",
    ".cpp": "cpp",
    ".cs": "csharp",
    ".css": "css",
    ".go": "go",
    ".html": "html",
    ".java": "java",
    ".js": "javascript",
    ".json": "json",
    ".jsx": "jsx",
    ".kt": "kotlin",
    ".md": "markdown",
    ".php": "php",
    ".py": "python",
    ".rb": "ruby",
    ".rs": "rust",
    ".sh": "bash",
    ".sql": "sql",
    ".swift": "swift",
    ".toml": "toml",
    ".ts": "typescript",
    ".tsx": "tsx",
    ".xml": "xml",
    ".yaml": "yaml",
    ".yml": "yaml",
}


def estimate_tokens(text: str) -> int:
    """Estimate tokens using an average of roughly four characters per token."""
    return (len(text) + 3) // 4


def get_language_tag(path: Path) -> str:
    """Return the Markdown code fence identifier for a file extension."""
    return _LANGUAGE_TAGS.get(path.suffix.lower(), "")


def generate_dump(
    root_dir: Path, ignore_filter: IgnoreFilter, tree_only: bool = False
) -> str:
    """Generate a Markdown repository dump with metadata and a usage summary."""
    root = root_dir.resolve()
    timestamp = datetime.now(timezone.utc).isoformat(timespec="seconds")
    sections = [
        "# Git Context Dump",
        "",
        f"- Generated: {timestamp}",
        f"- Target directory: {root}",
        "",
        "## Directory Structure",
        "",
        build_tree(root, ignore_filter),
    ]

    if not tree_only:
        sections.extend(("", "## File Contents"))
        for relative_path in collect_files(root, ignore_filter):
            content = read_file_content(root / relative_path)
            if content is None:
                continue
            cleaned_content = clean_whitespace(content)
            language = get_language_tag(relative_path)
            sections.extend(
                (
                    "",
                    f"### File: {relative_path.as_posix()}",
                    "",
                    f"```{language}",
                    cleaned_content,
                    "```",
                )
            )

    main_content = "\n".join(sections)
    summary = (
        "## Summary\n\n"
        f"- Total characters: {len(main_content)}\n"
        f"- Estimated tokens: {estimate_tokens(main_content)}"
    )
    return f"{main_content}\n\n{summary}"
