"""Deterministic guards. No LLM anywhere in this file (spec §5.5, §9)."""
from .bank import Candidate

PROBE_WINDOW_S = 240.0     # 4:00 — no probes after this
FIRE_GUARD_S = 270.0       # 4:30 — still in Fire? jump to Compass
Q7_GATE_S = 345.0          # 5:45 — Q7 only if Q6 finished before this
HARD_CLOSE_S = 390.0       # 6:30 — close after the current answer, whatever the slot
SILENCE_S = 25.0           # show the gentler rephrase after this much silence
PROBE_MIN_WORDS = 15
MAX_PROBES = 2
STT_MIN_WORDS = 5
MAX_RETRIES = 2


def filter_candidates(cands: list[Candidate], surfaced_tags: set[str], min_threat: int) -> list[Candidate]:
    return [c for c in cands
            if set(c.prerequisites) <= surfaced_tags and c.threat >= min_threat]


def probe_allowed(elapsed_s: float, probes_used: int, last_answer_words: int) -> bool:
    return elapsed_s < PROBE_WINDOW_S and probes_used < MAX_PROBES and last_answer_words >= PROBE_MIN_WORDS


def resolve_slot(session_slot: int, elapsed_s: float) -> int:
    if session_slot <= 4 and elapsed_s > FIRE_GUARD_S:
        return 5
    return session_slot


def q7_allowed(elapsed_s: float) -> bool:
    return elapsed_s < Q7_GATE_S


def should_hard_close(elapsed_s: float) -> bool:
    return elapsed_s >= HARD_CLOSE_S
