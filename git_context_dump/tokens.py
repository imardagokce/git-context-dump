"""Token counting: a dependency-free heuristic, or tiktoken when installed."""

from __future__ import annotations

from collections.abc import Callable

TOKENIZERS = ("heuristic", "tiktoken")

TokenCounter = Callable[[str], int]


def estimate_tokens(text: str) -> int:
    """Estimate tokens using an average of roughly four characters per token."""
    return (len(text) + 3) // 4


def get_token_counter(name: str = "heuristic") -> TokenCounter:
    """Return a token counting function for the named tokenizer."""
    if name == "heuristic":
        return estimate_tokens
    if name == "tiktoken":
        try:
            import tiktoken
        except ImportError as error:
            raise ValueError(
                "the tiktoken tokenizer needs the optional extra: "
                "pip install 'git-context-dump[tiktoken]'"
            ) from error
        encoding = tiktoken.get_encoding("cl100k_base")

        def count(text: str) -> int:
            return len(encoding.encode(text, disallowed_special=()))

        return count
    raise ValueError(f"unknown tokenizer: {name} (choose from {', '.join(TOKENIZERS)})")
