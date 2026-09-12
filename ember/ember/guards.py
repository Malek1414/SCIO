"""Deterministic guards. No LLM anywhere in this file (spec §5.5, §9)."""
from .bank import Candidate

# No guard here truncates the spine. An interview asks all seven slots however long it takes;
# the clock decides nothing about which questions get asked.
PROBE_WINDOW_S = 240.0     # 4:00 — no probes after this. Caps *extra* questions; never skips a spine slot.
SILENCE_S = 25.0           # show the gentler rephrase after this much silence
PROBE_MIN_WORDS = 15
MAX_PROBES = 2
STT_MIN_WORDS = 5


def filter_candidates(cands: list[Candidate], surfaced_tags: set[str], min_threat: int) -> list[Candidate]:
    return [c for c in cands
            if set(c.prerequisites) <= surfaced_tags and c.threat >= min_threat]


def probe_allowed(elapsed_s: float, probes_used: int, last_answer_words: int) -> bool:
    return elapsed_s < PROBE_WINDOW_S and probes_used < MAX_PROBES and last_answer_words >= PROBE_MIN_WORDS
