"""Copy text to the system clipboard using the platform's own tools."""

from __future__ import annotations

import shutil
import subprocess
import sys


class ClipboardError(RuntimeError):
    """Raised when no clipboard tool is available or copying fails."""


def _commands() -> list[tuple[list[str], str]]:
    """Candidate commands with the encoding each one expects on stdin."""
    if sys.platform == "win32":
        # clip.exe reads UTF-16LE correctly when the input starts with a BOM.
        return [(["clip"], "utf-16")]
    if sys.platform == "darwin":
        return [(["pbcopy"], "utf-8")]
    return [
        (["wl-copy"], "utf-8"),
        (["xclip", "-selection", "clipboard"], "utf-8"),
        (["xsel", "--clipboard", "--input"], "utf-8"),
    ]


def copy_to_clipboard(text: str) -> None:
    """Place *text* on the clipboard or raise :class:`ClipboardError`."""
    for command, encoding in _commands():
        if shutil.which(command[0]) is None:
            continue
        try:
            subprocess.run(command, input=text.encode(encoding), check=True, timeout=30)
        except (OSError, subprocess.SubprocessError) as error:
            raise ClipboardError(f"{command[0]} failed: {error}") from error
        return
    raise ClipboardError("no clipboard tool found (install wl-clipboard, xclip or xsel on Linux)")
