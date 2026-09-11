# ember v1 — Observer & Graph (Plan B) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Score every finished session on the nine constructs from its `transcript.json` alone, calibrate that scoring against hand scores, and render the cohort as a scatter that drills into a per-subject radar with evidence — plus the written protocol for the five pilots.

**Architecture:** `observer.py` is a pure function of `transcript.json` + `rubric.yaml`: one Agent SDK call at effort `high` against a JSON schema, then deterministic validation (evidence must be verbatim, signal is *computed*, uncovered constructs are `declined`). `calibrate.py` compares `observer.json` files with a hand-score YAML and reports agreement. `export.py` folds all `observer.json` files into `graph/data.js`, which a static `graph/index.html` (vanilla JS + inline SVG, no CDN) renders. The CLI gains `observe`, `export`, `calibrate`.

**Tech Stack:** Python 3.12 (`uv`), `claude-agent-sdk` via the existing `ember.llm.LLM`, pydantic v2, PyYAML, pytest; vanilla HTML/SVG for the graph.

**Spec:** `docs/superpowers/specs/2026-09-11-ember-v1-design.md` §6, §7, §10, §11, §13 steps 4–6. Plan A (`2026-09-11-ember-v1-interview-loop.md`) is merged on `main`; this plan builds on it.

## Global Constraints

- **Repo layout:** the git repo root is `~/Desktop/SCIO`; the project is `~/Desktop/SCIO/ember`. Every `uv run` command runs from the project dir. `git add` paths below are relative to the project dir (git resolves them). Branch: `ember/v1-observer-graph` off `main` — the executor creates it.
- **Python:** 3.12 via `uv`; all commands `uv run …`.
- **The wall (spec §2):** the observer reads **only** `transcript.json` and the bank's `rubric.yaml`/question texts. `ember/observer.py` must not import `ember.engine`, `ember.guards`, `ember.session`, `ember.server`, or `ember.llm` — the LLM is injected. Enforced by a test.
- **Observer rules (spec §6):** score 1–7 per construct against the three anchors; every evidence quote must be a verbatim substring (≥ 3 consecutive words, case-insensitive, punctuation-stripped) of some answer, or it is dropped; `signal` is computed by `ember.constructs.signal_for(n_quotes, n_distinct_answers, skipped)`, never taken from the model; a construct whose targeting question was never asked-and-answered, or which the model marks declined, is `signal: low` **and** listed in `declined`; `flags` are free text for the operator, never a score; `rubric_version` is `ember.store.RUBRIC_VERSION`; effort `high`; the observer runs after the session and is re-runnable (overwrites `observer.json`).
- **LLM options:** unchanged from Plan A — `ember.llm.LLM.call_json(system=, user=, schema=, effort=)` with the isolation options baked in. `ember observe` calls `guard_environment()` first.
- **Calibration target (spec §6):** observer within 1 point of the human median on **≥ 80 %** of construct scores; any **≥ 2-point** disagreement names an anchor to tighten.
- **Graph (spec §7 + dataviz skill):** one static page, opens from disk (`file://`) — data is embedded via `graph/data.js` (`window.EMBER_DATA = …`), which is **git-ignored** (it contains quotes). Cohort scatter: axes selectable from the nine constructs, default **F1 × F2**; dot size = signal (r 4 / 6 / 8 for low / med / high); colour = a third construct (default C2) on a **sequential** one-hue ramp; 2 px surface ring on every dot; ≥ 24 px hit target; hover tooltip; a legend; a table view. Subject view: nine-spoke radar as **one series** (slot-1 blue, 2 px line, ≤ 10 % fill), ≥ 8 px vertex markers, hollow marker where signal is low; spokes ordered F1 F2 F3 C1 C2 C3 G1 G2 G3; evidence per construct with a cluster dot (categorical slots 1–3 only); `declined`, `flags`, mirror, take-home. Text always in text tokens, never a series colour. Light palette on `:root`; dark under **both** `@media (prefers-color-scheme: dark)` guarded by `:root:not([data-theme="light"])` **and** `:root[data-theme="dark"]`. Untrusted strings (codes, quotes) go in via `textContent`.
- **Palette (dataviz reference instance, validated):** surface `#fcfcfb` / dark `#1a1a19`; page `#f9f9f7` / `#0d0d0d`; primary ink `#0b0b0b` / `#ffffff`; secondary `#52514e` / `#c3c2b7`; muted `#898781`; grid `#e1e0d9` / `#2c2c2a`; axis `#c3c2b7` / `#383835`; series-1 blue `#2a78d6` / `#3987e5`; series-2 orange `#eb6834` / `#d95926`; series-3 aqua `#1baf7a` / `#199e70`. Colour tiers for the colour construct — validated with `--ordinal` in both modes; a 7-step ramp **fails** the adjacent-ΔL check, so scores are binned **1–2 · 3–4 · 5–6 · 7** — light: `#86b6ef #3987e5 #1c5cab #0d366b`; dark (anchor flipped, never darker than step 600): `#184f95 #2a78d6 #5598e7 #86b6ef`. Aqua `#1baf7a` is 2.74:1 on the light surface; the validator's relief rule is met because the cluster dot always sits beside a text label and a table view exists.
- **Commits:** every commit message ends with the two trailer lines shown in Task 1 Step 6. Use them verbatim.

---

## File Structure

```
ember/
  ember/
    observer.py            OBSERVER_SCHEMA, ConstructScore, ObserverResult, prompts, coverage(), validate(),
                           score(), observe_session(), load_results()
    calibrate.py           load_human_scores(), median_scores(), agreement() -> Report, render()
    export.py              collect(), write_data_js()
    cli.py                 + observe / export / calibrate   (Modify)
  graph/index.html         cohort scatter + table → subject radar + evidence (static, reads data.js)
  graph/data.js            generated, git-ignored
  calibration/human_scores.yaml   hand-score template (committed)
  calibration/pilot_log.yaml      the two pilot questions per subject (committed template)
  docs/pilot-protocol.md   how to run the five pilots and the 40
  .gitignore               + graph/data.js   (Modify)
  tests/
    test_observer.py, test_observer_recorded.py, test_calibrate.py, test_export.py,
    test_graph_static.py, test_cli.py (Modify)
    fixtures/recorded/     + one observer recording (committed)
```

Dependency direction: `observer ← calibrate`, `observer ← export ← cli`. `observer` depends only on `bank`, `constructs`, `text`, `store.RUBRIC_VERSION`.

---

### Task 1: Observer contract, coverage, and validation (no LLM)

**Files:**
- Create: `ember/observer.py`, `tests/test_observer.py`

**Interfaces:**
- Consumes: `Bank`, `RubricEntry`, `load_bank` (`ember.bank`); `CONSTRUCTS`, `signal_for` (`ember.constructs`); `contains_verbatim` (`ember.text`); `RUBRIC_VERSION` (`ember.store`).
- Produces: `OPENER_TARGETS = ("F1", "F3")`; `MIN_QUOTE_WORDS = 3`; `OBSERVER_SCHEMA: dict`; pydantic `ConstructScore(score: int, signal: str, evidence: list[str], note: str)`; `ObserverResult(subject_id, session_id, scored_at, rubric_version, constructs: dict[str, ConstructScore], declined: list[str], flags: list[str])`; `coverage(transcript: dict, bank: Bank) -> dict[str, bool]`; `validate(raw: dict, transcript: dict, bank: Bank, *, subject_id: str, session_id: str, scored_at: str, rubric_version: str) -> ObserverResult`.

- [x] **Step 1: Write the failing tests**

`tests/test_observer.py`:
```python
import json
from pathlib import Path
import pytest

from ember.bank import load_bank
from ember.observer import (OBSERVER_SCHEMA, ObserverResult, coverage, validate)

A1 = "They just work a lot more than everyone else and they never wait to feel ready before they start something"
A2 = "I would be in the workshop with the door locked building the synth nobody asked for and no one could reach me"
A3 = "I gave up the graduate scheme and my parents thought I was insane but I have stopped trying to explain it"
ALL = ("F1", "F2", "F3", "C1", "C2", "C3", "G1", "G2", "G3")


@pytest.fixture(scope="module")
def bank():
    return load_bank()


def transcript(bank, answers=(A1, A2, A3), *, skip=(), questions=None):
    qs = questions or [bank.opener.text, bank.by_id("F1-a").text, bank.by_id("F2-a").text]
    turns = [{"slot": i + 1, "kind": "spine", "question": q, "answer": "" if i in skip else a,
              "asked_at": 10.0 * i, "answered_at": 10.0 * i + 8, "skipped": i in skip}
             for i, (q, a) in enumerate(zip(qs, answers))]
    return {"session_id": "S01_x", "subject_code": "S01", "started_at": 0.0, "closed": True,
            "mirror": None, "take_home": None, "turns": turns}


def raw(**over):
    base = {c: {"score": 4, "evidence": [], "note": "n"} for c in ALL}
    base.update(over)
    return {"constructs": base, "declined": [], "flags": []}


def _validate(bank, r, tr):
    return validate(r, tr, bank, subject_id="S01", session_id="S01_x", scored_at="t", rubric_version="1.0.0")


def test_schema_requires_all_nine_constructs():
    assert set(OBSERVER_SCHEMA["properties"]["constructs"]["required"]) == set(ALL)
    assert OBSERVER_SCHEMA["properties"]["constructs"]["properties"]["F1"]["properties"]["score"]["maximum"] == 7


def test_coverage_from_question_text_including_rephrase(bank):
    cov = coverage(transcript(bank), bank)
    assert cov == {"F1": True, "F2": True, "F3": True, "C1": False, "C2": False, "C3": False, "G1": False, "G2": False, "G3": False}
    assert coverage(transcript(bank, skip=(2,)), bank)["F2"] is False
    rephrased = transcript(bank, questions=[bank.opener.rephrase, bank.by_id("F1-a").rephrase, bank.by_id("F2-a").rephrase])
    assert coverage(rephrased, bank)["F2"] is True
    probe_only = transcript(bank)
    probe_only["turns"][2]["kind"] = "probe"
    assert coverage(probe_only, bank)["F2"] is False


def test_validate_keeps_only_verbatim_evidence_and_computes_signal(bank):
    r = raw(F1={"score": 6, "evidence": ["never wait to feel ready", "made-up quote here", "work a lot more"], "note": "x"},
            F2={"score": 5, "evidence": ["gave up the graduate scheme", "door locked building", "stopped trying to explain"], "note": "y"})
    out = _validate(bank, r, transcript(bank))
    assert out.constructs["F1"].evidence == ["never wait to feel ready", "work a lot more"]
    assert out.constructs["F1"].signal == "med"                     # 2 quotes, one answer
    assert out.constructs["F2"].signal == "high"                    # 3 quotes across 2 answers
    assert any("F1: 1 evidence quote(s) not verbatim" in f for f in out.flags)
    assert out.constructs["F3"].signal == "low"                     # covered by the opener, but no evidence
    assert "C1" in out.declined and out.constructs["C1"].signal == "low"


def test_validate_declined_bad_score_and_clamp(bank):
    r = raw(F2={"score": 5, "evidence": ["gave up the graduate scheme", "stopped trying to explain", "door locked building"], "note": ""},
            C2={"score": "x", "evidence": [], "note": ""},
            G1={"score": 9, "evidence": [], "note": ""})
    r["declined"] = ["F2", "ZZ"]
    r["flags"] = ["subject paused 30 s before F2"]
    out = _validate(bank, r, transcript(bank))
    assert out.constructs["F2"].signal == "low" and "F2" in out.declined
    assert out.constructs["C2"].score == 1 and any("C2: model returned no valid score" in f for f in out.flags)
    assert out.constructs["G1"].score == 7
    assert "ZZ" not in out.declined and out.flags[0] == "subject paused 30 s before F2"
    assert isinstance(out, ObserverResult) and out.rubric_version == "1.0.0"
```

- [x] **Step 2: Run to verify failure**

Run: `cd ~/Desktop/SCIO/ember && uv run pytest tests/test_observer.py -v`
Expected: `ModuleNotFoundError: No module named 'ember.observer'`

- [x] **Step 3: Implement**

`ember/observer.py`:
```python
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
    constructs: dict[str, ConstructScore]
    declined: list[str] = Field(default_factory=list)
    flags: list[str] = Field(default_factory=list)


# ── prompts ──────────────────────────────────────────────────────────────────
def build_observer_system(rubric: dict[str, RubricEntry]) -> str:
    blocks = []
    for cid in CONSTRUCTS:
        r = rubric[cid]
        anchors = "\n".join(f"    {a.score}: {a.description}\n       e.g. \"{a.exemplar}\""
                            for a in sorted(r.anchors, key=lambda a: a.score))
        inv = " (inverse: a high score means LOW tolerance)" if r.inverse else ""
        blocks.append(f"- {cid} — {r.name}{inv}\n{anchors}")
    joined = "\n".join(blocks)
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
"""


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
             scored_at: str, rubric_version: str) -> ObserverResult:
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
        skipped = (not cov[cid]) or (cid in declined_raw)
        constructs[cid] = ConstructScore(score=score, signal=signal_for(len(kept), len(hit_turns), skipped),
                                         evidence=kept[:3], note=str(entry.get("note") or "")[:200])
    return ObserverResult(subject_id=subject_id, session_id=session_id, scored_at=scored_at,
                          rubric_version=rubric_version, constructs=constructs,
                          declined=sorted(declined), flags=flags)


# ── entry points ─────────────────────────────────────────────────────────────
def score(transcript: dict, bank: Bank, llm, *, now: float | None = None) -> ObserverResult:
    raw = llm.call_json(system=build_observer_system(bank.rubric), user=build_observer_user(transcript),
                        schema=OBSERVER_SCHEMA, effort="high")
    ts = datetime.fromtimestamp(now if now is not None else time.time(), tz=timezone.utc).isoformat()
    return validate(raw, transcript, bank, subject_id=transcript["subject_code"],
                    session_id=transcript["session_id"], scored_at=ts, rubric_version=RUBRIC_VERSION)


def observe_session(session_dir: Path, bank: Bank, llm) -> Path:
    transcript = json.loads((session_dir / "transcript.json").read_text(encoding="utf-8"))
    result = score(transcript, bank, llm)
    out = session_dir / "observer.json"
    out.write_text(json.dumps(result.model_dump(), indent=2, ensure_ascii=False), encoding="utf-8")
    return out


def load_results(sessions_root: Path) -> dict[str, dict]:
    """session_id → parsed observer.json, for every session that has one."""
    return {p.parent.name: json.loads(p.read_text(encoding="utf-8")) for p in sorted(Path(sessions_root).glob("*/observer.json"))}
```

- [x] **Step 4: Run to verify pass**

Run: `uv run pytest tests/test_observer.py -v`
Expected: `4 passed`

- [x] **Step 5: Commit**

```bash
git add ember/observer.py tests/test_observer.py
git commit -m "feat: observer contract, coverage, and deterministic validation" \
  -m "Co-Authored-By: WOZCODE <contact@withwoz.com>" \
  -m "Claude-Session: https://claude.ai/code/session_011xY91ug8K4Ke8JHFsa5ekB"
```

---

### Task 2: Observer scoring, file I/O, and the import wall

**Files:**
- Modify: `tests/test_observer.py` (append)

**Interfaces:**
- Consumes: everything in Task 1; `FakeLLM` from `tests/conftest.py`.
- Produces: verified behaviour of `score()`, `observe_session()`, `load_results()`.

- [x] **Step 1: Append the failing tests**

Append to `tests/test_observer.py`:
```python


from ember.observer import score, observe_session, load_results, build_observer_system, build_observer_user
from tests.conftest import FakeLLM


def test_score_calls_llm_with_rubric_high_effort_and_stamps_version(bank):
    llm = FakeLLM([raw(F1={"score": 6, "evidence": ["never wait to feel ready"], "note": "n"})])
    out = score(transcript(bank), bank, llm, now=1_757_600_000.0)
    call = llm.calls[0]
    assert call["effort"] == "high" and call["schema"] is OBSERVER_SCHEMA
    assert "F3 — Mediocrity tolerance (inverse" in call["system"] and "watching someone fall asleep" in call["system"]
    assert A2 in call["user"] and "[2] spine slot 2" in call["user"]
    assert out.rubric_version == "1.0.0" and out.scored_at.startswith("2025-09-11")
    assert out.constructs["F1"].score == 6 and out.constructs["F1"].signal == "low"      # one quote → low


def test_observe_session_reads_only_transcript_and_overwrites(tmp_path: Path, bank):
    d = tmp_path / "S01_x"
    d.mkdir()
    (d / "transcript.json").write_text(json.dumps(transcript(bank)))
    (d / "engine_log.json").write_text('[{"secret": "engine reasoning must never be read"}]')
    p = observe_session(d, bank, FakeLLM([raw(G1={"score": 2, "evidence": [], "note": ""})]))
    first = json.loads(p.read_text())
    assert p.name == "observer.json" and first["constructs"]["G1"]["score"] == 2 and first["subject_id"] == "S01"
    observe_session(d, bank, FakeLLM([raw(G1={"score": 5, "evidence": [], "note": ""})]))
    assert json.loads(p.read_text())["constructs"]["G1"]["score"] == 5
    assert load_results(tmp_path) == {"S01_x": json.loads(p.read_text())}


def test_import_wall():
    src = (Path(__file__).parent.parent / "ember" / "observer.py").read_text()
    for forbidden in ("from .engine", "from .guards", "from .session", "from .server", "from .llm", "import ember.engine"):
        assert forbidden not in src, forbidden
```

- [x] **Step 2: Run to verify the new tests pass against Task 1's implementation**

Run: `uv run pytest tests/test_observer.py -v`
Expected: `7 passed`. (Task 1 implemented these entry points; this task pins their behaviour. If any fail, fix `ember/observer.py` — do not weaken the test.)

- [x] **Step 3: Commit**

```bash
git add tests/test_observer.py
git commit -m "test: observer scoring, file I/O, and import wall" \
  -m "Co-Authored-By: WOZCODE <contact@withwoz.com>" \
  -m "Claude-Session: https://claude.ai/code/session_011xY91ug8K4Ke8JHFsa5ekB"
```

---

### Task 3: Observer against the real model (recorded)

**Files:**
- Create: `tests/test_observer_recorded.py`; `tests/fixtures/recorded/<hash>.json` (recorded on first run, committed)

**Interfaces:**
- Consumes: `score` (Task 1); `RecordingLLM` (`tests/recording.py`, Plan A); `LLM`, `guard_environment` (`ember.llm`).

- [x] **Step 1: Write the test with a synthetic seven-turn session**

`tests/test_observer_recorded.py`:
```python
import pytest

from ember.bank import load_bank
from ember.constructs import CONSTRUCTS
from ember.llm import LLM, guard_environment
from ember.observer import score
from ember.text import contains_verbatim
from tests.recording import RecordingLLM

pytestmark = pytest.mark.api

# A synthetic subject. Question ids follow the default path through the bank.
ANSWERS = [
    (None, "My flatmate Karim. Everyone in our year talks about starting something and he just starts. He got rejected "
           "from the accelerator twice and both times had a new version the next week. He doesn't wait to feel ready. "
           "I keep waiting to feel ready and he treats it like a Tuesday."),
    ("F1-a", "If money was handled I'd be in the workshop. There's a half-finished synth on my desk I haven't touched in "
             "two months because of the internship. Two in the afternoon I'd have the soldering iron out and nobody "
             "would be able to reach me. Not travelling, not resting. Building the thing nobody asked for."),
    ("F2-a", "I gave up the graduate scheme. Everyone thought I was insane, my parents especially. Safe money and a title "
             "and I walked away to keep working on this. I don't regret it but I can't fully explain it to them and "
             "I've stopped trying. That's the real cost. Not the money. The explaining."),
    ("F2-c", "I'd have to become someone who doesn't pick up the phone. I already see it a bit. My sister called three "
             "times last month and I let it ring because I was in the middle of something. If it works I think that "
             "becomes normal and I'm not sure I want normal to look like that."),
    ("C3-a", "The guy at the reunion who is still talking about the thing he was going to build. Ten years on, same "
             "story, better excuses. I can picture him exactly. Sometimes I catch myself using his sentences."),
    ("G1-a", "Forty minutes in I've stopped pretending to read. That's when the synth shows up in my head, and the calls "
             "I didn't return, in that order. I'd probably start sketching something just to not sit with the second one."),
    ("G3-a", "When I'm at my best they're doing their own thing and they know I'll surface. My sister sends photos and "
             "doesn't expect a reply until Sunday. That's the version I want. The version I've got is them waiting."),
]


def full_transcript(bank):
    turns = []
    for i, (qid, a) in enumerate(ANSWERS):
        q = bank.opener.text if qid is None else bank.by_id(qid).text
        turns.append({"slot": i + 1, "kind": "spine", "question": q, "answer": a,
                      "asked_at": 45.0 * i, "answered_at": 45.0 * i + 40, "skipped": False})
    return {"session_id": "SYN_2026-09-11T00-00-00", "subject_code": "SYN", "started_at": 0.0, "closed": True,
            "mirror": "I'm not sure I want normal to look like that", "take_home": "Who is waiting?", "turns": turns}


@pytest.fixture(scope="module")
def llm():
    guard_environment()
    return RecordingLLM(inner=LLM())


def test_observer_scores_full_session(llm):
    bank = load_bank()
    tr = full_transcript(bank)
    out = score(tr, bank, llm, now=0.0)
    text = "\n".join(t["answer"] for t in tr["turns"])
    assert set(out.constructs) == set(CONSTRUCTS)
    assert all(1 <= c.score <= 7 for c in out.constructs.values())
    assert all(contains_verbatim(text, q, min_words=3) for c in out.constructs.values() for q in c.evidence)
    assert {"C1", "C2", "G2"} <= set(out.declined)                 # never asked → declined, low
    assert all(out.constructs[c].signal == "low" for c in ("C1", "C2", "G2"))
    assert sum(c.signal != "low" for c in out.constructs.values()) >= 3   # the six covered constructs should mostly have evidence
    assert all(out.constructs[c].note for c in ("F1", "F2", "F3", "C3", "G1", "G3"))   # covered constructs carry a note
```

- [x] **Step 2: Record — needs the operator's Claude Code login**

Run: `EMBER_RECORD=1 uv run pytest tests/test_observer_recorded.py -v`
Expected: `1 passed` (one live call at effort `high`, ~10–20 s) and one new file in `tests/fixtures/recorded/`.
If the assertion on `signal != "low"` fails, the model is returning too few verbatim quotes: read the recording, tighten the evidence wording in `build_observer_system`, delete the new recording, re-record. Do not loosen the validator.

- [x] **Step 3: Replay**

Run: `uv run pytest tests/test_observer_recorded.py -v`
Expected: `1 passed`, no network.

- [x] **Step 4: Commit**

```bash
git add tests/test_observer_recorded.py tests/fixtures/recorded/
git commit -m "test: recorded observer run on a synthetic seven-turn session" \
  -m "Co-Authored-By: WOZCODE <contact@withwoz.com>" \
  -m "Claude-Session: https://claude.ai/code/session_011xY91ug8K4Ke8JHFsa5ekB"
```

---

### Task 4: Calibration harness

**Files:**
- Create: `ember/calibrate.py`, `calibration/human_scores.yaml`, `tests/test_calibrate.py`

**Interfaces:**
- Consumes: `CONSTRUCTS` (`ember.constructs`).
- Produces: `TARGET_AGREEMENT = 0.8`, `DISAGREE_AT = 2`; `load_human_scores(path: Path) -> dict[str, dict[str, dict[str, int]]]` (session → rater → construct → score); `median_scores(raters: dict[str, dict[str, int]]) -> dict[str, float]`; dataclasses `Disagreement(session_id, construct, observer, human_median, delta)` and `Report(n_scores, n_within_1, disagreements, missing)` with properties `agreement: float`, `passed: bool`; `agreement(observer: dict[str, dict], human: dict) -> Report`; `render(report: Report) -> str`.

- [x] **Step 1: Write the failing tests**

`tests/test_calibrate.py`:
```python
from pathlib import Path
import yaml

from ember.calibrate import load_human_scores, median_scores, agreement, render, Report

ALL = ("F1", "F2", "F3", "C1", "C2", "C3", "G1", "G2", "G3")


def _obs(sid, **scores):
    s = {c: 4 for c in ALL}
    s.update(scores)
    return {"session_id": sid, "constructs": {c: {"score": v, "signal": "med", "evidence": [], "note": ""} for c, v in s.items()}}


def test_load_human_scores_and_median(tmp_path: Path):
    p = tmp_path / "h.yaml"
    p.write_text(yaml.safe_dump({"sessions": {"S01_x": {"malek": {"F1": 5, "F2": 2}, "claude": {"F1": 3, "F2": 4}, "third": {"F1": 4}}}}))
    h = load_human_scores(p)
    assert h["S01_x"]["malek"]["F1"] == 5
    assert median_scores(h["S01_x"]) == {"F1": 4, "F2": 3}


def test_agreement_counts_within_one_and_flags_two_point_gaps():
    human = {"S01_x": {"a": {c: 4 for c in ALL}, "b": {c: 4 for c in ALL}},
             "S02_x": {"a": {c: 4 for c in ALL}}}
    obs = {"S01_x": _obs("S01_x", F1=5, F2=6, G3=1), "S02_x": _obs("S02_x"), "S03_x": _obs("S03_x")}
    rep = agreement(obs, human)
    assert rep.n_scores == 18 and rep.n_within_1 == 16
    assert round(rep.agreement, 3) == round(16 / 18, 3) and rep.passed is True
    assert [(d.construct, d.observer, d.delta) for d in rep.disagreements] == [("F2", 6, 2.0), ("G3", 1, 3.0)]
    assert rep.missing == ["S03_x"]


def test_render_names_pass_fail_and_anchors():
    rep = agreement({"S01_x": _obs("S01_x", F1=7)}, {"S01_x": {"a": {c: 4 for c in ALL}}})
    text = render(rep)
    assert "8/9 within 1 point = 89%" in text and "PASS" in text
    assert "F1  S01_x  observer 7  human median 4  Δ3" in text
    empty = render(Report())
    assert "0/0" in empty and "FAIL" in empty
```

- [x] **Step 2: Run to verify failure**

Run: `uv run pytest tests/test_calibrate.py -v`
Expected: `ModuleNotFoundError: No module named 'ember.calibrate'`

- [x] **Step 3: Implement**

`ember/calibrate.py`:
```python
"""Calibration: observer scores against hand scores (spec §6)."""
import statistics
from dataclasses import dataclass, field
from pathlib import Path

import yaml

from .constructs import CONSTRUCTS

TARGET_AGREEMENT = 0.8
DISAGREE_AT = 2


def load_human_scores(path: Path) -> dict[str, dict[str, dict[str, int]]]:
    data = yaml.safe_load(Path(path).read_text(encoding="utf-8")) or {}
    return {sid: {rater: {c: int(v) for c, v in (scores or {}).items()} for rater, scores in (raters or {}).items()}
            for sid, raters in (data.get("sessions") or {}).items()}


def median_scores(raters: dict[str, dict[str, int]]) -> dict[str, float]:
    out: dict[str, float] = {}
    for c in CONSTRUCTS:
        vals = [r[c] for r in raters.values() if c in r]
        if vals:
            out[c] = statistics.median(vals)
    return out


@dataclass
class Disagreement:
    session_id: str
    construct: str
    observer: int
    human_median: float
    delta: float


@dataclass
class Report:
    n_scores: int = 0
    n_within_1: int = 0
    disagreements: list[Disagreement] = field(default_factory=list)
    missing: list[str] = field(default_factory=list)

    @property
    def agreement(self) -> float:
        return self.n_within_1 / self.n_scores if self.n_scores else 0.0

    @property
    def passed(self) -> bool:
        return self.n_scores > 0 and self.agreement >= TARGET_AGREEMENT


def agreement(observer: dict[str, dict], human: dict[str, dict[str, dict[str, int]]]) -> Report:
    rep = Report()
    for sid in sorted(set(observer) | set(human)):
        if sid not in observer or sid not in human:
            rep.missing.append(sid)
            continue
        for c, m in median_scores(human[sid]).items():
            o = int(observer[sid]["constructs"][c]["score"])
            rep.n_scores += 1
            d = abs(o - m)
            if d <= 1:
                rep.n_within_1 += 1
            if d >= DISAGREE_AT:
                rep.disagreements.append(Disagreement(sid, c, o, m, float(d)))
    return rep


def render(rep: Report) -> str:
    lines = [f"agreement: {rep.n_within_1}/{rep.n_scores} within 1 point = {rep.agreement:.0%}  "
             f"(target {TARGET_AGREEMENT:.0%}) → {'PASS' if rep.passed else 'FAIL'}"]
    if rep.disagreements:
        lines.append(f"\n≥{DISAGREE_AT}-point disagreements — tighten these anchors in ember/bank/rubric.yaml:")
        for c in CONSTRUCTS:
            for d in (x for x in rep.disagreements if x.construct == c):
                lines.append(f"  {c}  {d.session_id}  observer {d.observer}  human median {d.human_median:g}  Δ{d.delta:g}")
    if rep.missing:
        lines.append("\nno observer/human pair for: " + ", ".join(rep.missing))
    return "\n".join(lines)
```

`calibration/human_scores.yaml`:
```yaml
# Hand scores for calibration (spec §6). Score each pilot transcript against ember/bank/rubric.yaml
# BEFORE looking at its observer.json. One block per session id, one map per rater, every construct 1–7.
# Then: uv run ember calibrate
sessions: {}
# example:
# sessions:
#   S01_2026-09-20T14-05-11:
#     malek:  {F1: 5, F2: 4, F3: 6, C1: 3, C2: 2, C3: 5, G1: 4, G2: 3, G3: 5}
#     claude: {F1: 5, F2: 5, F3: 6, C1: 3, C2: 3, C3: 5, G1: 4, G2: 2, G3: 5}
```

- [x] **Step 4: Run to verify pass**

Run: `uv run pytest tests/test_calibrate.py -v`
Expected: `3 passed`

- [x] **Step 5: Commit**

```bash
git add ember/calibrate.py calibration/human_scores.yaml tests/test_calibrate.py
git commit -m "feat: calibration harness — observer vs human-median agreement report" \
  -m "Co-Authored-By: WOZCODE <contact@withwoz.com>" \
  -m "Claude-Session: https://claude.ai/code/session_011xY91ug8K4Ke8JHFsa5ekB"
```

---

### Task 5: Export to `graph/data.js`

**Files:**
- Create: `ember/export.py`, `tests/test_export.py`
- Modify: `.gitignore` (append `graph/data.js`)

**Interfaces:**
- Consumes: `load_results` (Task 1); `Bank` (`ember.bank`); `CONSTRUCTS`, `CLUSTER_OF` (`ember.constructs`); `RUBRIC_VERSION` (`ember.store`).
- Produces: `collect(sessions_root: Path, bank: Bank, *, now: float | None = None) -> dict` with keys `generated_at`, `rubric_version`, `constructs: [{id, cluster, name, inverse}]`, `subjects: [{subject_code, session_id, scored_at, rubric_version, scores: {cid: {score, signal, evidence, note}}, declined, flags, mirror, take_home}]`; `write_data_js(data: dict, out: Path) -> Path`.

- [x] **Step 1: Write the failing tests**

`tests/test_export.py`:
```python
import json
from pathlib import Path

from ember.bank import load_bank
from ember.export import collect, write_data_js

ALL = ("F1", "F2", "F3", "C1", "C2", "C3", "G1", "G2", "G3")


def _session(root: Path, sid: str, code: str, f1: int, mirror: str):
    d = root / sid
    d.mkdir(parents=True)
    (d / "observer.json").write_text(json.dumps({
        "subject_id": code, "session_id": sid, "scored_at": "2026-09-20T10:00:00+00:00", "rubric_version": "1.0.0",
        "constructs": {c: {"score": f1 if c == "F1" else 4, "signal": "med", "evidence": [f"{c} quote"], "note": "n"} for c in ALL},
        "declined": ["G2"], "flags": []}))
    (d / "transcript.json").write_text(json.dumps({"session_id": sid, "subject_code": code, "started_at": 0, "closed": True,
                                                   "mirror": mirror, "take_home": "Why?", "turns": []}))


def test_collect_shapes_subjects_and_constructs(tmp_path: Path):
    _session(tmp_path, "S02_x", "S02", 6, "second")
    _session(tmp_path, "S01_x", "S01", 2, "first")
    (tmp_path / "S03_unscored").mkdir()                                  # no observer.json → excluded
    data = collect(tmp_path, load_bank(), now=1_757_600_000.0)
    assert data["generated_at"].startswith("2025-09-11") and data["rubric_version"] == "1.0.0"
    assert [c["id"] for c in data["constructs"]] == list(ALL)
    assert data["constructs"][2] == {"id": "F3", "cluster": "fire", "name": "Mediocrity tolerance", "inverse": True}
    assert [s["subject_code"] for s in data["subjects"]] == ["S01", "S02"]
    s = data["subjects"][0]
    assert s["scores"]["F1"]["score"] == 2 and s["declined"] == ["G2"] and s["mirror"] == "first" and s["take_home"] == "Why?"


def test_write_data_js_is_a_global_assignment(tmp_path: Path):
    out = write_data_js({"subjects": [], "constructs": []}, tmp_path / "graph" / "data.js")
    text = out.read_text()
    assert text.startswith("window.EMBER_DATA = {") and text.rstrip().endswith("};")
```

- [x] **Step 2: Run to verify failure**

Run: `uv run pytest tests/test_export.py -v`
Expected: `ModuleNotFoundError: No module named 'ember.export'`

- [x] **Step 3: Implement and ignore the generated file**

`ember/export.py`:
```python
"""Fold every observer.json into graph/data.js for the static cohort page (spec §7)."""
import json
import time
from datetime import datetime, timezone
from pathlib import Path

from .bank import Bank
from .constructs import CONSTRUCTS, CLUSTER_OF
from .observer import load_results
from .store import RUBRIC_VERSION


def collect(sessions_root: Path, bank: Bank, *, now: float | None = None) -> dict:
    root = Path(sessions_root)
    subjects = []
    for sid, r in load_results(root).items():
        tr_path = root / sid / "transcript.json"
        tr = json.loads(tr_path.read_text(encoding="utf-8")) if tr_path.exists() else {}
        subjects.append({"subject_code": r["subject_id"], "session_id": sid, "scored_at": r["scored_at"],
                         "rubric_version": r["rubric_version"], "scores": r["constructs"],
                         "declined": r.get("declined", []), "flags": r.get("flags", []),
                         "mirror": tr.get("mirror"), "take_home": tr.get("take_home")})
    subjects.sort(key=lambda s: s["subject_code"])
    ts = datetime.fromtimestamp(now if now is not None else time.time(), tz=timezone.utc).isoformat()
    return {"generated_at": ts, "rubric_version": RUBRIC_VERSION,
            "constructs": [{"id": c, "cluster": CLUSTER_OF[c], "name": bank.rubric[c].name, "inverse": bank.rubric[c].inverse}
                           for c in CONSTRUCTS],
            "subjects": subjects}


def write_data_js(data: dict, out: Path) -> Path:
    out = Path(out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text("window.EMBER_DATA = " + json.dumps(data, ensure_ascii=False, indent=1) + ";\n", encoding="utf-8")
    return out
```

Append to `.gitignore`:
```
graph/data.js
```

- [x] **Step 4: Run to verify pass**

Run: `uv run pytest tests/test_export.py -v`
Expected: `2 passed`

- [x] **Step 5: Commit**

```bash
git add ember/export.py tests/test_export.py .gitignore
git commit -m "feat: export observer results to graph/data.js (git-ignored)" \
  -m "Co-Authored-By: WOZCODE <contact@withwoz.com>" \
  -m "Claude-Session: https://claude.ai/code/session_011xY91ug8K4Ke8JHFsa5ekB"
```

---

### Task 6: The graph page — cohort scatter and subject radar

**Files:**
- Create: `graph/index.html`, `tests/test_graph_static.py`

**Interfaces:**
- Consumes: `graph/data.js` (Task 5's shape).
- Produces: a static page. Element ids used by the test: `cohort`, `subject`, `x-select`, `y-select`, `c-select`, `scatter`, `cohort-table`, `radar`, `evidence`, `tooltip`, `back`.

- [ ] **Step 1: Write the failing test**

`tests/test_graph_static.py`:
```python
from pathlib import Path

HTML = Path(__file__).parent.parent / "graph" / "index.html"


def test_graph_page_is_wired_and_theme_aware():
    src = HTML.read_text(encoding="utf-8")
    assert '<script src="data.js">' in src and "window.EMBER_DATA" in src
    for el in ("cohort", "subject", "x-select", "y-select", "c-select", "scatter", "cohort-table", "radar", "evidence", "tooltip", "back"):
        assert f'id="{el}"' in src, el
    assert "prefers-color-scheme: dark" in src and ':root:not([data-theme="light"])' in src and ':root[data-theme="dark"]' in src
    assert "textContent" in src and "innerHTML" not in src           # untrusted strings never go through innerHTML
    assert "#2a78d6" in src and "#86b6ef" in src and "#0d366b" in src  # slot-1 blue and the ordinal ramp ends
    assert "<table" in src and 'class="legend"' in src
```

- [ ] **Step 2: Run to verify failure**

Run: `uv run pytest tests/test_graph_static.py -v`
Expected: `FileNotFoundError` for `graph/index.html`.

- [ ] **Step 3: Write the page**

`graph/index.html`:
```html
<!doctype html>
<meta charset="utf-8">
<title>ember · cohort</title>
<style>
  :root {
    color-scheme: light;
    --surface: #fcfcfb; --page: #f9f9f7;
    --ink: #0b0b0b; --ink-2: #52514e; --muted: #898781; --grid: #e1e0d9; --axis: #c3c2b7;
    --s1: #2a78d6; --s2: #eb6834; --s3: #1baf7a;
    --r1: #86b6ef; --r2: #3987e5; --r3: #1c5cab; --r4: #0d366b;
  }
  @media (prefers-color-scheme: dark) {
    :root:not([data-theme="light"]) {
      color-scheme: dark;
      --surface: #1a1a19; --page: #0d0d0d;
      --ink: #ffffff; --ink-2: #c3c2b7; --muted: #898781; --grid: #2c2c2a; --axis: #383835;
      --s1: #3987e5; --s2: #d95926; --s3: #199e70;
      --r1: #184f95; --r2: #2a78d6; --r3: #5598e7; --r4: #86b6ef;
    }
  }
  :root[data-theme="dark"] {
    color-scheme: dark;
    --surface: #1a1a19; --page: #0d0d0d;
    --ink: #ffffff; --ink-2: #c3c2b7; --muted: #898781; --grid: #2c2c2a; --axis: #383835;
    --s1: #3987e5; --s2: #d95926; --s3: #199e70;
    --r1: #184f95; --r2: #2a78d6; --r3: #5598e7; --r4: #86b6ef;
  }
  html, body { margin: 0; background: var(--page); color: var(--ink); font: 14px/1.45 system-ui, -apple-system, "Segoe UI", sans-serif; }
  main { max-width: 1100px; margin: 0 auto; padding: 24px; }
  h1 { font-size: 20px; font-weight: 600; margin: 0 0 4px; } h2 { font-size: 16px; font-weight: 600; margin: 24px 0 8px; }
  .sub { color: var(--ink-2); margin: 0 0 16px; }
  section { display: none; } section.on { display: block; }
  .controls { display: flex; gap: 16px; align-items: center; margin: 0 0 12px; flex-wrap: wrap; }
  select { font: inherit; padding: 4px 6px; background: var(--surface); color: var(--ink); border: 1px solid var(--axis); border-radius: 6px; }
  .card { background: var(--surface); border: 1px solid var(--grid); border-radius: 10px; padding: 16px; }
  svg text { fill: var(--ink-2); font-size: 11px; } svg .muted { fill: var(--muted); }
  .legend { display: flex; gap: 20px; align-items: center; color: var(--ink-2); font-size: 12px; margin-top: 8px; flex-wrap: wrap; }
  .swatches span { display: inline-block; width: 14px; height: 14px; margin-right: 2px; vertical-align: middle; border-radius: 2px; }
  table { border-collapse: collapse; width: 100%; margin-top: 16px; font-variant-numeric: tabular-nums; }
  th, td { text-align: left; padding: 6px 8px; border-bottom: 1px solid var(--grid); } th { color: var(--ink-2); font-weight: 500; }
  tr.row { cursor: pointer; } tr.row:hover { background: var(--grid); }
  #tooltip { position: fixed; pointer-events: none; background: var(--surface); color: var(--ink); border: 1px solid var(--axis);
             border-radius: 6px; padding: 6px 8px; font-size: 12px; display: none; box-shadow: 0 2px 8px rgba(0,0,0,.12); }
  .two { display: grid; grid-template-columns: 360px 1fr; gap: 24px; } @media (max-width: 800px) { .two { grid-template-columns: 1fr; } }
  ul { padding-left: 0; list-style: none; margin: 0; } li { margin: 0 0 10px; }
  .cid { font-weight: 600; } .dot { display: inline-block; width: 8px; height: 8px; border-radius: 50%; margin-right: 6px; vertical-align: middle; }
  .q { color: var(--ink-2); display: block; margin-left: 14px; } .q::before { content: "“"; } .q::after { content: "”"; }
  .low { color: var(--muted); } blockquote { margin: 8px 0; padding-left: 12px; border-left: 2px solid var(--axis); color: var(--ink-2); }
  #back { background: none; border: 1px solid var(--axis); color: var(--ink); border-radius: 6px; padding: 4px 10px; font: inherit; cursor: pointer; }
</style>
<main>
  <section id="cohort" class="on">
    <h1>ember · cohort</h1>
    <p class="sub" id="meta"></p>
    <div class="controls">
      <label>x <select id="x-select"></select></label>
      <label>y <select id="y-select"></select></label>
      <label>colour <select id="c-select"></select></label>
    </div>
    <div class="card">
      <svg id="scatter" viewBox="0 0 640 440" width="100%" role="img" aria-label="Cohort scatter"></svg>
      <div class="legend">
        <span>size = signal:</span><span>● low</span><span style="font-size:15px">● med</span><span style="font-size:18px">● high</span>
        <span>colour = <b id="c-name"></b> · 1–2 · 3–4 · 5–6 · 7:</span><span class="swatches" id="ramp"></span>
      </div>
    </div>
    <table id="cohort-table"><thead><tr><th>subject</th><th id="th-x"></th><th id="th-y"></th><th id="th-c"></th><th>declined</th><th>flags</th></tr></thead><tbody></tbody></table>
  </section>

  <section id="subject">
    <p><button id="back">← cohort</button></p>
    <h1 id="s-title"></h1>
    <p class="sub" id="s-meta"></p>
    <div class="two">
      <div class="card"><svg id="radar" viewBox="0 0 360 360" width="100%" role="img" aria-label="Nine-construct radar"></svg>
        <div class="legend"><span>◯ hollow = low signal</span></div></div>
      <div class="card">
        <ul id="evidence"></ul>
        <h2>declined</h2><p id="s-declined" class="low"></p>
        <h2>flags</h2><p id="s-flags" class="low"></p>
        <h2>close</h2><blockquote id="s-mirror"></blockquote><p id="s-takehome"></p>
      </div>
    </div>
  </section>
</main>
<div id="tooltip"></div>
<script src="data.js"></script>
<script>
const D = window.EMBER_DATA || {constructs: [], subjects: []};
const $ = id => document.getElementById(id);
const NS = "http://www.w3.org/2000/svg";
const ORDER = D.constructs.map(c => c.id);
const NAME = Object.fromEntries(D.constructs.map(c => [c.id, c.name]));
const CLUSTER = Object.fromEntries(D.constructs.map(c => [c.id, c.cluster]));
const CLUSTER_VAR = {fire: "--s1", compass: "--s2", ground: "--s3"};
const R = {low: 4, med: 6, high: 8};
const css = v => getComputedStyle(document.documentElement).getPropertyValue(v).trim();
const ramp = () => [1,2,3,4].map(i => css("--r" + i));
const tier = v => v <= 2 ? 0 : v <= 4 ? 1 : v <= 6 ? 2 : 3;          // 1–2 · 3–4 · 5–6 · 7
const el = (tag, attrs = {}, text) => { const e = document.createElementNS(NS, tag); for (const [k, v] of Object.entries(attrs)) e.setAttribute(k, v); if (text != null) e.textContent = text; return e; };
const jitter = (code, k) => { let h = 0; for (const ch of code + k) h = (h * 31 + ch.charCodeAt(0)) >>> 0; return ((h % 1000) / 1000 - 0.5) * 0.3; };
const scoreOf = (s, c) => (s.scores[c] || {}).score || 1;
const sigOf = (s, c) => (s.scores[c] || {}).signal || "low";

function fillSelects() {
  for (const [id, def] of [["x-select", "F1"], ["y-select", "F2"], ["c-select", "C2"]]) {
    const sel = $(id);
    for (const c of ORDER) { const o = document.createElement("option"); o.value = c; o.textContent = `${c} · ${NAME[c]}`; if (c === def) o.selected = true; sel.appendChild(o); }
    sel.addEventListener("change", drawCohort);
  }
}

function drawCohort() {
  const x = $("x-select").value, y = $("y-select").value, c = $("c-select").value;
  const svg = $("scatter"); svg.replaceChildren();
  const P = {l: 44, r: 16, t: 12, b: 36}, W = 640, H = 440;
  const sx = v => P.l + (v - 1) / 6 * (W - P.l - P.r), sy = v => H - P.b - (v - 1) / 6 * (H - P.t - P.b);
  for (let i = 1; i <= 7; i++) {
    svg.appendChild(el("line", {x1: sx(i), x2: sx(i), y1: P.t, y2: H - P.b, stroke: css("--grid"), "stroke-width": 1}));
    svg.appendChild(el("line", {x1: P.l, x2: W - P.r, y1: sy(i), y2: sy(i), stroke: css("--grid"), "stroke-width": 1}));
    svg.appendChild(el("text", {x: sx(i), y: H - P.b + 16, "text-anchor": "middle", class: "muted"}, String(i)));
    svg.appendChild(el("text", {x: P.l - 8, y: sy(i) + 4, "text-anchor": "end", class: "muted"}, String(i)));
  }
  svg.appendChild(el("line", {x1: P.l, x2: W - P.r, y1: H - P.b, y2: H - P.b, stroke: css("--axis")}));
  svg.appendChild(el("line", {x1: P.l, x2: P.l, y1: P.t, y2: H - P.b, stroke: css("--axis")}));
  svg.appendChild(el("text", {x: (P.l + W - P.r) / 2, y: H - 4, "text-anchor": "middle"}, `${x} · ${NAME[x]}`));
  svg.appendChild(el("text", {x: 12, y: (P.t + H - P.b) / 2, transform: `rotate(-90 12 ${(P.t + H - P.b) / 2})`, "text-anchor": "middle"}, `${y} · ${NAME[y]}`));
  const rp = ramp(), surf = css("--surface");
  for (const s of D.subjects) {
    const cx = sx(scoreOf(s, x) + jitter(s.subject_code, "x")), cy = sy(scoreOf(s, y) + jitter(s.subject_code, "y"));
    const sig = [sigOf(s, x), sigOf(s, y)].includes("low") ? "low" : ([sigOf(s, x), sigOf(s, y)].includes("med") ? "med" : "high");
    const g = el("g", {tabindex: 0, role: "button", "aria-label": s.subject_code, style: "cursor:pointer"});
    g.appendChild(el("circle", {cx, cy, r: R[sig], fill: rp[tier(scoreOf(s, c))], stroke: surf, "stroke-width": 2}));
    g.appendChild(el("circle", {cx, cy, r: 12, fill: "transparent"}));                     // ≥24px hit target
    const show = ev => { const t = $("tooltip"); t.replaceChildren(); for (const line of [s.subject_code, `${x} ${scoreOf(s, x)} · ${y} ${scoreOf(s, y)} · ${c} ${scoreOf(s, c)}`, `signal ${sig}`]) { const d = document.createElement("div"); d.textContent = line; t.appendChild(d); } t.style.display = "block"; t.style.left = (ev.clientX + 12) + "px"; t.style.top = (ev.clientY + 12) + "px"; };
    g.addEventListener("pointermove", show); g.addEventListener("focus", () => { const b = g.getBoundingClientRect(); show({clientX: b.left, clientY: b.top}); });
    g.addEventListener("pointerleave", () => $("tooltip").style.display = "none"); g.addEventListener("blur", () => $("tooltip").style.display = "none");
    g.addEventListener("click", () => openSubject(s)); g.addEventListener("keydown", e => { if (e.key === "Enter") openSubject(s); });
    svg.appendChild(g);
  }
  $("c-name").textContent = `${c} · ${NAME[c]}`;
  $("ramp").replaceChildren(...rp.map(h => { const sp = document.createElement("span"); sp.style.background = h; return sp; }));
  $("th-x").textContent = x; $("th-y").textContent = y; $("th-c").textContent = c;
  const tb = $("cohort-table").querySelector("tbody"); tb.replaceChildren();
  for (const s of D.subjects) {
    const tr = document.createElement("tr"); tr.className = "row";
    for (const v of [s.subject_code, `${scoreOf(s, x)} (${sigOf(s, x)})`, `${scoreOf(s, y)} (${sigOf(s, y)})`, `${scoreOf(s, c)} (${sigOf(s, c)})`, s.declined.join(" "), String(s.flags.length)]) {
      const td = document.createElement("td"); td.textContent = v; tr.appendChild(td);
    }
    tr.addEventListener("click", () => openSubject(s)); tb.appendChild(tr);
  }
}

function openSubject(s) {
  $("cohort").classList.remove("on"); $("subject").classList.add("on"); $("tooltip").style.display = "none";
  $("s-title").textContent = s.subject_code; $("s-meta").textContent = `${s.session_id} · scored ${s.scored_at} · rubric ${s.rubric_version}`;
  const svg = $("radar"); svg.replaceChildren();
  const C = 180, RAD = 130, n = ORDER.length, ang = i => -Math.PI / 2 + i * 2 * Math.PI / n;
  const pt = (i, v) => [C + Math.cos(ang(i)) * RAD * v / 7, C + Math.sin(ang(i)) * RAD * v / 7];
  for (const ring of [1, 4, 7]) svg.appendChild(el("polygon", {points: ORDER.map((_, i) => pt(i, ring).join(",")).join(" "), fill: "none", stroke: css("--grid"), "stroke-width": 1}));
  ORDER.forEach((c, i) => {
    const [x2, y2] = pt(i, 7), [lx, ly] = pt(i, 8.2);
    svg.appendChild(el("line", {x1: C, y1: C, x2, y2, stroke: css("--grid"), "stroke-width": 1}));
    svg.appendChild(el("text", {x: lx, y: ly + 4, "text-anchor": "middle"}, c));
  });
  const pts = ORDER.map((c, i) => pt(i, scoreOf(s, c)));
  svg.appendChild(el("polygon", {points: pts.map(p => p.join(",")).join(" "), fill: css("--s1"), "fill-opacity": 0.1, stroke: css("--s1"), "stroke-width": 2}));
  ORDER.forEach((c, i) => {
    const low = sigOf(s, c) === "low";
    svg.appendChild(el("circle", {cx: pts[i][0], cy: pts[i][1], r: 4, fill: low ? css("--surface") : css("--s1"), stroke: low ? css("--s1") : css("--surface"), "stroke-width": 2}));
  });
  const ul = $("evidence"); ul.replaceChildren();
  for (const c of ORDER) {
    const sc = s.scores[c] || {score: "–", signal: "low", evidence: [], note: ""};
    const li = document.createElement("li"); if (sc.signal === "low") li.className = "low";
    const dot = document.createElement("span"); dot.className = "dot"; dot.style.background = css(CLUSTER_VAR[CLUSTER[c]]);
    const head = document.createElement("span"); head.className = "cid"; head.textContent = `${c} · ${NAME[c]} — ${sc.score} · signal ${sc.signal}`;
    li.append(dot, head);
    if (sc.note) { const nt = document.createElement("span"); nt.className = "q"; nt.textContent = sc.note; li.appendChild(nt); }
    for (const q of sc.evidence) { const sp = document.createElement("span"); sp.className = "q"; sp.textContent = q; li.appendChild(sp); }
    ul.appendChild(li);
  }
  $("s-declined").textContent = s.declined.length ? s.declined.join(", ") : "—";
  $("s-flags").textContent = s.flags.length ? s.flags.join(" · ") : "—";
  $("s-mirror").textContent = s.mirror || "—"; $("s-takehome").textContent = s.take_home || "";
}

$("back").addEventListener("click", () => { $("subject").classList.remove("on"); $("cohort").classList.add("on"); });
$("meta").textContent = `${D.subjects.length} subject${D.subjects.length === 1 ? "" : "s"} · generated ${D.generated_at || "—"} · rubric ${D.rubric_version || "—"}`;
fillSelects(); drawCohort();
matchMedia("(prefers-color-scheme: dark)").addEventListener("change", () => { drawCohort(); });
</script>
```

- [ ] **Step 4: Run to verify pass**

Run: `uv run pytest tests/test_graph_static.py -v`
Expected: `1 passed`

- [ ] **Step 5: Render it and look at it (dataviz step 7)**

Run: `uv run python -c "from pathlib import Path; from ember.bank import load_bank; from ember.export import collect, write_data_js; import json, tempfile; d=Path(tempfile.mkdtemp()); [ (d/f'S0{i}_x').mkdir() or (d/f'S0{i}_x'/'observer.json').write_text(json.dumps({'subject_id':f'S0{i}','session_id':f'S0{i}_x','scored_at':'t','rubric_version':'1.0.0','constructs':{c:{'score':(i*3+j)%7+1,'signal':['low','med','high'][(i+j)%3],'evidence':[f'{c} sample quote'],'note':'note'} for j,c in enumerate(['F1','F2','F3','C1','C2','C3','G1','G2','G3'])},'declined':['G2'],'flags':['read G2 by hand']})) for i in range(1,7)]; write_data_js(collect(d, load_bank()), Path('graph/data.js')); print('graph/data.js written with 6 synthetic subjects')" && open graph/index.html`

Check in the browser: six dots with a 2 px ring, hover shows the tooltip, the table lists six rows, click a dot → radar with nine spokes, hollow markers where signal is low, evidence beside it, back returns. Toggle the OS to dark mode: colours swap, ramp flips. If a label collides or overflows, fix it in the HTML before committing.

- [ ] **Step 6: Commit**

```bash
git add graph/index.html tests/test_graph_static.py
git commit -m "feat: static cohort scatter and subject radar page" \
  -m "Co-Authored-By: WOZCODE <contact@withwoz.com>" \
  -m "Claude-Session: https://claude.ai/code/session_011xY91ug8K4Ke8JHFsa5ekB"
```

---

### Task 7: CLI — `observe`, `export`, `calibrate` — and a live run on the real session

**Files:**
- Modify: `ember/cli.py`, `tests/test_cli.py` (append)

**Interfaces:**
- Consumes: `observe_session`, `load_results` (Task 1); `collect`, `write_data_js` (Task 5); `load_human_scores`, `agreement`, `render` (Task 4); `guard_environment`, `LLM` (`ember.llm`); `load_bank`.
- Produces: `ember observe <session_dir>` (exit 0, prints the nine scores); `ember export [--sessions sessions] [--out graph/data.js]`; `ember calibrate [--scores calibration/human_scores.yaml] [--sessions sessions]` (exit 0 on PASS, 1 on FAIL).

- [ ] **Step 1: Append the failing tests**

Append to `tests/test_cli.py`:
```python


def test_cli_help_lists_plan_b_commands():
    out = subprocess.run([sys.executable, "-m", "ember.cli", "--help"], capture_output=True, text=True)
    assert all(cmd in out.stdout for cmd in ("observe", "export", "calibrate"))


def test_cli_export_and_calibrate_on_fixtures(tmp_path, monkeypatch):
    import json, yaml
    from ember.cli import main
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    ALL = ("F1", "F2", "F3", "C1", "C2", "C3", "G1", "G2", "G3")
    d = tmp_path / "sessions" / "S01_x"
    d.mkdir(parents=True)
    (d / "observer.json").write_text(json.dumps({"subject_id": "S01", "session_id": "S01_x", "scored_at": "t", "rubric_version": "1.0.0",
        "constructs": {c: {"score": 4, "signal": "med", "evidence": [], "note": ""} for c in ALL}, "declined": [], "flags": []}))
    out = tmp_path / "graph" / "data.js"
    assert main(["export", "--sessions", str(tmp_path / "sessions"), "--out", str(out)]) == 0
    assert out.read_text().startswith("window.EMBER_DATA")
    scores = tmp_path / "human.yaml"
    scores.write_text(yaml.safe_dump({"sessions": {"S01_x": {"malek": {c: 4 for c in ALL}}}}))
    assert main(["calibrate", "--scores", str(scores), "--sessions", str(tmp_path / "sessions")]) == 0
    scores.write_text(yaml.safe_dump({"sessions": {"S01_x": {"malek": {c: 7 for c in ALL}}}}))
    assert main(["calibrate", "--scores", str(scores), "--sessions", str(tmp_path / "sessions")]) == 1
```

- [ ] **Step 2: Run to verify failure**

Run: `uv run pytest tests/test_cli.py -v`
Expected: the two new tests fail (`observe` not in help; `main` raises on unknown command `export`).

- [ ] **Step 3: Extend the CLI**

Replace `ember/cli.py` with:
```python
"""Command line entry point: serve · observe · export · calibrate."""
import argparse
from pathlib import Path

from .llm import guard_environment


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(prog="ember")
    sub = p.add_subparsers(dest="cmd", required=True)

    s = sub.add_parser("serve", help="run the interview server")
    s.add_argument("--port", type=int, default=8765)
    s.add_argument("--sessions", type=Path, default=Path("sessions"))
    s.add_argument("--no-warm", action="store_true", help="skip loading the whisper model at start (tests)")

    o = sub.add_parser("observe", help="score a session's transcript.json → observer.json (uses your Claude subscription)")
    o.add_argument("session_dir", type=Path)

    e = sub.add_parser("export", help="fold every observer.json into graph/data.js")
    e.add_argument("--sessions", type=Path, default=Path("sessions"))
    e.add_argument("--out", type=Path, default=Path("graph/data.js"))

    c = sub.add_parser("calibrate", help="compare observer scores with hand scores")
    c.add_argument("--scores", type=Path, default=Path("calibration/human_scores.yaml"))
    c.add_argument("--sessions", type=Path, default=Path("sessions"))

    args = p.parse_args(argv)

    if args.cmd == "serve":
        guard_environment()                       # exits if ANTHROPIC_API_KEY is set; strips CLAUDE* vars
        import uvicorn
        from .bank import load_bank
        from .engine import Engine
        from .llm import LLM
        from .server import create_app
        from .store import SessionStore
        from .stt import Transcriber

        transcriber = Transcriber()
        if not args.no_warm:
            print(f"loading whisper… {transcriber.warm():.1f}s")
        app = create_app(SessionStore(args.sessions), Engine(load_bank(), LLM()), transcriber)
        if args.port == 0:
            return 0
        print(f"subject:  http://127.0.0.1:{args.port}/\noperator: http://127.0.0.1:{args.port}/operator")
        uvicorn.run(app, host="127.0.0.1", port=args.port, log_level="warning")
        return 0

    if args.cmd == "observe":
        guard_environment()
        import json
        from .bank import load_bank
        from .llm import LLM
        from .observer import observe_session

        out = observe_session(args.session_dir, load_bank(), LLM())
        r = json.loads(out.read_text(encoding="utf-8"))
        print(f"wrote {out}")
        for cid, cs in r["constructs"].items():
            print(f"  {cid}  {cs['score']}  {cs['signal']:4s}  {cs['note'][:70]}")
        if r["declined"]:
            print("  declined:", ", ".join(r["declined"]))
        for f in r["flags"]:
            print("  flag:", f)
        return 0

    if args.cmd == "export":
        from .bank import load_bank
        from .export import collect, write_data_js

        data = collect(args.sessions, load_bank())
        out = write_data_js(data, args.out)
        print(f"{len(data['subjects'])} subject(s) → {out}   (open graph/index.html)")
        return 0

    if args.cmd == "calibrate":
        from .calibrate import agreement, load_human_scores, render
        from .observer import load_results

        rep = agreement(load_results(args.sessions), load_human_scores(args.scores))
        print(render(rep))
        return 0 if rep.passed else 1

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
```

- [ ] **Step 4: Run to verify pass, then the full suite**

Run: `uv run pytest tests/test_cli.py -v && uv run pytest -q`
Expected: `4 passed` for the CLI file; the full suite passes (Plan A's 73 + Plan B's new tests).

- [ ] **Step 5: Live run on the operator's real session — operator verification**

Run: `uv run ember observe sessions/S00_2026-09-11T12-46-27 && uv run ember export && open graph/index.html`
Expected: nine lines of scores with notes; `observer.json` written next to that session's `transcript.json`; the graph shows one subject (plus `TEST` if `ember observe sessions/TEST_2026-09-11T12-32-26` is run too). The operator reads the evidence against their own memory of the session — this is the first sanity check of the rubric on real speech. Anything obviously wrong is a rubric-anchor or prompt problem: note it in `calibration/human_scores.yaml` comments for the pilot round; do not tune on one session.

- [ ] **Step 6: Commit**

```bash
git add ember/cli.py tests/test_cli.py
git commit -m "feat: ember observe / export / calibrate commands" \
  -m "Co-Authored-By: WOZCODE <contact@withwoz.com>" \
  -m "Claude-Session: https://claude.ai/code/session_011xY91ug8K4Ke8JHFsa5ekB"
```

---

### Task 8: Pilot protocol and hand-scoring sheets

**Files:**
- Create: `docs/pilot-protocol.md`, `calibration/pilot_log.yaml`, `tests/test_docs.py`

**Interfaces:**
- Produces: the written procedure for the five pilots (spec §10 craft measures, §6 calibration loop) and the go/no-go for the 40.

- [ ] **Step 1: Write the failing test**

`tests/test_docs.py`:
```python
from pathlib import Path
import yaml

ROOT = Path(__file__).parent.parent


def test_pilot_protocol_covers_the_spec_measures():
    doc = (ROOT / "docs" / "pilot-protocol.md").read_text(encoding="utf-8")
    for needle in ("Did you say anything you hadn't put into words before?", "Still thinking about the last question?",
                   "3/5", "ember observe", "ember calibrate", "80", "human_scores.yaml", "pilot_log.yaml", "rubric_version"):
        assert needle in doc, needle


def test_pilot_log_template_parses():
    data = yaml.safe_load((ROOT / "calibration" / "pilot_log.yaml").read_text(encoding="utf-8"))
    assert data == {"pilots": {}}
```

- [ ] **Step 2: Run to verify failure**

Run: `uv run pytest tests/test_docs.py -v`
Expected: `FileNotFoundError` for `docs/pilot-protocol.md`.

- [ ] **Step 3: Write the protocol and the log template**

`docs/pilot-protocol.md`:
```markdown
# ember — pilot protocol

Five pilot sessions before the cohort of ~40 (spec §10, §6). Everything below is run by the operator.

## Before the first pilot
1. Bank reviewed: every line of `ember/bank/questions.yaml`, `opener.yaml`, `rubric.yaml` read and approved.
2. `uv run pytest -q` green.
3. Room: quiet, subject alone with the laptop and a decent mic; operator seated behind, silent.
4. Chrome. Start the server from a plain terminal: `uv run ember serve` — wait for `loading whisper… N s`.
5. Open http://127.0.0.1:8765/ on the subject's screen and http://127.0.0.1:8765/operator on the operator's.

## Each session
1. Assign a subject code (`S01`…`S40`). No names anywhere.
2. Subject reads the three consent lines, enters the code, starts, allows the mic.
3. Operator is silent. Watch the operator page; do not intervene. Notes go in `sessions/<id>/meta.json` → `operator_notes` afterwards.
4. The session closes itself at ~6:30. The mirror and take-home stay on screen; let the subject sit with it. Say nothing about the questions.
5. Immediately after, ask exactly: **"Did you say anything you hadn't put into words before?"** Record yes/no in `calibration/pilot_log.yaml`.

## 24 hours later
Message the subject: **"Still thinking about the last question?"** Record yes/no in `calibration/pilot_log.yaml`.

## After the five pilots
1. Score each transcript by hand **before** running the observer: read `sessions/<id>/transcript.json` against `ember/bank/rubric.yaml`, one 1–7 per construct, into `calibration/human_scores.yaml` (one map per rater — operator, and a second rater if available).
2. `uv run ember observe sessions/<id>` for each pilot.
3. `uv run ember calibrate` — target **80 %** of construct scores within 1 point of the human median.
4. Every ≥ 2-point disagreement names a construct: tighten that construct's anchors in `rubric.yaml` (sharper description, a better exemplar), bump `RUBRIC_VERSION` in `ember/store.py`, re-run `ember observe` on the five, re-run `calibrate`. Repeat until it passes.
5. `uv run ember export` and open `graph/index.html` — read the five as people, not as scores. If the take-homes felt earned in the room but the radar shape looks wrong, the rubric is the problem, not the session.

## Go / no-go for the 40
- ≥ **3/5** "yes" on the immediate question **and** ≥ **3/5** "yes" on the 24-hour question, **and**
- `ember calibrate` passes at the current `rubric_version`.
If either fails: revise the bank or the rubric, run two more pilots, re-evaluate. Do not scale a loop that does not produce the effect.

## The 40
- Max 5x plan: keep to **≤ 15 sessions per day**, spread over three days, so the 5-hour usage windows never bite mid-session.
- Same room, same mic, same operator posture.
- `ember observe` each session the same day; `ember export` at the end of each day.
- Deletion on request: `rm -rf sessions/<id>` and delete the row from `ember.sqlite` (`sqlite3 ember.sqlite "delete from sessions where session_id='<id>'"`); re-run `ember export`.

## What is never committed
`sessions/`, `ember.sqlite`, `graph/data.js`. The hand-score and pilot-log YAMLs carry subject codes only.
```

`calibration/pilot_log.yaml`:
```yaml
# The two craft measures (spec §10), one entry per pilot subject code.
# immediate: asked right after the session — "Did you say anything you hadn't put into words before?"
# day_after: asked ~24 h later by message — "Still thinking about the last question?"
pilots: {}
# example:
# pilots:
#   S01: {session_id: S01_2026-09-20T14-05-11, immediate: yes, day_after: no, notes: "long pause before G1"}
```

- [ ] **Step 4: Run to verify pass, then the full suite**

Run: `uv run pytest tests/test_docs.py -v && uv run pytest -q`
Expected: `2 passed`; full suite green.

- [ ] **Step 5: Commit**

```bash
git add docs/pilot-protocol.md calibration/pilot_log.yaml tests/test_docs.py
git commit -m "docs: pilot protocol, hand-scoring and pilot-log templates" \
  -m "Co-Authored-By: WOZCODE <contact@withwoz.com>" \
  -m "Claude-Session: https://claude.ai/code/session_011xY91ug8K4Ke8JHFsa5ekB"
```

---

## After this plan

Spec §13 step 6 (the five pilots) and step 7 (the 40) are human work run from `docs/pilot-protocol.md`. Nothing further is built until the pilots say the loop produces the effect.
