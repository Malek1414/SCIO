"""In-memory session state and its JSON shape (spec §8 storage, §2 wall)."""
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from typing import Iterable


def new_session_id(subject_code: str, now: float) -> str:
    ts = datetime.fromtimestamp(now, tz=timezone.utc).strftime("%Y-%m-%dT%H-%M-%S")
    return f"{subject_code}_{ts}"


@dataclass
class Turn:
    slot: int
    kind: str                       # "spine" | "probe"
    question_id: str | None
    question: str
    asked_at: float
    answer: str = ""
    answered_at: float | None = None
    skipped: bool = False
    rephrased: bool = False


@dataclass
class Session:
    session_id: str
    subject_code: str
    started_at: float
    consent_at: float
    language: str = "en"
    turns: list[Turn] = field(default_factory=list)
    pending: Turn | None = None
    surfaced_tags: list[str] = field(default_factory=list)
    probes_used: int = 0
    retries: int = 0
    closed: bool = False
    mirror: str | None = None
    take_home: str | None = None

    # ── derived ──────────────────────────────────────────────────────────
    def elapsed(self, now: float) -> float:
        return now - self.started_at

    def spine_turns(self) -> list[Turn]:
        return [t for t in self.turns if t.kind == "spine"]

    def current_slot(self) -> int:
        return 1 + len(self.spine_turns())

    def last_answer(self) -> str:
        return self.turns[-1].answer if self.turns else ""

    def last_spine(self) -> Turn | None:
        st = self.spine_turns()
        return st[-1] if st else None

    def used_ids(self) -> set[str]:
        return {t.question_id for t in self.turns if t.question_id}

    def fire_answers(self) -> list[str]:
        return [t.answer for t in self.spine_turns() if t.slot <= 4 and not t.skipped and t.answer]

    def transcript_text(self) -> str:
        return "\n".join(t.answer for t in self.turns if t.answer)

    def add_tags(self, tags: Iterable[str]) -> None:
        for t in tags:
            if t not in self.surfaced_tags:
                self.surfaced_tags.append(t)

    # ── the observer's view: Q/A + timestamps only ────────────────────────
    def transcript_for_observer(self) -> list[dict]:
        return [{"slot": t.slot, "kind": t.kind, "question": t.question, "answer": t.answer,
                 "asked_at": t.asked_at, "answered_at": t.answered_at, "skipped": t.skipped}
                for t in self.turns]

    # ── persistence ──────────────────────────────────────────────────────
    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: dict) -> "Session":
        d = dict(d)
        d["turns"] = [Turn(**t) for t in d.get("turns", [])]
        d["pending"] = Turn(**d["pending"]) if d.get("pending") else None
        return cls(**d)
