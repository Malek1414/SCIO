"""Filler and stutter removal. Used only by ParakeetTranscriber — whisper strips these natively
and contextually, which is why whisper is the default backend (spec §3.2)."""
import re

FILLERS: dict[str, frozenset[str]] = {
    "en": frozenset({"uh", "um", "erm", "eh", "hm", "hmm", "mhm", "uhh", "umm"}),
    "de": frozenset({"äh", "ähm", "ehm", "hm", "hmm", "öh", "ähh", "mhm"}),
}

_TOKEN = re.compile(r"\s+")
_MAX_STUTTER = 3          # collapse repeats up to three words long: "I don't I don't", "das ist das ist"


def _key(tok: str) -> str:
    return tok.strip(".,!?;:—–\"'").lower()


def clean_disfluencies(text: str, language: str = "en") -> str:
    """Drop filler words and collapse immediately repeated 1–3 word runs.

    Known limitation: a genuine immediate repetition ("I had had enough") loses one copy.
    Acceptable because this runs only on Parakeet output, which is not a default backend.
    """
    fillers = FILLERS.get(language, FILLERS["en"])
    toks = [t for t in _TOKEN.split(text.strip()) if t and _key(t) not in fillers]
    out: list[str] = []
    i = 0
    while i < len(toks):
        for size in range(_MAX_STUTTER, 0, -1):
            if len(out) >= size and i + size <= len(toks) \
                    and [_key(x) for x in out[-size:]] == [_key(x) for x in toks[i:i + size]]:
                i += size
                break
        else:
            out.append(toks[i])
            i += 1
    return " ".join(out)
