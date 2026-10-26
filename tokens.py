"""Token counting that works with no network.

tiktoken normally downloads its encoding file on first use. We ship the
o200k_base file in data/tiktoken/ (see the README there) and point
TIKTOKEN_CACHE_DIR at it right before loading. If anything goes wrong, we fall
back to a rule of thumb and label it as such.
"""

import math
import os
import re
from pathlib import Path

import pricing

TIKTOKEN_DIR = Path(__file__).parent / "data" / "tiktoken"
OPENAI_LABEL = "OpenAI's public tokenizer (GPT-4o / GPT-5 era)"  # spaces, so narrow tables break between words
CLAUDE_ESTIMATE_LABEL = "estimate: Claude's tokenizer isn't public"
FALLBACK_LABEL = "rough estimate (tokenizer unavailable)"

_encoding = None  # None = not loaded yet, False = unavailable
load_error = ""


def _get_encoding():
    global _encoding, load_error
    if _encoding is None:
        os.environ["TIKTOKEN_CACHE_DIR"] = str(TIKTOKEN_DIR)
        try:
            import tiktoken

            _encoding = tiktoken.get_encoding("o200k_base")
            load_error = ""
        except Exception as exc:  # package missing, bundled file missing/corrupt, no network
            _encoding = False
            load_error = f"{type(exc).__name__}: {exc}"
    return _encoding or None


def encoding_available() -> bool:
    return _get_encoding() is not None


def word_count(text: str) -> int:
    return len(text.split())


def fallback_count(text: str) -> int:
    if not text.strip():
        return 0
    return max(math.ceil(word_count(text) / 0.75), math.ceil(len(text) / 4))


def openai_count(text: str) -> tuple[int, str]:
    encoding = _get_encoding()
    if encoding is None:
        return fallback_count(text), FALLBACK_LABEL
    return len(encoding.encode(text, disallowed_special=())), OPENAI_LABEL


def claude_estimate(text: str) -> tuple[int, int]:
    """Low/high estimate from Anthropic's documented words- and chars-per-token ratios."""
    if not text.strip():
        return (0, 0)
    by_words = math.ceil(word_count(text) / pricing.CLAUDE_WORDS_PER_TOKEN)
    by_chars = math.ceil(len(text) / pricing.CLAUDE_CHARS_PER_TOKEN)
    return (min(by_words, by_chars), max(by_words, by_chars))


def claude_estimate_reliable(text: str) -> bool:
    """Anthropic's ratio is for English prose. Under 3 words or mostly non-ASCII text, it badly undercounts."""
    visible = [ch for ch in text if not ch.isspace()]
    non_ascii = sum(1 for ch in visible if not ch.isascii())
    return word_count(text) >= 3 and non_ascii * 2 <= len(visible)


def split_for_display(text: str) -> list[str]:
    """Pieces that rejoin to exactly `text`, one per token where possible."""
    return [piece for piece, _ in split_with_counts(text)]


def split_with_counts(text: str) -> list[tuple[str, int]]:
    """Each drawn piece with how many tokens it holds.

    A token can end mid-character (some emoji and scripts), so it can't be drawn alone; it joins the
    next piece, which then holds 2 or more tokens. The counts add up to openai_count(text).
    """
    encoding = _get_encoding()
    if encoding is None:
        return [(piece, 1) for piece in re.findall(r"\s*\S+|\s+", text)]
    decoded, offsets = encoding.decode_with_offsets(encoding.encode(text, disallowed_special=()))
    if not offsets:
        return []  # empty text has no tokens
    ends = [*offsets[1:], len(decoded)]
    pieces: list[tuple[str, int]] = []
    held = 0
    for start, end in zip(offsets, ends, strict=True):
        held += 1
        if end > start:
            pieces.append((decoded[start:end], held))
            held = 0
    return pieces
