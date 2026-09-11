"""Verbatim-quote matching and small text helpers (spec §5.4, §5.6, §9)."""
import re

_WORD = re.compile(r"[a-z0-9']+")
_QUOTE = re.compile(r'["“]([^"”]+)["”]')
_SENT = re.compile(r"[.!?]+")


def normalize(s: str) -> list[str]:
    return _WORD.findall(s.lower())


def word_count(s: str) -> int:
    return len(normalize(s))


def contains_verbatim(haystack: str, needle: str, *, min_words: int, max_words: int | None = None) -> bool:
    """True if `needle` (normalised) is a contiguous run of `haystack` and its length is in bounds."""
    h, n = normalize(haystack), normalize(needle)
    if len(n) < min_words or (max_words is not None and len(n) > max_words):
        return False
    return any(h[i : i + len(n)] == n for i in range(len(h) - len(n) + 1))


def extract_quote(text: str) -> str | None:
    m = _QUOTE.search(text)
    return m.group(1).strip() if m else None


def longest_sentence(text: str) -> str:
    parts = [p.strip() for p in _SENT.split(text) if p.strip()]
    return max(parts, key=word_count) if parts else ""
