"""Diagnostic observer: transcript.json → observer.json. A pure function of the transcript (spec §6).
Never imports the engine side; the LLM is injected. See test_observer.py::test_import_wall."""
import json
import time
from datetime import datetime, timezone
from pathlib import Path

from pydantic import BaseModel, Field

from .bank import Bank, RubricEntry
from .constructs import CONSTRUCTS, signal_for
from .store import RUBRIC_VERSION
from .text import contains_verbatim

OPENER_TARGETS = ("F1", "F3")
MIN_QUOTE_WORDS = 3

OBSERVER_SCHEMA = {
    "type": "object",
    "properties": {
        "constructs": {
            "type": "object",
            "properties": {c: {
                "type": "object",
                "properties": {"score": {"type": "integer", "minimum": 1, "maximum": 7},
                               "evidence": {"type": "array", "items": {"type": "string"}},
                               "note": {"type": "string"}},
                "required": ["score", "evidence", "note"], "additionalProperties": False} for c in CONSTRUCTS},
            "required": list(CONSTRUCTS), "additionalProperties": False},
        "declined": {"type": "array", "items": {"type": "string"}},
        "flags": {"type": "array", "items": {"type": "string"}},
    },
    "required": ["constructs", "declined", "flags"],
    "additionalProperties": False,
}


class ConstructScore(BaseModel):
    score: int = Field(ge=1, le=7)
    signal: str
    evidence: list[str] = Field(default_factory=list)
    note: str = ""


class ObserverResult(BaseModel):
    subject_id: str
    session_id: str
    scored_at: str
    rubric_version: str
    language: str = "en"
    constructs: dict[str, ConstructScore]
    declined: list[str] = Field(default_factory=list)
    flags: list[str] = Field(default_factory=list)


# ── prompts ──────────────────────────────────────────────────────────────────
def build_observer_system(rubric: dict[str, RubricEntry], language: str = "en") -> str:
    blocks = []
    for cid in CONSTRUCTS:
        r = rubric[cid]
        anchors = "\n".join(f"    {a.score}: {a.description}\n       e.g. \"{a.exemplar}\""
                            for a in sorted(r.anchors, key=lambda a: a.score))
        inv = " (inverse: a high score means LOW tolerance)" if r.inverse else ""
        blocks.append(f"- {cid} — {r.name}{inv}\n{anchors}")
    joined = "\n".join(blocks)
    note = (
        "\nThe transcript is in German. Score against the English rubric above; quote evidence verbatim "
        "in German, exactly as the subject said it. Write every note and flag in English — the operator reads them.\n"
        if language == "de" else ""
    )
    return f"""You score an interview transcript against a fixed rubric. You are not the interviewer. You never advise, \
praise, or diagnose — you place each construct on a 1–7 scale using the anchors below and you cite evidence.

Rules:
- Score every construct 1–7 against its anchors. 1, 4 and 7 are defined; 2, 3, 5 and 6 sit between them.
- evidence: up to 3 quotes per construct, each copied EXACTLY from the subject's answers, at least 3 consecutive words. \
Never paraphrase. If the transcript gives no evidence, return an empty list.
- note: one line on why, written for the operator.
- declined: construct ids where the subject explicitly refused or deflected the question that targeted them.
- flags: anything the operator should read by hand — a contradiction, a long pause, something the rubric cannot hold. Not a score.
- Reply with one JSON object and nothing else.

Rubric:
{joined}
{note}"""


def build_observer_user(transcript: dict) -> str:
    lines = []
    for i, t in enumerate(transcript["turns"], 1):
        a = "(skipped)" if t.get("skipped") else t.get("answer", "")
        lines.append(f"[{i}] {t['kind']} slot {t['slot']}\nQ: {t['question']}\nA: {a}")
    return "Transcript:\n\n" + "\n\n".join(lines) + "\n\nScore every construct. Reply with the JSON object."


# ── coverage: which constructs were actually asked about ─────────────────────
def _question_targets(bank: Bank) -> dict[str, tuple[str, ...]]:
    m = {bank.opener.text: OPENER_TARGETS, bank.opener.rephrase: OPENER_TARGETS}
    for c in bank.candidates:
        m[c.text] = tuple(c.targets)
        m[c.rephrase] = tuple(c.targets)
    return m


def coverage(transcript: dict, bank: Bank) -> dict[str, bool]:
    targets = _question_targets(bank)
    covered: set[str] = set()
    for t in transcript["turns"]:
        if t["kind"] != "spine" or t.get("skipped") or not t.get("answer"):
            continue
        covered.update(targets.get(t["question"], ()))
    return {c: c in covered for c in CONSTRUCTS}


# ── validation: the model proposes, this function disposes ───────────────────
def validate(raw: dict, transcript: dict, bank: Bank, *, subject_id: str, session_id: str,
             scored_at: str, rubric_version: str, language: str = "en") -> ObserverResult:
    answers = [t.get("answer", "") for t in transcript["turns"] if t.get("answer")]
    cov = coverage(transcript, bank)
    raw_c = raw.get("constructs") or {}
    declined_raw = {d for d in (raw.get("declined") or []) if d in CONSTRUCTS}
    flags = [str(f) for f in (raw.get("flags") or [])]
    constructs: dict[str, ConstructScore] = {}
    declined: set[str] = set(declined_raw)
    for cid in CONSTRUCTS:
        entry = raw_c.get(cid) or {}
        try:
            score = int(entry.get("score"))
        except (TypeError, ValueError):
            score = 1
            flags.append(f"{cid}: model returned no valid score; set to 1")
        score = max(1, min(7, score))
        kept: list[str] = []
        hit_turns: set[int] = set()
        proposed = [q for q in (entry.get("evidence") or []) if isinstance(q, str)]
        for q in proposed:
            matched = [i for i, a in enumerate(answers) if contains_verbatim(a, q, min_words=MIN_QUOTE_WORDS)]
            if matched:
                kept.append(q.strip())
                hit_turns.update(matched)
        if len(proposed) - len(kept):
            flags.append(f"{cid}: {len(proposed) - len(kept)} evidence quote(s) not verbatim, dropped")
        if not cov[cid]:
            declined.add(cid)
        skipped = cid in declined          # one source of truth: §6 says declined ⇒ low signal
        constructs[cid] = ConstructScore(score=score, signal=signal_for(len(kept), len(hit_turns), skipped),
                                         evidence=kept[:3], note=str(entry.get("note") or "")[:200])
    return ObserverResult(subject_id=subject_id, session_id=session_id, scored_at=scored_at,
                          rubric_version=rubric_version, language=language, constructs=constructs,
                          declined=sorted(declined), flags=flags)


# ── entry points ─────────────────────────────────────────────────────────────
def score(transcript: dict, bank: Bank, llm, *, now: float | None = None) -> ObserverResult:
    language = transcript.get("language", "en")
    raw = llm.call_json(system=build_observer_system(bank.rubric, language), user=build_observer_user(transcript),
                        schema=OBSERVER_SCHEMA, effort="high")
    ts = datetime.fromtimestamp(now if now is not None else time.time(), tz=timezone.utc).isoformat()
    return validate(raw, transcript, bank, subject_id=transcript["subject_code"],
                    session_id=transcript["session_id"], scored_at=ts, rubric_version=RUBRIC_VERSION,
                    language=language)


def observe_session(session_dir: Path, bank: Bank, llm) -> Path:
    transcript = json.loads((session_dir / "transcript.json").read_text(encoding="utf-8"))
    lang = transcript.get("language", "en")
    if lang != bank.language:            # coverage() keys on question TEXT, which is per-language
        from .bank import load_bank
        bank = load_bank(lang)
    result = score(transcript, bank, llm)
    out = session_dir / "observer.json"
    out.write_text(json.dumps(result.model_dump(), indent=2, ensure_ascii=False), encoding="utf-8")
    return out


def load_results(sessions_root: Path) -> dict[str, dict]:
    """session_id → parsed observer.json, for every session that has one."""
    return {p.parent.name: json.loads(p.read_text(encoding="utf-8")) for p in sorted(Path(sessions_root).glob("*/observer.json"))}
