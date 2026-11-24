"""Flag lines that look like credentials before a dump leaves the machine.

The scan is a heuristic safety net, not a guarantee: it reports file and line
numbers (never the matched value) so the user can review them.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

_PATTERNS: tuple[tuple[str, re.Pattern[str]], ...] = (
    ("private key", re.compile(r"-----BEGIN (?:[A-Z]+ )*PRIVATE KEY-----")),
    ("AWS access key", re.compile(r"\b(?:AKIA|ASIA)[0-9A-Z]{16}\b")),
    ("GitHub token", re.compile(r"\b(?:gh[pousr]_[A-Za-z0-9]{36,}|github_pat_\w{40,})\b")),
    ("Slack token", re.compile(r"\bxox[abposr]-[A-Za-z0-9-]{10,}\b")),
    ("Stripe live key", re.compile(r"\b[rs]k_live_[A-Za-z0-9]{16,}\b")),
    ("Google API key", re.compile(r"\bAIza[0-9A-Za-z_\-]{35}\b")),
    ("API key", re.compile(r"\bsk-(?:ant-|proj-)?[A-Za-z0-9_\-]{20,}\b")),
    (
        "hard-coded secret",
        re.compile(
            r"""(?ix)
            \b[\w.-]*(?:api[_-]?key|secret|passw(?:or)?d|access[_-]?token|auth[_-]?token)[\w.-]*
            ["']?\s*[:=]\s*
            ["']([^"'\s$<>{}]{12,})["']
            """
        ),
    ),
)


@dataclass(frozen=True)
class SecretFinding:
    """A line that looks like it contains a credential."""

    path: str
    line: int
    kind: str

    def __str__(self) -> str:
        return f"{self.path}:{self.line}: possible {self.kind}"


def scan_text(path: str, text: str) -> list[SecretFinding]:
    """Return findings for *text*, at most one per line."""
    findings: list[SecretFinding] = []
    for number, line in enumerate(text.splitlines(), start=1):
        for kind, pattern in _PATTERNS:
            if pattern.search(line):
                findings.append(SecretFinding(path, number, kind))
                break
    return findings
