"""Maieutic engine: chooses spine questions, writes probes and the close (spec §5)."""
import time
from dataclasses import dataclass
from typing import Literal

from pydantic import BaseModel, Field, ValidationError

from .bank import Bank, Candidate
from .constructs import TAGS, TAG_HINTS
from .guards import filter_candidates, probe_allowed, resolve_slot, q7_allowed, should_hard_close
from .llm import LLMError
from .session import Session
from .text import contains_verbatim, extract_quote, word_count, longest_sentence


# ── contracts ────────────────────────────────────────────────────────────────
class Action(BaseModel):
    action: Literal["pick", "probe", "close"]
    candidate_id: str | None = None
    probe_text: str | None = None
    surfaced_tags: list[str] = Field(default_factory=list)
    reason: str = ""


class CloseOut(BaseModel):
    mirror: str
    take_home: str


@dataclass
class Next:
    kind: str                    # "spine" | "probe" | "close"
    slot: int
    question_id: str | None
    text: str
    fallback_used: bool
    log: dict


ACTION_SCHEMA = {
    "type": "object",
    "properties": {
        "action": {"type": "string", "enum": ["pick", "probe", "close"]},
        "candidate_id": {"type": ["string", "null"]},
        "probe_text": {"type": ["string", "null"]},
        "surfaced_tags": {"type": "array", "items": {"type": "string"}},
        "reason": {"type": "string"},
    },
    "required": ["action", "candidate_id", "probe_text", "surfaced_tags", "reason"],
    "additionalProperties": False,
}

CLOSE_SCHEMA = {
    "type": "object",
    "properties": {"mirror": {"type": "string"}, "take_home": {"type": "string"}},
    "required": ["mirror", "take_home"],
    "additionalProperties": False,
}


# ── prompts ──────────────────────────────────────────────────────────────────
def build_system_prompt(bank: Bank) -> str:
    cands = "\n".join(
        f"- {c.id} | slot {c.slot} | {c.cluster} | targets {','.join(c.targets)} | threat {c.threat} | "
        f"{c.framing} | needs {','.join(c.prerequisites) or '-'}\n  {c.text}"
        for c in bank.candidates)
    tags = "\n".join(f"- {t}: {TAG_HINTS[t]}" for t in sorted(TAGS))
    return f"""You choose the next question in a short spoken interview. The subject is a young builder. \
The goal is for them to say something true about themselves they had not put into words. \
You never diagnose, never explain what a question is for, never praise, never summarise.

Each turn you receive the transcript so far, the current slot, and the candidate questions you may pick from. \
Reply with one JSON object and nothing else.

Actions:
- "pick": choose ONE candidate_id from the offered list. Follow the thread the subject opened; prefer the \
candidate whose prerequisite tags just surfaced; prefer higher threat when answers are long and open.
- "probe": only when "Probe allowed: yes". Write probe_text: a statement, not a question, at most 12 words, \
containing a 3–6 word phrase copied exactly from the last answer inside double quotes, framed "You said …". \
Then the subject fills the silence. No yes/no phrasing anywhere. Do not probe if the answer already went deep.
- If the last answer is a refusal or a deflection ("I'd rather not"), never probe it — pick the next candidate.
- "close": only if told the session is closing.

surfaced_tags: list every tag below whose topic appears anywhere in the transcript so far (empty list if none):
{tags}

Candidates (you may only pick ids that appear in the turn's offered list):
{cands}
"""


def _render_transcript(session: Session) -> str:
    lines = []
    for t in session.turns:
        q = f"[{t.kind} slot {t.slot}] Q: {t.question}"
        a = "(skipped)" if t.skipped else f"A: {t.answer}"
        lines.append(f"{q}\n{a}")
    return "\n\n".join(lines) or "(no turns yet)"


def build_turn_prompt(session: Session, slot: int, offered: list[Candidate], probe_ok: bool, elapsed_s: float) -> str:
    ids = ", ".join(c.id for c in offered)
    return (f"Transcript so far:\n{_render_transcript(session)}\n\n"
            f"Elapsed: {int(elapsed_s)} s. Next slot: {slot}.\n"
            f"Offered candidate ids: {ids}\n"
            f"Probe allowed: {'yes' if probe_ok else 'no'}\n"
            f"Reply with the JSON object.")


def build_close_prompt(session: Session) -> str:
    return (f"The interview is ending. Transcript:\n{_render_transcript(session)}\n\n"
            "Write the close as JSON. mirror: one thing the subject said, copied EXACTLY, at least 5 words, "
            "no interpretation. take_home: one question of at most 20 words that references the mirror and "
            "that they will not get to answer here. No praise, no diagnosis, no advice.")


# ── engine ───────────────────────────────────────────────────────────────────
class Engine:
    def __init__(self, bank: Bank, llm):
        self.bank = bank
        self.llm = llm
        self.system = build_system_prompt(bank)

    def first(self) -> Next:
        return Next(kind="spine", slot=1, question_id=None, text=self.bank.opener.text,
                    fallback_used=False, log={"note": "fixed opener"})

    def next(self, session: Session, now: float) -> Next:
        elapsed = session.elapsed(now)
        if should_hard_close(elapsed):
            return Next(kind="close", slot=session.current_slot(), question_id=None, text="",
                        fallback_used=False, log={"note": "hard close", "elapsed": elapsed})

        slot = resolve_slot(session.current_slot(), elapsed)
        if slot == 7 and not q7_allowed(elapsed):
            return Next(kind="close", slot=7, question_id=None, text="", fallback_used=False,
                        log={"note": "q7 gate", "elapsed": elapsed})
        if slot > 7:
            return Next(kind="close", slot=slot, question_id=None, text="", fallback_used=False,
                        log={"note": "slots exhausted", "elapsed": elapsed})

        used = session.used_ids()
        pool = self.bank.for_slot(slot, used)
        last_spine = session.last_spine()
        min_threat = 0
        if slot <= 4 and last_spine and last_spine.question_id:          # Fire-only threat monotonicity
            min_threat = self.bank.by_id(last_spine.question_id).threat
        offered = filter_candidates(pool, set(session.surfaced_tags), min_threat)
        filter_empty = not offered
        if filter_empty:                                                 # never strand a slot
            offered = pool
        default = self.bank.default_for(slot, used)
        if default is None:
            return Next(kind="close", slot=slot, question_id=None, text="", fallback_used=False,
                        log={"note": "no candidates left", "elapsed": elapsed})

        last = session.last_answer()
        probe_ok = probe_allowed(elapsed, session.probes_used, word_count(last))
        user = build_turn_prompt(session, slot, offered, probe_ok, elapsed)
        log: dict = {"slot": slot, "elapsed": elapsed, "offered": [c.id for c in offered],
                     "probe_allowed": probe_ok, "min_threat": min_threat, "filter_empty": filter_empty}
        t0 = time.perf_counter()
        try:
            raw = self.llm.call_json(system=self.system, user=user, schema=ACTION_SCHEMA, effort="low")
            log["raw"] = raw
            action = Action.model_validate(raw)
        except (LLMError, ValidationError) as e:
            log.update(error=str(e), latency_ms=int((time.perf_counter() - t0) * 1000), meta=getattr(self.llm, "last_meta", {}))
            return self._fallback(slot, default, log)
        log.update(latency_ms=int((time.perf_counter() - t0) * 1000), meta=getattr(self.llm, "last_meta", {}))

        session.add_tags(t for t in action.surfaced_tags if t in TAGS)

        if action.action == "probe":
            quote = extract_quote(action.probe_text or "")
            ok = (probe_ok and quote is not None
                  and contains_verbatim(last, quote, min_words=3, max_words=6)
                  and word_count(action.probe_text) <= 12
                  and not action.probe_text.strip().endswith("?"))
            if not ok:
                log["validation_error"] = "probe rejected"
                return self._fallback(slot, default, log)
            session.probes_used += 1
            return Next(kind="probe", slot=session.current_slot() - 1, question_id=None,
                        text=action.probe_text.strip(), fallback_used=False, log=log)

        if action.action == "pick" and action.candidate_id in {c.id for c in offered}:
            c = self.bank.by_id(action.candidate_id)
            return Next(kind="spine", slot=slot, question_id=c.id, text=c.text, fallback_used=False, log=log)

        log["validation_error"] = f"unusable action {action.action} / {action.candidate_id}"
        return self._fallback(slot, default, log)

    @staticmethod
    def _fallback(slot: int, default: Candidate, log: dict) -> Next:
        log["fallback"] = default.id
        return Next(kind="spine", slot=slot, question_id=default.id, text=default.text, fallback_used=True, log=log)

    def close(self, session: Session) -> CloseOut:
        transcript = session.transcript_text()
        try:
            raw = self.llm.call_json(system=self.system, user=build_close_prompt(session),
                                     schema=CLOSE_SCHEMA, effort="high")
            out = CloseOut.model_validate(raw)
            mirror_ok = contains_verbatim(transcript, out.mirror, min_words=5)
            th = out.take_home.strip()
            th_ok = th.endswith("?") and word_count(th) <= 20
            if mirror_ok and th_ok:
                return CloseOut(mirror=out.mirror.strip(), take_home=th)
        except (LLMError, ValidationError):
            pass
        fire = session.fire_answers() or [transcript]
        mirror = max((longest_sentence(a) for a in fire), key=word_count) if fire else ""
        return CloseOut(mirror=mirror, take_home=self.bank.opener.fallback_take_home)
