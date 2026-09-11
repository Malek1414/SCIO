# ember v1 — Interview Loop Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** A working 5–8 minute voice-answered interview: question on screen → subject speaks → local STT → engine picks the next question → mirror + take-home close, with every session written to disk in the format the observer (Plan B) will read.

**Architecture:** Hand-crafted question bank (YAML) + deterministic guards + a Claude Agent SDK call that only *chooses* spine questions and *writes* short probes and the close. FastAPI serves one subject page and one operator page; `mlx_whisper` transcribes in-process. Session state is a dataclass persisted per turn to a session folder; `transcript.json` contains Q/A only and is the sole observer input.

**Tech Stack:** Python 3.12 (`uv`), `claude-agent-sdk` ≥ 0.2.152 (subscription auth), `mlx-whisper` 0.4.3, FastAPI + uvicorn, pydantic v2, PyYAML, SQLite (stdlib), pytest, ffmpeg (already installed at `/opt/homebrew/bin/ffmpeg`).

**Spec:** `docs/superpowers/specs/2026-09-11-ember-v1-design.md`. This plan covers spec build steps 1–3 (bank, engine, live loop). Plan B covers steps 4–5 (observer, graph).

## Global Constraints

Copied from the spec. Every task's requirements include these.

- **Python:** `requires-python = ">=3.12,<3.13"`; `.python-version` = `3.12`. All commands run as `uv run …`. System Python is 3.14 and is *not* used.
- **LLM backend:** `claude-agent-sdk`, one-shot `query()`. Options on every call: `model="opus"`, `fallback_model="sonnet"`, `thinking={"type": "adaptive"}`, `output_format={"type": "json_schema", "schema": …}`, `tools=[]`, `max_turns=2`, `setting_sources=[]`, `mcp_servers={}`, `strict_mcp_config=True`. Effort `low` for per-turn picks, `high` for the close.
- **Environment guard:** the process exits with a message if `ANTHROPIC_API_KEY` is set; it strips every env var starting with `CLAUDE` at startup.
- **LLM call bounds:** 15 s timeout per attempt, one retry, then the slot's default candidate (spec §9).
- **No API-key code path.** There is no `anthropic` package dependency.
- **Time guards (seconds):** probe window closes at 240; Fire guard at 270 (slot ≤ 4 → jump to 5); Q7 gate at 345; hard close at 390; silence rephrase at 25.
- **Counts:** max 2 probes/session; probe needs last answer ≥ 15 words; STT answer < 5 words = retry, max 2 retries then skip.
- **Probe text:** ≤ 12 words total, must contain a `"double-quoted"` phrase of 3–6 words that appears verbatim (case-insensitive, punctuation-stripped) in the last answer, must not end with `?`.
- **Close:** mirror is a verbatim ≥ 5-word substring of the transcript; take-home ≤ 20 words and ends with `?`. Fallback: longest sentence from any Fire-slot answer + `opener.fallback_take_home`.
- **Slot rules:** slot 1 = fixed opener, no LLM. Slots 2–6 each have ≥ 3 candidates and exactly one `default: true`. Slot 7 draws from unused slot-5/6 candidates. Slot-2 candidates have empty `prerequisites`. Threat monotonicity applies within Fire (slots 2–4) only. No question text starts with a yes/no auxiliary.
- **STT:** `mlx-community/whisper-large-v3-turbo`, 16 kHz mono WAV, model loaded once and held in memory. Browser sends webm; server converts with ffmpeg.
- **Storage:** `sessions/<session_id>/` with `meta.json`, `session.json`, `transcript.json` (Q/A + timestamps only), `engine_log.json`, `audio/qN.wav`. `sessions/` is git-ignored. `ember.sqlite` at repo root indexes sessions.
- **Subject screen:** shows no transcript, no timer. Operator screen is a separate URL.
- **Commits:** every commit message ends with the two trailer lines shown in Task 1 Step 6. Use them verbatim on every commit.

---

## File Structure

```
ember/                                 repo root (already exists, git initialised)
  pyproject.toml                       project + deps + pytest config + `ember` script
  .python-version                      3.12
  .gitignore
  ember/
    __init__.py
    constructs.py                      construct ids, clusters, tag + framing vocab, signal_for()
    text.py                            normalize, word_count, contains_verbatim, extract_quote, longest_sentence
    bank.py                            pydantic models + load_bank(); all bank validation lives here
    bank/opener.yaml                   Q1 + rephrase + fallback take-home
    bank/questions.yaml                21 spine candidates
    bank/rubric.yaml                   3 anchors × 9 constructs (consumed by Plan B; validated here)
    session.py                         Turn, Session dataclasses; JSON round-trip; derived accessors
    guards.py                          all deterministic thresholds and filters
    llm.py                             LLM wrapper over claude-agent-sdk; guard_environment()
    engine.py                          Action/CloseOut/Next; prompts; Engine.first/next/close
    stt.py                             Transcriber (warm, transcribe), to_wav
    store.py                           SessionStore: folders, JSON files, SQLite index
    server.py                          FastAPI app factory + routes
    static/subject.html                consent → question → hold-space → close
    static/operator.html               polling status view
    cli.py                             `ember serve`
  tests/
    conftest.py                        mini bank on disk, FakeLLM, make_session()
    test_constructs.py … test_server.py, test_cli.py
    fixtures/transcripts/*.json        hand-written partial sessions for the recorded-API suite
    fixtures/recorded/*.json           recorded LLM responses (committed)
```

Each module has one responsibility and is testable without the ones below it. Dependency direction: `constructs ← text ← bank ← session ← guards ← llm ← engine ← stt ← store ← server ← cli`.

---

### Task 1: Project scaffold

**Files:**
- Create: `pyproject.toml`, `.python-version`, `.gitignore`, `ember/__init__.py`, `tests/__init__.py`, `tests/test_scaffold.py`

**Interfaces:**
- Produces: a `uv`-managed venv in which `uv run pytest` works and `import ember`, `import claude_agent_sdk`, `import mlx_whisper` all succeed.

- [x] **Step 1: Write the failing test**

`tests/test_scaffold.py`:
```python
import importlib


def test_project_imports():
    for mod in ("ember", "claude_agent_sdk", "mlx_whisper", "fastapi", "pydantic", "yaml"):
        importlib.import_module(mod)
```

- [x] **Step 2: Run it to verify it fails**

Run: `cd ~/Desktop/ember && uv run pytest tests/test_scaffold.py -v`
Expected: fails — `uv` has no `pyproject.toml` to resolve, or `ModuleNotFoundError: ember`.

- [x] **Step 3: Create the project files**

`pyproject.toml`:
```toml
[project]
name = "ember"
version = "0.1.0"
description = "Maieutic voice interview with a decoupled diagnostic observer"
requires-python = ">=3.12,<3.13"
dependencies = [
    "claude-agent-sdk>=0.2.152",
    "mlx-whisper>=0.4.3",
    "fastapi>=0.115",
    "uvicorn>=0.30",
    "python-multipart>=0.0.9",
    "pydantic>=2.7",
    "pyyaml>=6",
    "numpy>=1.26",
]

[project.scripts]
ember = "ember.cli:main"

[dependency-groups]
dev = ["pytest>=8", "httpx>=0.27"]

[build-system]
requires = ["hatchling"]
build-backend = "hatchling.build"

[tool.hatch.build.targets.wheel]
packages = ["ember"]

[tool.pytest.ini_options]
testpaths = ["tests"]
markers = [
    "slow: loads the whisper model or runs ffmpeg",
    "api: calls the Claude Agent SDK unless recordings exist",
]
```

`.python-version`:
```
3.12
```

`.gitignore`:
```
.venv/
__pycache__/
*.pyc
sessions/
ember.sqlite
tests/fixtures/audio/
.env
```

`ember/__init__.py`:
```python
"""ember — maieutic voice interview."""
__version__ = "0.1.0"
```

`tests/__init__.py`: empty file.

- [x] **Step 4: Sync and run the test**

Run: `cd ~/Desktop/ember && uv python pin 3.12 && uv sync && uv run pytest tests/test_scaffold.py -v`
Expected: `1 passed`. (First `uv sync` downloads mlx-whisper and the 82 MB claude-agent-sdk; allow a minute.)

- [x] **Step 5: Confirm the venv is on 3.12**

Run: `uv run python --version`
Expected: `Python 3.12.x`

- [x] **Step 6: Commit**

```bash
git add pyproject.toml .python-version .gitignore uv.lock ember/__init__.py tests/__init__.py tests/test_scaffold.py
git commit -m "chore: scaffold ember project on Python 3.12 with uv" \
  -m "Co-Authored-By: WOZCODE <contact@withwoz.com>" \
  -m "Claude-Session: https://claude.ai/code/session_011xY91ug8K4Ke8JHFsa5ekB"
```

---

### Task 2: Constructs, tags, framings, signal rule

**Files:**
- Create: `ember/constructs.py`, `tests/test_constructs.py`

**Interfaces:**
- Produces: `CLUSTERS: dict[str, tuple[str, ...]]`, `CONSTRUCTS: tuple[str, ...]`, `CLUSTER_OF: dict[str, str]`, `TAGS: frozenset[str]`, `FRAMINGS: frozenset[str]`, `signal_for(n_quotes: int, n_distinct_answers: int, skipped: bool) -> str`.

- [x] **Step 1: Write the failing tests**

`tests/test_constructs.py`:
```python
from ember.constructs import CLUSTERS, CONSTRUCTS, CLUSTER_OF, TAGS, FRAMINGS, signal_for


def test_nine_constructs_in_three_clusters():
    assert CONSTRUCTS == ("F1", "F2", "F3", "C1", "C2", "C3", "G1", "G2", "G3")
    assert set(CLUSTERS) == {"fire", "compass", "ground"}
    assert CLUSTER_OF["F2"] == "fire" and CLUSTER_OF["G3"] == "ground"


def test_tag_and_framing_vocab():
    assert "named-project" in TAGS and "faith" in TAGS
    assert "cost-already-paid" in FRAMINGS and "empty-room" in FRAMINGS


def test_signal_thresholds():
    assert signal_for(0, 0, False) == "low"
    assert signal_for(1, 1, False) == "low"
    assert signal_for(2, 1, False) == "med"
    assert signal_for(3, 1, False) == "med"        # 3 quotes but one answer
    assert signal_for(3, 2, False) == "high"
    assert signal_for(5, 3, True) == "low"         # skipped always low
```

- [x] **Step 2: Run to verify failure**

Run: `uv run pytest tests/test_constructs.py -v`
Expected: `ModuleNotFoundError: No module named 'ember.constructs'`

- [x] **Step 3: Implement**

`ember/constructs.py`:
```python
"""Construct ids, clusters, controlled vocabularies, and the signal rule (spec §3, §5.3)."""

CLUSTERS: dict[str, tuple[str, ...]] = {
    "fire": ("F1", "F2", "F3"),
    "compass": ("C1", "C2", "C3"),
    "ground": ("G1", "G2", "G3"),
}
CONSTRUCTS: tuple[str, ...] = tuple(c for cs in CLUSTERS.values() for c in cs)
CLUSTER_OF: dict[str, str] = {c: k for k, cs in CLUSTERS.items() for c in cs}

# Engine-internal tags. The observer never sees these.
TAGS: frozenset[str] = frozenset({
    "named-project", "family", "money", "health", "loss", "faith",
    "relationship", "solitude", "quit", "moved", "failure", "competition",
})

TAG_HINTS: dict[str, str] = {
    "named-project": "a specific thing they are building or working on",
    "family": "parents, siblings, children, family expectations",
    "money": "money, income, financial pressure or freedom",
    "health": "physical or mental health, their own or someone close",
    "loss": "a death, a breakup, losing something that mattered",
    "faith": "religion, God, spiritual practice or belief",
    "relationship": "a partner, close friend, or specific named person",
    "solitude": "being alone, loneliness, time by themselves",
    "quit": "quitting or leaving something — job, degree, city, project",
    "moved": "moving country or city",
    "failure": "something they tried that did not work",
    "competition": "rivalry, comparison to peers, being measured against others",
}

FRAMINGS: frozenset[str] = frozenset({
    "third-person-projection", "counterfactual-removal", "envy-locator",
    "cost-already-paid", "settled-person-read", "pressure-decision",
    "scale-of-things", "fear-of-self", "empty-room", "aftermath-not-event",
    "people-as", "discrepancy", "forking",
})


def signal_for(n_quotes: int, n_distinct_answers: int, skipped: bool) -> str:
    """Spec §3: low <2 quotes or skipped; high ≥3 quotes from ≥2 answers; else med."""
    if skipped or n_quotes < 2:
        return "low"
    if n_quotes >= 3 and n_distinct_answers >= 2:
        return "high"
    return "med"
```

- [x] **Step 4: Run to verify pass**

Run: `uv run pytest tests/test_constructs.py -v`
Expected: `3 passed`

- [x] **Step 5: Commit**

```bash
git add ember/constructs.py tests/test_constructs.py
git commit -m "feat: construct model, tag and framing vocab, signal rule" \
  -m "Co-Authored-By: WOZCODE <contact@withwoz.com>" \
  -m "Claude-Session: https://claude.ai/code/session_011xY91ug8K4Ke8JHFsa5ekB"
```

---

### Task 3: Text utilities — verbatim matching

**Files:**
- Create: `ember/text.py`, `tests/test_text.py`

**Interfaces:**
- Produces: `normalize(s: str) -> list[str]`, `word_count(s: str) -> int`, `contains_verbatim(haystack: str, needle: str, *, min_words: int, max_words: int | None = None) -> bool`, `extract_quote(text: str) -> str | None`, `longest_sentence(text: str) -> str`.

- [x] **Step 1: Write the failing tests**

`tests/test_text.py`:
```python
from ember.text import normalize, word_count, contains_verbatim, extract_quote, longest_sentence

ANSWER = "Honestly, I couldn't stop. I rebuilt the whole backend three times — nobody asked me to."


def test_normalize_strips_punctuation_and_case():
    assert normalize("I couldn't STOP.") == ["i", "couldn't", "stop"]


def test_word_count():
    assert word_count(ANSWER) == 15


def test_contains_verbatim_hit_and_bounds():
    assert contains_verbatim(ANSWER, "I couldn't stop", min_words=3, max_words=6)
    assert contains_verbatim(ANSWER, "rebuilt the whole backend three times", min_words=3, max_words=6)
    assert not contains_verbatim(ANSWER, "couldn't stop", min_words=3, max_words=6)        # too short
    assert not contains_verbatim(ANSWER, "I rebuilt the whole backend three times", min_words=3, max_words=6)  # 7 words
    assert not contains_verbatim(ANSWER, "I could not stop", min_words=3, max_words=6)     # not verbatim
    assert contains_verbatim(ANSWER, "nobody asked me to", min_words=3)                   # no max


def test_extract_quote_double_and_curly():
    assert extract_quote('You said "I couldn\'t stop."') == "I couldn't stop."
    assert extract_quote("You said “nobody asked me to”.") == "nobody asked me to"
    assert extract_quote("You said it plainly.") is None


def test_longest_sentence():
    assert longest_sentence(ANSWER) == "I rebuilt the whole backend three times — nobody asked me to"
    assert longest_sentence("") == ""
```

- [x] **Step 2: Run to verify failure**

Run: `uv run pytest tests/test_text.py -v`
Expected: `ModuleNotFoundError: No module named 'ember.text'`

- [x] **Step 3: Implement**

`ember/text.py`:
```python
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
```

- [x] **Step 4: Run to verify pass**

Run: `uv run pytest tests/test_text.py -v`
Expected: `5 passed`

- [x] **Step 5: Commit**

```bash
git add ember/text.py tests/test_text.py
git commit -m "feat: verbatim matcher, quote extraction, sentence helper" \
  -m "Co-Authored-By: WOZCODE <contact@withwoz.com>" \
  -m "Claude-Session: https://claude.ai/code/session_011xY91ug8K4Ke8JHFsa5ekB"
```

---

### Task 4: Bank schema and loader

**Files:**
- Create: `ember/bank.py`, `tests/conftest.py`, `tests/test_bank.py`

**Interfaces:**
- Consumes: `CONSTRUCTS`, `CLUSTER_OF`, `TAGS`, `FRAMINGS` from Task 2.
- Produces: pydantic models `Candidate`, `Opener`, `Anchor`, `RubricEntry`, `Bank`; `Bank.for_slot(slot: int, used: set[str] = frozenset()) -> list[Candidate]`, `Bank.default_for(slot: int, used: set[str] = frozenset()) -> Candidate | None`, `Bank.by_id(cid: str) -> Candidate`; `load_bank(dir: Path) -> Bank`; `BANK_DIR: Path`.
- Test fixtures: `mini_bank_dir` (tmp path with valid YAMLs), `mini_bank`.

- [x] **Step 1: Write the shared fixtures**

`tests/conftest.py`:
```python
from pathlib import Path
import pytest
import yaml

from ember.constructs import CONSTRUCTS


def write_mini_bank(d: Path) -> None:
    """A minimal valid bank: 3 candidates per slot 2–6, one default each, all 9 rubric entries."""
    opener = {
        "text": "Think of someone you know who's clearly going to make it. What do they do differently?",
        "rephrase": "Someone you know who's going to make it. What's different about them?",
        "fallback_take_home": "What would you have to stop doing to become that person?",
    }
    cluster = {2: "fire", 3: "fire", 4: "fire", 5: "compass", 6: "ground"}
    target = {2: "F1", 3: "F2", 4: "F3", 5: "C1", 6: "G1"}
    cands = []
    for slot in range(2, 7):
        for i, letter in enumerate("abc"):
            cands.append({
                "id": f"S{slot}-{letter}", "slot": slot, "cluster": cluster[slot],
                "targets": [target[slot]], "threat": min(7, slot + i),
                "framing": "counterfactual-removal",
                "prerequisites": [] if (slot == 2 or letter != "c") else ["family"],
                "default": letter == "a",
                "text": f"What happens at slot {slot} option {letter}?",
                "rephrase": f"What is slot {slot} option {letter} like?",
            })
    rubric = [{
        "construct": c, "name": f"Construct {c}", "inverse": c == "F3",
        "anchors": [{"score": s, "description": f"{c} level {s}", "exemplar": f"{c} example {s}"} for s in (1, 4, 7)],
    } for c in CONSTRUCTS]
    (d / "opener.yaml").write_text(yaml.safe_dump(opener, sort_keys=False))
    (d / "questions.yaml").write_text(yaml.safe_dump({"candidates": cands}, sort_keys=False))
    (d / "rubric.yaml").write_text(yaml.safe_dump({"rubric": rubric}, sort_keys=False))


@pytest.fixture
def mini_bank_dir(tmp_path: Path) -> Path:
    d = tmp_path / "bank"
    d.mkdir()
    write_mini_bank(d)
    return d


@pytest.fixture
def mini_bank(mini_bank_dir):
    from ember.bank import load_bank
    return load_bank(mini_bank_dir)
```

- [x] **Step 2: Write the failing tests**

`tests/test_bank.py`:
```python
from pathlib import Path
import pytest
import yaml
from pydantic import ValidationError

from ember.bank import Candidate, Bank, load_bank
from tests.conftest import write_mini_bank


def test_load_mini_bank(mini_bank):
    assert mini_bank.opener.text.startswith("Think of someone")
    assert len(mini_bank.candidates) == 15
    assert set(mini_bank.rubric) == {"F1", "F2", "F3", "C1", "C2", "C3", "G1", "G2", "G3"}


def test_for_slot_and_default(mini_bank):
    assert [c.id for c in mini_bank.for_slot(3)] == ["S3-a", "S3-b", "S3-c"]
    assert mini_bank.default_for(3).id == "S3-a"
    assert mini_bank.by_id("S5-b").cluster == "compass"


def test_slot7_draws_unused_5_and_6(mini_bank):
    ids = {c.id for c in mini_bank.for_slot(7, used={"S5-a", "S6-b"})}
    assert ids == {"S5-b", "S5-c", "S6-a", "S6-c"}
    assert mini_bank.default_for(7, used={"S6-a"}).id == "S5-a"
    assert mini_bank.default_for(7, used={"S5-a", "S5-b", "S5-c", "S6-a", "S6-b", "S6-c"}) is None


def _cand(**over):
    base = dict(id="X", slot=3, cluster="fire", targets=["F2"], threat=5, framing="cost-already-paid",
                prerequisites=[], default=False, text="What did it cost you?", rephrase="What was the cost?")
    base.update(over)
    return base


def test_candidate_rejects_yes_no_question():
    with pytest.raises(ValidationError, match="yes/no"):
        Candidate(**_cand(text="Do you regret it?"))


def test_candidate_rejects_cluster_target_mismatch():
    with pytest.raises(ValidationError, match="cluster"):
        Candidate(**_cand(cluster="compass"))


def test_candidate_rejects_unknown_tag_or_framing():
    with pytest.raises(ValidationError):
        Candidate(**_cand(prerequisites=["astrology"]))
    with pytest.raises(ValidationError):
        Candidate(**_cand(framing="mind-reading"))


def test_slot2_prerequisites_must_be_empty():
    with pytest.raises(ValidationError, match="slot 2"):
        Candidate(**_cand(slot=2, targets=["F1"], prerequisites=["money"]))


def test_bank_requires_one_default_per_slot(tmp_path: Path):
    write_mini_bank(tmp_path)
    q = yaml.safe_load((tmp_path / "questions.yaml").read_text())
    for c in q["candidates"]:
        if c["id"] == "S4-b":
            c["default"] = True
    (tmp_path / "questions.yaml").write_text(yaml.safe_dump(q))
    with pytest.raises(ValidationError, match="slot 4"):
        load_bank(tmp_path)


def test_bank_requires_three_candidates_per_slot(tmp_path: Path):
    write_mini_bank(tmp_path)
    q = yaml.safe_load((tmp_path / "questions.yaml").read_text())
    q["candidates"] = [c for c in q["candidates"] if c["id"] != "S6-c"]
    (tmp_path / "questions.yaml").write_text(yaml.safe_dump(q))
    with pytest.raises(ValidationError, match="slot 6"):
        load_bank(tmp_path)
```

- [x] **Step 3: Run to verify failure**

Run: `uv run pytest tests/test_bank.py -v`
Expected: `ModuleNotFoundError: No module named 'ember.bank'`

- [x] **Step 4: Implement**

`ember/bank.py`:
```python
"""Question bank: schema, validation rules (spec §5.1, §5.2), loader."""
from pathlib import Path
from typing import Iterable

import yaml
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from .constructs import CONSTRUCTS, CLUSTER_OF, TAGS, FRAMINGS

BANK_DIR = Path(__file__).parent / "bank"

YES_NO_STARTS = ("do ", "does ", "did ", "are ", "is ", "was ", "were ", "have ", "has ", "had ",
                 "can ", "could ", "will ", "would ", "should ")


def _open_question(text: str) -> str:
    if text.strip().lower().startswith(YES_NO_STARTS):
        raise ValueError(f"yes/no question not allowed: {text[:50]!r}")
    return text


class Candidate(BaseModel):
    id: str
    slot: int = Field(ge=2, le=6)
    cluster: str
    targets: list[str] = Field(min_length=1)
    threat: int = Field(ge=1, le=7)
    framing: str
    prerequisites: list[str] = Field(default_factory=list)
    default: bool = False
    text: str
    rephrase: str

    @field_validator("targets")
    @classmethod
    def _targets_known(cls, v: list[str]) -> list[str]:
        bad = [t for t in v if t not in CONSTRUCTS]
        if bad:
            raise ValueError(f"unknown construct(s) {bad}")
        return v

    @field_validator("prerequisites")
    @classmethod
    def _tags_known(cls, v: list[str]) -> list[str]:
        bad = [t for t in v if t not in TAGS]
        if bad:
            raise ValueError(f"unknown tag(s) {bad}")
        return v

    @field_validator("framing")
    @classmethod
    def _framing_known(cls, v: str) -> str:
        if v not in FRAMINGS:
            raise ValueError(f"unknown framing {v!r}")
        return v

    @field_validator("text", "rephrase")
    @classmethod
    def _open(cls, v: str) -> str:
        return _open_question(v)

    @model_validator(mode="after")
    def _consistency(self) -> "Candidate":
        for t in self.targets:
            if CLUSTER_OF[t] != self.cluster:
                raise ValueError(f"{self.id}: target {t} is not in cluster {self.cluster}")
        if self.slot == 2 and self.prerequisites:
            raise ValueError(f"{self.id}: slot 2 candidates must have no prerequisites")
        return self


class Opener(BaseModel):
    text: str
    rephrase: str
    fallback_take_home: str

    @field_validator("text", "rephrase")
    @classmethod
    def _open(cls, v: str) -> str:
        return _open_question(v)

    @field_validator("fallback_take_home")
    @classmethod
    def _is_question(cls, v: str) -> str:
        if not v.strip().endswith("?"):
            raise ValueError("fallback_take_home must end with '?'")
        return v


class Anchor(BaseModel):
    score: int
    description: str
    exemplar: str

    @field_validator("score")
    @classmethod
    def _147(cls, v: int) -> int:
        if v not in (1, 4, 7):
            raise ValueError("anchor score must be 1, 4 or 7")
        return v


class RubricEntry(BaseModel):
    model_config = ConfigDict(populate_by_name=True)
    construct_id: str = Field(alias="construct")   # 'construct' shadows BaseModel.construct()
    name: str
    inverse: bool = False
    anchors: list[Anchor] = Field(min_length=3, max_length=3)

    @model_validator(mode="after")
    def _scores_complete(self) -> "RubricEntry":
        if {a.score for a in self.anchors} != {1, 4, 7}:
            raise ValueError(f"{self.construct_id}: anchors must be exactly scores 1, 4, 7")
        return self


class Bank(BaseModel):
    opener: Opener
    candidates: list[Candidate]
    rubric: dict[str, RubricEntry]

    @model_validator(mode="after")
    def _structure(self) -> "Bank":
        ids = [c.id for c in self.candidates]
        if len(ids) != len(set(ids)):
            raise ValueError("duplicate candidate ids")
        for slot in range(2, 7):
            cs = [c for c in self.candidates if c.slot == slot]
            if len(cs) < 3:
                raise ValueError(f"slot {slot} needs at least 3 candidates, has {len(cs)}")
            if sum(c.default for c in cs) != 1:
                raise ValueError(f"slot {slot} must have exactly one default candidate")
        if set(self.rubric) != set(CONSTRUCTS):
            raise ValueError(f"rubric must cover exactly {CONSTRUCTS}")
        return self

    def for_slot(self, slot: int, used: Iterable[str] = frozenset()) -> list[Candidate]:
        used = set(used)
        if slot == 7:
            return [c for c in self.candidates if c.slot in (5, 6) and c.id not in used]
        return [c for c in self.candidates if c.slot == slot]

    def default_for(self, slot: int, used: Iterable[str] = frozenset()) -> "Candidate | None":
        used = set(used)
        if slot == 7:
            pool = self.for_slot(7, used)
            for c in pool:                      # prefer an unused default, slot 5 first
                if c.default:
                    return c
            return pool[0] if pool else None
        return next(c for c in self.candidates if c.slot == slot and c.default)

    def by_id(self, cid: str) -> Candidate:
        return next(c for c in self.candidates if c.id == cid)


def load_bank(dir: Path = BANK_DIR) -> Bank:
    opener = yaml.safe_load((dir / "opener.yaml").read_text(encoding="utf-8"))
    qs = yaml.safe_load((dir / "questions.yaml").read_text(encoding="utf-8"))
    rub = yaml.safe_load((dir / "rubric.yaml").read_text(encoding="utf-8"))
    return Bank(opener=opener, candidates=qs["candidates"], rubric={r["construct"]: r for r in rub["rubric"]})
```

- [x] **Step 5: Run to verify pass**

Run: `uv run pytest tests/test_bank.py -v`
Expected: `9 passed`

- [x] **Step 6: Commit**

```bash
git add ember/bank.py tests/conftest.py tests/test_bank.py
git commit -m "feat: question bank schema, validation rules, loader" \
  -m "Co-Authored-By: WOZCODE <contact@withwoz.com>" \
  -m "Claude-Session: https://claude.ai/code/session_011xY91ug8K4Ke8JHFsa5ekB"
```

---

### Task 5: Author the real bank — HUMAN GATE at the end

**Files:**
- Create: `ember/bank/opener.yaml`, `ember/bank/questions.yaml`, `ember/bank/rubric.yaml`, `tests/test_real_bank.py`

**Interfaces:**
- Consumes: `load_bank`, `BANK_DIR` from Task 4.
- Produces: the shipped bank. `load_bank()` with no argument loads it.

- [x] **Step 1: Write the failing test**

`tests/test_real_bank.py`:
```python
from ember.bank import load_bank


def test_real_bank_loads_and_has_expected_shape():
    bank = load_bank()
    assert len(bank.candidates) == 21
    assert {c.slot for c in bank.candidates} == {2, 3, 4, 5, 6}
    fire_ids = {c.id for c in bank.candidates if c.cluster == "fire"}
    assert len(fire_ids) == 11
    assert all(c.prerequisites == [] for c in bank.for_slot(2))


def test_fire_threat_monotonicity_is_satisfiable():
    """For any Fire pick at slot s, slot s+1 must still offer at least one candidate with threat >= it."""
    bank = load_bank()
    for s in (2, 3):
        for c in bank.for_slot(s):
            assert any(n.threat >= c.threat for n in bank.for_slot(s + 1)), f"{c.id} strands slot {s + 1}"
```

- [x] **Step 2: Run to verify failure**

Run: `uv run pytest tests/test_real_bank.py -v`
Expected: `FileNotFoundError: … ember/bank/opener.yaml`

- [x] **Step 3: Write the opener**

`ember/bank/opener.yaml`:
```yaml
text: >-
  Think of someone you know who's clearly going to make it. Not famous — someone you
  actually know. What do they do differently from everyone else?
rephrase: >-
  Someone you know who's going to make it. What's different about how they spend an
  ordinary Tuesday?
fallback_take_home: >-
  What would you have to stop doing to become the person you described first?
```

- [x] **Step 4: Write the spine questions**

`ember/bank/questions.yaml`:
```yaml
candidates:
  # ── Slot 2 · Fire · threat 4–5 · no prerequisites allowed ──────────────────
  - id: F1-a
    slot: 2
    cluster: fire
    targets: [F1]
    threat: 4
    framing: counterfactual-removal
    default: true
    text: >-
      Money's solved. Rent, food, family — handled, forever. It's a Tuesday.
      What are you doing at two in the afternoon?
    rephrase: >-
      If money were never a problem again — what would you actually be doing
      on an ordinary afternoon?
  - id: F1-b
    slot: 2
    cluster: fire
    targets: [F1]
    threat: 5
    framing: envy-locator
    text: Whose life makes you jealous in a way you'd rather not admit?
    rephrase: Whose life do you look at and feel something you don't love feeling?
  - id: F3-c
    slot: 2
    cluster: fire
    targets: [F3]
    threat: 4
    framing: third-person-projection
    text: >-
      Think of the most talented person you know who isn't going anywhere.
      What's the thing they won't do?
    rephrase: The most gifted person you know who's stuck — what do they refuse to do?

  # ── Slot 3 · Fire · threat 5–6 ──────────────────────────────────────────────
  - id: F2-a
    slot: 3
    cluster: fire
    targets: [F2]
    threat: 5
    framing: cost-already-paid
    default: true
    text: >-
      What's something you've already given up for this that the people around
      you didn't understand?
    rephrase: >-
      What has it cost you — time, people, money — to go after something you
      cared about?
  - id: F2-b
    slot: 3
    cluster: fire
    targets: [F2]
    threat: 6
    framing: cost-already-paid
    prerequisites: [relationship]
    text: You brought up someone close to you. What has what you're chasing cost you with them?
    rephrase: The person you mentioned — where has your ambition gotten in the way with them?
  - id: F3-a
    slot: 3
    cluster: fire
    targets: [F3]
    threat: 5
    framing: settled-person-read
    text: >-
      Think of someone you know who settled. Comfortable life, stopped pushing.
      How is it, being around them?
    rephrase: Someone who stopped trying — what's it like spending an evening with them?
  - id: F1-d
    slot: 3
    cluster: fire
    targets: [F1]
    threat: 5
    framing: discrepancy
    prerequisites: [money]
    text: You mentioned money earlier. If the thing you want turned out to make none — what changes?
    rephrase: Take money out of it entirely. What's left of the wanting?
  - id: F1-c
    slot: 3
    cluster: fire
    targets: [F1, F3]
    threat: 5
    framing: third-person-projection
    prerequisites: [named-project]
    text: >-
      You mentioned something you're building. When it's working — what does
      that actually feel like, physically?
    rephrase: The thing you're working on — what's the feeling when it clicks?

  # ── Slot 4 · Fire deep · threat 6–7 ─────────────────────────────────────────
  - id: F2-c
    slot: 4
    cluster: fire
    targets: [F2, F3]
    threat: 7
    framing: cost-already-paid
    default: true
    text: >-
      Say it works. You get exactly what you described. What did you have to
      become, to get there, that you're not sure you want to be?
    rephrase: If you get everything you're after — what will it have cost you as a person?
  - id: F3-b
    slot: 4
    cluster: fire
    targets: [F3]
    threat: 6
    framing: forking
    prerequisites: [failure]
    text: You mentioned something that didn't work. Was that the failure — or was it that you stopped?
    rephrase: That thing that failed — what actually ended it, the failing or the stopping?
  - id: F1-e
    slot: 4
    cluster: fire
    targets: [F1]
    threat: 7
    framing: aftermath-not-event
    prerequisites: [quit]
    text: You said you quit something. What were you actually leaving?
    rephrase: When you stopped — what were you really walking away from?

  # ── Slot 5 · Compass ────────────────────────────────────────────────────────
  - id: C1-a
    slot: 5
    cluster: compass
    targets: [C1]
    threat: 6
    framing: pressure-decision
    default: true
    text: >-
      Last time you had to decide something fast and it cost someone something.
      What did you pick?
    rephrase: A fast decision that cost something — which way did you go, and why that way?
  - id: C2-a
    slot: 5
    cluster: compass
    targets: [C2]
    threat: 5
    framing: scale-of-things
    text: What's the biggest thing you're a small part of?
    rephrase: What do you belong to that's bigger than your own life?
  - id: C2-b
    slot: 5
    cluster: compass
    targets: [C2]
    threat: 6
    framing: forking
    prerequisites: [faith]
    text: You mentioned faith. When it and what you want point different ways — which one moves?
    rephrase: When belief and ambition disagree — which one gives?
  - id: C3-a
    slot: 5
    cluster: compass
    targets: [C3]
    threat: 6
    framing: fear-of-self
    text: What kind of person are you afraid of turning into?
    rephrase: What version of yourself are you trying not to become?
  - id: C1-b
    slot: 5
    cluster: compass
    targets: [C1]
    threat: 6
    framing: discrepancy
    prerequisites: [family]
    text: Your family came up. What's a rule you live by that they'd say you break?
    rephrase: Something you believe about how to live — that your family would say you don't actually do?

  # ── Slot 6 · Ground ─────────────────────────────────────────────────────────
  - id: G1-a
    slot: 6
    cluster: ground
    targets: [G1]
    threat: 5
    framing: empty-room
    default: true
    text: Phone's dead. Nobody's coming for six hours. You're forty minutes in. What's happening?
    rephrase: Six hours alone, no phone. What does the middle of it look like?
  - id: G2-a
    slot: 6
    cluster: ground
    targets: [G2]
    threat: 6
    framing: aftermath-not-event
    text: Something knocked you sideways once. Not the thing itself — what did you build afterwards?
    rephrase: After the worst thing that happened to you — what did you start doing differently?
  - id: G2-b
    slot: 6
    cluster: ground
    targets: [G2]
    threat: 7
    framing: aftermath-not-event
    prerequisites: [loss]
    text: You mentioned losing something. What did you decide, after, that you've never said out loud?
    rephrase: After that loss — what did you quietly decide?
  - id: G3-a
    slot: 6
    cluster: ground
    targets: [G3]
    threat: 5
    framing: people-as
    text: When you're at your best, what are the people closest to you doing?
    rephrase: On your best day — where are the people you love, and what are they doing?
  - id: G3-b
    slot: 6
    cluster: ground
    targets: [G3]
    threat: 6
    framing: people-as
    prerequisites: [solitude]
    text: You said you spend a lot of time alone. Who knows that?
    rephrase: Being alone that much — who actually knows that about you?
```

- [x] **Step 5: Write the rubric anchors**

`ember/bank/rubric.yaml`:
```yaml
rubric:
  - construct: F1
    name: Driver specificity
    anchors:
      - score: 1
        description: Names only abstractions — impact, success, freedom. Cannot say what a good day of it looks like.
        exemplar: I just want to build something that matters.
      - score: 4
        description: Names a domain or a project but describes it from outside — outcomes, not the doing.
        exemplar: I want to run my own studio, be my own boss.
      - score: 7
        description: Describes the itch from inside — a specific moment, sensation, or mechanism, unprompted.
        exemplar: When the pieces fit and something clunky becomes obvious — I don't get that anywhere else.
  - construct: F2
    name: Trade-off evidence
    anchors:
      - score: 1
        description: Only hypothetical sacrifice. No cost has actually been paid.
        exemplar: I'd give up anything for it.
      - score: 4
        description: Names a real cost but frames it as temporary or reversible, or performs regret.
        exemplar: I skipped a few parties, but I'll make it up to them.
      - score: 7
        description: Names a specific cost already paid — time, money, a relationship — plainly, without asking to be admired for it.
        exemplar: Some relationships too, if I'm being honest.
  - construct: F3
    name: Mediocrity tolerance
    inverse: true
    anchors:
      - score: 1
        description: Describes settled people with warmth, ease, or open envy. A comfortable life sounds fine.
        exemplar: Honestly he seems happy. I'd take that.
      - score: 4
        description: Mixed. Respects settling in others but says it isn't for them, without heat.
        exemplar: Good for them. It's just not what I want.
      - score: 7
        description: Visible discomfort or restlessness around settling; describes it as something to avoid, sometimes as fear.
        exemplar: Being around him is like watching someone fall asleep.
  - construct: C1
    name: Values–reality gap
    anchors:
      - score: 1
        description: Stated code and the pressure decision contradict, and the subject does not notice.
        exemplar: I always put people first. I took the deal and told them after.
      - score: 4
        description: Partial. Names a tension but resolves it with a rationalisation.
        exemplar: I know it looked bad, but they'd have done the same.
      - score: 7
        description: Code and decision match, or the subject names the gap themselves before being asked.
        exemplar: I say loyalty matters and I chose the money. I know.
  - construct: C2
    name: Transcendence frame
    anchors:
      - score: 1
        description: Nothing larger than self. "Biggest thing" returns a job, a team, a friend group.
        exemplar: My company, I guess.
      - score: 4
        description: Names something larger — a cause, a tradition, a family line — but cannot say how it changes a decision.
        exemplar: I believe in something bigger, sure.
      - score: 7
        description: A specific frame that exceeds the self, and a concrete way it has shaped a choice.
        exemplar: My grandfather built the first one. I can't be the one who lets it go.
  - construct: C3
    name: Fear specificity
    anchors:
      - score: 1
        description: Cannot name a fear, or names a generic outcome.
        exemplar: Failing, I guess.
      - score: 4
        description: Names an outcome with detail — losing a specific thing.
        exemplar: Ending up broke in my parents' house at thirty-five.
      - score: 7
        description: Names a self they fear becoming, specifically.
        exemplar: The guy who talks about the thing he was going to do.
  - construct: G1
    name: Solitude stance
    anchors:
      - score: 1
        description: Has never considered it. The empty room fills with activity or is deflected with a joke.
        exemplar: I'd probably just sleep.
      - score: 4
        description: Knows what happens but describes it from outside — activities, not what surfaces.
        exemplar: I'd read, tidy up, think about work.
      - score: 7
        description: Knows precisely what surfaces at minute forty and why — or says exactly that they don't, and that it unsettles them.
        exemplar: That's when the thing I've been avoiding shows up.
  - construct: G2
    name: Disruption processed
    anchors:
      - score: 1
        description: Names an event with no account of what changed after.
        exemplar: My parents split when I was twelve.
      - score: 4
        description: Names consequences, but as things that happened to them.
        exemplar: After that I sort of stopped trusting people.
      - score: 7
        description: Names what they built, decided, or dropped as a result, in causal language they own.
        exemplar: I decided I'd never depend on one person for everything again. That's why I started the business.
  - construct: G3
    name: Relational orientation
    anchors:
      - score: 1
        description: People are audience or fuel and the subject cannot see it.
        exemplar: At my best? They're watching, honestly.
      - score: 4
        description: Mixed or unexamined. People are present but their role is vague.
        exemplar: They're just around, I guess.
      - score: 7
        description: People are anchors — or the subject names the audience/fuel pattern in themselves.
        exemplar: They're doing their own thing, and I know they're there. That's the whole point.
```

- [x] **Step 6: Run to verify pass**

Run: `uv run pytest tests/test_real_bank.py tests/test_bank.py -v`
Expected: all pass. If a question trips the yes/no validator, rewrite that question — do not weaken the validator.

- [x] **Step 7: Commit**

```bash
git add ember/bank/ tests/test_real_bank.py
git commit -m "feat: author v1 question bank — opener, 21 spine questions, rubric anchors" \
  -m "Co-Authored-By: WOZCODE <contact@withwoz.com>" \
  -m "Claude-Session: https://claude.ai/code/session_011xY91ug8K4Ke8JHFsa5ekB"
```

- [x] **Step 8: STOP — human review gate**

Spec §5.1: *"every line reviewed by Malek before the pilots."* Send Malek `ember/bank/questions.yaml`, `opener.yaml`, and `rubric.yaml`. Do not start Task 6 until he has read them and either approved or requested edits. Apply edits as a follow-up commit `bank: revisions from review`.

---

### Task 6: Session state

**Files:**
- Create: `ember/session.py`, `tests/test_session.py`

**Interfaces:**
- Produces: `Turn` dataclass (`slot: int, kind: str, question_id: str | None, question: str, asked_at: float, answer: str = "", answered_at: float | None = None, skipped: bool = False, rephrased: bool = False`); `Session` dataclass (fields below) with `elapsed(now) -> float`, `spine_turns() -> list[Turn]`, `current_slot() -> int`, `last_answer() -> str`, `last_spine() -> Turn | None`, `used_ids() -> set[str]`, `fire_answers() -> list[str]`, `transcript_text() -> str`, `add_tags(tags) -> None`, `transcript_for_observer() -> list[dict]`, `to_dict() -> dict`, `Session.from_dict(d) -> Session`; `new_session_id(subject_code: str, now: float) -> str`.
- Test helper: `make_session(now)` added to `tests/conftest.py`.

- [x] **Step 1: Write the failing tests**

Append to `tests/conftest.py`:
```python
def make_session(now: float = 1000.0):
    from ember.session import Session, new_session_id
    return Session(session_id=new_session_id("S01", now), subject_code="S01", started_at=now, consent_at=now - 5)
```

`tests/test_session.py`:
```python
from ember.session import Turn, Session, new_session_id
from tests.conftest import make_session


def test_session_id_format():
    assert new_session_id("S07", 1_757_600_000.0).startswith("S07_2025")


def test_slot_counting_ignores_probes_and_pending():
    s = make_session()
    assert s.current_slot() == 1
    s.turns.append(Turn(slot=1, kind="spine", question_id=None, question="Q1", asked_at=0, answer="a b c", answered_at=5))
    s.turns.append(Turn(slot=1, kind="probe", question_id=None, question="p", asked_at=6, answer="d e", answered_at=9))
    s.pending = Turn(slot=2, kind="spine", question_id="F1-a", question="Q2", asked_at=10)
    assert s.current_slot() == 2
    assert s.last_answer() == "d e"
    assert s.last_spine().question == "Q1"


def test_used_ids_fire_answers_and_tags():
    s = make_session()
    s.turns += [
        Turn(slot=1, kind="spine", question_id=None, question="Q1", asked_at=0, answer="one", answered_at=1),
        Turn(slot=2, kind="spine", question_id="F1-a", question="Q2", asked_at=2, answer="two", answered_at=3),
        Turn(slot=5, kind="spine", question_id="C1-a", question="Q5", asked_at=4, answer="five", answered_at=5),
        Turn(slot=3, kind="spine", question_id="F2-a", question="Q3", asked_at=6, answer="", answered_at=7, skipped=True),
    ]
    assert s.used_ids() == {"F1-a", "C1-a", "F2-a"}
    assert s.fire_answers() == ["one", "two"]
    s.add_tags(["money", "money", "family"])
    s.add_tags(["family"])
    assert s.surfaced_tags == ["money", "family"]


def test_round_trip_and_observer_view():
    s = make_session()
    s.turns.append(Turn(slot=1, kind="spine", question_id=None, question="Q1", asked_at=0, answer="x", answered_at=1))
    s.add_tags(["quit"])
    s.probes_used = 1
    d = s.to_dict()
    back = Session.from_dict(d)
    assert back == s
    view = s.transcript_for_observer()
    assert view == [{"slot": 1, "kind": "spine", "question": "Q1", "answer": "x", "asked_at": 0, "answered_at": 1, "skipped": False}]
    assert "surfaced_tags" not in view[0]
```

- [x] **Step 2: Run to verify failure**

Run: `uv run pytest tests/test_session.py -v`
Expected: `ModuleNotFoundError: No module named 'ember.session'`

- [x] **Step 3: Implement**

`ember/session.py`:
```python
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
```

- [x] **Step 4: Run to verify pass**

Run: `uv run pytest tests/test_session.py -v`
Expected: `4 passed`

- [x] **Step 5: Commit**

```bash
git add ember/session.py tests/test_session.py tests/conftest.py
git commit -m "feat: session state with observer-safe transcript view" \
  -m "Co-Authored-By: WOZCODE <contact@withwoz.com>" \
  -m "Claude-Session: https://claude.ai/code/session_011xY91ug8K4Ke8JHFsa5ekB"
```

---

### Task 7: Deterministic guards

**Files:**
- Create: `ember/guards.py`, `tests/test_guards.py`

**Interfaces:**
- Consumes: `Candidate` from Task 4.
- Produces: constants `PROBE_WINDOW_S = 240.0`, `FIRE_GUARD_S = 270.0`, `Q7_GATE_S = 345.0`, `HARD_CLOSE_S = 390.0`, `SILENCE_S = 25.0`, `PROBE_MIN_WORDS = 15`, `MAX_PROBES = 2`, `STT_MIN_WORDS = 5`, `MAX_RETRIES = 2`; functions `filter_candidates(cands: list[Candidate], surfaced_tags: set[str], min_threat: int) -> list[Candidate]`, `probe_allowed(elapsed_s: float, probes_used: int, last_answer_words: int) -> bool`, `resolve_slot(session_slot: int, elapsed_s: float) -> int`, `q7_allowed(elapsed_s: float) -> bool`, `should_hard_close(elapsed_s: float) -> bool`.

- [x] **Step 1: Write the failing tests**

`tests/test_guards.py`:
```python
from ember.guards import (filter_candidates, probe_allowed, resolve_slot, q7_allowed, should_hard_close,
                          PROBE_WINDOW_S, FIRE_GUARD_S, Q7_GATE_S, HARD_CLOSE_S)


def test_filter_prerequisites_and_threat(mini_bank):
    slot3 = mini_bank.for_slot(3)                       # S3-a t3, S3-b t4, S3-c t5 (needs family)
    assert [c.id for c in filter_candidates(slot3, set(), 0)] == ["S3-a", "S3-b"]
    assert [c.id for c in filter_candidates(slot3, {"family"}, 0)] == ["S3-a", "S3-b", "S3-c"]
    assert [c.id for c in filter_candidates(slot3, {"family"}, 4)] == ["S3-b", "S3-c"]
    assert filter_candidates(slot3, set(), 9) == []


def test_probe_gate():
    assert probe_allowed(10, 0, 15)
    assert not probe_allowed(10, 0, 14)
    assert not probe_allowed(10, 2, 40)
    assert probe_allowed(PROBE_WINDOW_S - 1, 1, 40)
    assert not probe_allowed(PROBE_WINDOW_S, 1, 40)


def test_fire_guard_jumps_to_compass():
    assert resolve_slot(3, FIRE_GUARD_S) == 3
    assert resolve_slot(3, FIRE_GUARD_S + 1) == 5
    assert resolve_slot(4, FIRE_GUARD_S + 1) == 5
    assert resolve_slot(6, FIRE_GUARD_S + 1) == 6
    assert resolve_slot(7, 0) == 7


def test_q7_and_hard_close():
    assert q7_allowed(Q7_GATE_S - 1) and not q7_allowed(Q7_GATE_S)
    assert not should_hard_close(HARD_CLOSE_S - 1) and should_hard_close(HARD_CLOSE_S)
```

- [x] **Step 2: Run to verify failure**

Run: `uv run pytest tests/test_guards.py -v`
Expected: `ModuleNotFoundError: No module named 'ember.guards'`

- [x] **Step 3: Implement**

`ember/guards.py`:
```python
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
```

- [x] **Step 4: Run to verify pass**

Run: `uv run pytest tests/test_guards.py -v`
Expected: `4 passed`

- [x] **Step 5: Commit**

```bash
git add ember/guards.py tests/test_guards.py
git commit -m "feat: deterministic time, probe, and candidate guards" \
  -m "Co-Authored-By: WOZCODE <contact@withwoz.com>" \
  -m "Claude-Session: https://claude.ai/code/session_011xY91ug8K4Ke8JHFsa5ekB"
```

---

### Task 8: LLM wrapper over the Claude Agent SDK

**Files:**
- Create: `ember/llm.py`, `tests/test_llm.py`

**Interfaces:**
- Produces: `class LLMError(RuntimeError)`; `guard_environment() -> None`; `class LLM` with `__init__(self, *, model: str = "opus", fallback_model: str = "sonnet", timeout_s: float = 15.0, query_fn=None)`, `options(self, *, system: str, schema: dict, effort: str) -> ClaudeAgentOptions`, `call_json(self, *, system: str, user: str, schema: dict, effort: str) -> dict` (synchronous; runs its own event loop — callers already on a loop use `asyncio.to_thread`; bounded by `timeout_s` per attempt with one retry, then raises `LLMError`), and `last_meta: dict` (cost, duration, usage of the last call).
- Test helper: `FakeLLM` added to `tests/conftest.py`.

- [x] **Step 1: Add FakeLLM to conftest**

Append to `tests/conftest.py`:
```python
class FakeLLM:
    """Stand-in for ember.llm.LLM. Pops canned responses; an Exception instance is raised instead."""

    def __init__(self, responses=None):
        self.responses = list(responses or [])
        self.calls: list[dict] = []
        self.last_meta: dict = {}

    def call_json(self, *, system: str, user: str, schema: dict, effort: str) -> dict:
        self.calls.append({"system": system, "user": user, "schema": schema, "effort": effort})
        if not self.responses:
            raise AssertionError("FakeLLM: no more responses queued")
        r = self.responses.pop(0)
        if isinstance(r, Exception):
            raise r
        return r
```

- [x] **Step 2: Write the failing tests**

`tests/test_llm.py`:
```python
import os
from types import SimpleNamespace
import pytest

from ember.llm import LLM, LLMError, guard_environment

SCHEMA = {"type": "object", "properties": {"x": {"type": "integer"}}, "required": ["x"], "additionalProperties": False}


def _fake_query(structured=None, result=None, is_error=False, subtype="success"):
    async def q(*, prompt, options):
        q.seen = {"prompt": prompt, "options": options}
        yield SimpleNamespace(structured_output=structured, result=result, is_error=is_error, subtype=subtype,
                              total_cost_usd=0.01, duration_ms=1500, usage={"input_tokens": 2})
    return q


def test_call_json_returns_structured_output_and_meta():
    q = _fake_query(structured={"x": 3})
    llm = LLM(query_fn=q)
    assert llm.call_json(system="S", user="U", schema=SCHEMA, effort="low") == {"x": 3}
    assert llm.last_meta["total_cost_usd"] == 0.01
    assert q.seen["prompt"] == "U"


def test_options_carry_isolation_and_model_settings():
    llm = LLM(query_fn=_fake_query(structured={"x": 1}))
    o = llm.options(system="S", schema=SCHEMA, effort="high")
    assert o.system_prompt == "S" and o.model == "opus" and o.fallback_model == "sonnet"
    assert o.effort == "high" and o.thinking == {"type": "adaptive"}
    assert o.output_format == {"type": "json_schema", "schema": SCHEMA}
    assert o.tools == [] and o.max_turns == 2
    assert o.setting_sources == [] and o.mcp_servers == {} and o.strict_mcp_config is True


def test_falls_back_to_parsing_result_string():
    llm = LLM(query_fn=_fake_query(structured=None, result='{"x": 9}'))
    assert llm.call_json(system="S", user="U", schema=SCHEMA, effort="low") == {"x": 9}


def test_error_result_raises_llm_error():
    llm = LLM(query_fn=_fake_query(structured=None, result=None, is_error=True, subtype="agent_error"))
    with pytest.raises(LLMError):
        llm.call_json(system="S", user="U", schema=SCHEMA, effort="low")


def test_transport_exception_wrapped():
    async def boom(*, prompt, options):
        raise RuntimeError("socket closed")
        yield  # pragma: no cover
    with pytest.raises(LLMError, match="socket closed"):
        LLM(query_fn=boom).call_json(system="S", user="U", schema=SCHEMA, effort="low")


def test_retries_once_then_succeeds():
    calls = {"n": 0}

    async def flaky(*, prompt, options):
        calls["n"] += 1
        if calls["n"] == 1:
            raise RuntimeError("first attempt fails")
        yield SimpleNamespace(structured_output={"x": 5}, result=None, is_error=False, subtype="success",
                              total_cost_usd=0, duration_ms=1, usage={})
    assert LLM(query_fn=flaky).call_json(system="S", user="U", schema=SCHEMA, effort="low") == {"x": 5}
    assert calls["n"] == 2


def test_timeout_per_attempt_then_llm_error():
    import asyncio

    async def slow(*, prompt, options):
        await asyncio.sleep(0.2)
        yield SimpleNamespace(structured_output={"x": 1}, result=None, is_error=False, subtype="success")
    with pytest.raises(LLMError, match="timed out"):
        LLM(query_fn=slow, timeout_s=0.05).call_json(system="S", user="U", schema=SCHEMA, effort="low")


def test_guard_environment(monkeypatch):
    monkeypatch.setenv("CLAUDECODE", "1")
    monkeypatch.setenv("CLAUDE_CODE_SESSION_ID", "abc")
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    guard_environment()
    assert "CLAUDECODE" not in os.environ and "CLAUDE_CODE_SESSION_ID" not in os.environ
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-x")
    with pytest.raises(SystemExit, match="ANTHROPIC_API_KEY"):
        guard_environment()
```

- [x] **Step 3: Run to verify failure**

Run: `uv run pytest tests/test_llm.py -v`
Expected: `ModuleNotFoundError: No module named 'ember.llm'`

- [x] **Step 4: Implement**

`ember/llm.py`:
```python
"""The only module that talks to the Claude Agent SDK (spec §8 Engine)."""
import asyncio
import json
import os

from claude_agent_sdk import query as sdk_query, ClaudeAgentOptions

MODEL = "opus"
FALLBACK_MODEL = "sonnet"


class LLMError(RuntimeError):
    pass


def guard_environment() -> None:
    """Refuse to bill the API by accident; strip nested Claude Code session vars."""
    if os.environ.get("ANTHROPIC_API_KEY") is not None:
        raise SystemExit("ember runs on your Claude subscription. Unset ANTHROPIC_API_KEY before starting.")
    for k in [k for k in os.environ if k.startswith("CLAUDE")]:
        os.environ.pop(k)


class LLM:
    def __init__(self, *, model: str = MODEL, fallback_model: str = FALLBACK_MODEL, timeout_s: float = 15.0, query_fn=None):
        self.model = model
        self.fallback_model = fallback_model
        self.timeout_s = timeout_s
        self._query = query_fn or sdk_query
        self.last_meta: dict = {}

    def options(self, *, system: str, schema: dict, effort: str) -> ClaudeAgentOptions:
        return ClaudeAgentOptions(
            system_prompt=system,
            model=self.model,
            fallback_model=self.fallback_model,
            effort=effort,
            thinking={"type": "adaptive"},
            output_format={"type": "json_schema", "schema": schema},
            tools=[],
            max_turns=2,
            setting_sources=[],        # no ~/.claude or ./.claude settings, skills, memory
            mcp_servers={},
            strict_mcp_config=True,    # no MCP servers from any config file
        )

    def call_json(self, *, system: str, user: str, schema: dict, effort: str) -> dict:
        """Synchronous. Runs its own event loop; from inside a running loop use asyncio.to_thread.
        Bounded: timeout_s per attempt, one retry, then LLMError (spec §9)."""
        last: LLMError | None = None
        for _attempt in range(2):
            try:
                return asyncio.run(asyncio.wait_for(self._call(system, user, schema, effort), timeout=self.timeout_s))
            except LLMError as e:
                last = e
            except TimeoutError:
                last = LLMError(f"timed out after {self.timeout_s}s")
            except Exception as e:  # transport, SDK, JSON
                last = LLMError(str(e))
                last.__cause__ = e
        raise last

    async def _call(self, system: str, user: str, schema: dict, effort: str) -> dict:
        result = None
        async for m in self._query(prompt=user, options=self.options(system=system, schema=schema, effort=effort)):
            if hasattr(m, "structured_output"):
                result = m
        if result is None:
            raise LLMError("no ResultMessage received")
        self.last_meta = {
            "total_cost_usd": getattr(result, "total_cost_usd", None),
            "duration_ms": getattr(result, "duration_ms", None),
            "usage": getattr(result, "usage", None),
        }
        if getattr(result, "is_error", False) or getattr(result, "subtype", "success") != "success":
            raise LLMError(f"result subtype={getattr(result, 'subtype', '?')}")
        out = result.structured_output
        if out is None:
            out = json.loads(result.result or "")
        if not isinstance(out, dict):
            raise LLMError("structured output is not an object")
        return out
```

- [x] **Step 5: Run to verify pass**

Run: `uv run pytest tests/test_llm.py -v`
Expected: `8 passed`

- [x] **Step 6: Commit**

```bash
git add ember/llm.py tests/test_llm.py tests/conftest.py
git commit -m "feat: Claude Agent SDK wrapper with isolation options and environment guard" \
  -m "Co-Authored-By: WOZCODE <contact@withwoz.com>" \
  -m "Claude-Session: https://claude.ai/code/session_011xY91ug8K4Ke8JHFsa5ekB"
```

---

### Task 9: Engine — prompts, turn contract, validation, close

**Files:**
- Create: `ember/engine.py`, `tests/test_engine.py`

**Interfaces:**
- Consumes: `Bank`, `Candidate` (Task 4); `Session`, `Turn` (Task 6); guards (Task 7); `LLM`, `LLMError` (Task 8); `contains_verbatim`, `extract_quote`, `word_count`, `longest_sentence` (Task 3); `TAGS`, `TAG_HINTS` (Task 2).
- Produces: pydantic `Action` (`action: Literal["pick","probe","close"], candidate_id: str | None, probe_text: str | None, surfaced_tags: list[str], reason: str`), `CloseOut` (`mirror: str, take_home: str`); dataclass `Next` (`kind: str, slot: int, question_id: str | None, text: str, fallback_used: bool, log: dict`); `ACTION_SCHEMA: dict`, `CLOSE_SCHEMA: dict`; `build_system_prompt(bank: Bank) -> str`, `build_turn_prompt(session: Session, slot: int, offered: list[Candidate], probe_ok: bool, elapsed_s: float) -> str`, `build_close_prompt(session: Session) -> str`; `class Engine(bank: Bank, llm)` with `first() -> Next`, `next(session: Session, now: float) -> Next` (mutates `session.surfaced_tags` and `session.probes_used`), `close(session: Session) -> CloseOut`.

- [x] **Step 1: Write the failing tests**

`tests/test_engine.py`:
```python
import pytest

from ember.engine import Engine, Next, ACTION_SCHEMA, CLOSE_SCHEMA, build_system_prompt
from ember.llm import LLMError
from ember.session import Turn
from ember.guards import FIRE_GUARD_S, HARD_CLOSE_S, PROBE_WINDOW_S
from tests.conftest import FakeLLM, make_session

LONG = "I rebuilt the whole backend three times because the first two felt wrong and nobody asked me to do any of it honestly"


def _answered(s, slot, qid, answer, at):
    s.turns.append(Turn(slot=slot, kind="spine", question_id=qid, question=f"Q{slot}", asked_at=at - 30, answer=answer, answered_at=at))


def test_first_is_opener_without_llm(mini_bank):
    eng = Engine(mini_bank, FakeLLM())
    n = eng.first()
    assert n.kind == "spine" and n.slot == 1 and n.question_id is None
    assert n.text == mini_bank.opener.text


def test_system_prompt_lists_bank_and_tags(mini_bank):
    sp = build_system_prompt(mini_bank)
    assert "S3-b" in sp and "named-project" in sp and "yes/no" in sp.lower()


def test_pick_valid_candidate_and_tags(mini_bank):
    llm = FakeLLM([{"action": "pick", "candidate_id": "S2-b", "surfaced_tags": ["money", "bogus"], "reason": "r"}])
    s = make_session(now=0.0)
    _answered(s, 1, None, LONG, 40.0)
    n = Engine(mini_bank, llm).next(s, now=45.0)
    assert n.kind == "spine" and n.slot == 2 and n.question_id == "S2-b" and n.fallback_used is False
    assert s.surfaced_tags == ["money"]                      # unknown tag dropped
    assert llm.calls[0]["effort"] == "low" and llm.calls[0]["schema"] is ACTION_SCHEMA
    assert "S2-a" in llm.calls[0]["user"] and "S2-b" in llm.calls[0]["user"]


def test_pick_outside_offered_falls_back_to_default(mini_bank):
    llm = FakeLLM([{"action": "pick", "candidate_id": "S5-a", "surfaced_tags": [], "reason": "r"}])
    s = make_session(now=0.0)
    _answered(s, 1, None, LONG, 40.0)
    n = Engine(mini_bank, llm).next(s, now=45.0)
    assert n.question_id == "S2-a" and n.fallback_used is True and n.log["validation_error"]


def test_llm_error_falls_back_to_default(mini_bank):
    s = make_session(now=0.0)
    _answered(s, 1, None, LONG, 40.0)
    n = Engine(mini_bank, FakeLLM([LLMError("down")])).next(s, now=45.0)
    assert n.question_id == "S2-a" and n.fallback_used is True and "down" in n.log["error"]


def test_valid_probe_quotes_answer_and_spends_budget(mini_bank):
    llm = FakeLLM([{"action": "probe", "probe_text": 'You said "nobody asked me to".', "surfaced_tags": [], "reason": "r"}])
    s = make_session(now=0.0)
    _answered(s, 1, None, LONG, 40.0)
    n = Engine(mini_bank, llm).next(s, now=45.0)
    assert n.kind == "probe" and n.slot == 1 and n.question_id is None and s.probes_used == 1
    assert n.text == 'You said "nobody asked me to".'


def test_probe_without_verbatim_quote_is_rejected(mini_bank):
    llm = FakeLLM([{"action": "probe", "probe_text": 'You said "nobody ever asked".', "surfaced_tags": [], "reason": "r"}])
    s = make_session(now=0.0)
    _answered(s, 1, None, LONG, 40.0)
    n = Engine(mini_bank, llm).next(s, now=45.0)
    assert n.kind == "spine" and n.question_id == "S2-a" and n.fallback_used and s.probes_used == 0


def test_probe_not_offered_when_answer_short_or_window_closed(mini_bank):
    llm = FakeLLM([{"action": "probe", "probe_text": 'You said "a b c".', "surfaced_tags": [], "reason": "r"}] * 2)
    s = make_session(now=0.0)
    _answered(s, 1, None, "a b c d e f", 40.0)
    n = Engine(mini_bank, llm).next(s, now=45.0)
    assert n.kind == "spine" and "Probe allowed: no" in llm.calls[0]["user"]
    s2 = make_session(now=0.0)
    _answered(s2, 1, None, LONG, PROBE_WINDOW_S + 1)
    n2 = Engine(mini_bank, llm).next(s2, now=PROBE_WINDOW_S + 2)
    assert n2.kind == "spine"


def test_fire_threat_monotonic_filters_offered(mini_bank):
    llm = FakeLLM([{"action": "pick", "candidate_id": "S3-b", "surfaced_tags": [], "reason": "r"}])
    s = make_session(now=0.0)
    _answered(s, 1, None, LONG, 30.0)
    _answered(s, 2, "S2-c", LONG, 60.0)                       # S2-c has threat 4
    Engine(mini_bank, llm).next(s, now=65.0)
    assert "S3-a" not in llm.calls[0]["user"] and "S3-b" in llm.calls[0]["user"]


def test_fire_guard_jumps_to_compass(mini_bank):
    llm = FakeLLM([{"action": "pick", "candidate_id": "S5-b", "surfaced_tags": [], "reason": "r"}])
    s = make_session(now=0.0)
    _answered(s, 1, None, LONG, 30.0)
    _answered(s, 2, "S2-a", LONG, FIRE_GUARD_S + 5)
    n = Engine(mini_bank, llm).next(s, now=FIRE_GUARD_S + 10)
    assert n.slot == 5 and n.question_id == "S5-b"


def test_hard_close_returns_close_without_llm(mini_bank):
    s = make_session(now=0.0)
    _answered(s, 1, None, LONG, HARD_CLOSE_S + 1)
    n = Engine(mini_bank, FakeLLM()).next(s, now=HARD_CLOSE_S + 2)
    assert n.kind == "close"


def test_close_validates_mirror_and_take_home(mini_bank):
    llm = FakeLLM([{"mirror": "nobody asked me to do any of it", "take_home": "Who would you have to disappoint to keep going?"}])
    s = make_session(now=0.0)
    _answered(s, 1, None, LONG, 40.0)
    out = Engine(mini_bank, llm).close(s)
    assert out.mirror == "nobody asked me to do any of it"
    assert llm.calls[0]["effort"] == "high" and llm.calls[0]["schema"] is CLOSE_SCHEMA


def test_close_fallback_uses_longest_fire_sentence(mini_bank):
    llm = FakeLLM([{"mirror": "this was never said", "take_home": "Why?"}])
    s = make_session(now=0.0)
    _answered(s, 1, None, "Short one. " + LONG + ".", 40.0)
    out = Engine(mini_bank, llm).close(s)
    assert out.mirror == LONG
    assert out.take_home == mini_bank.opener.fallback_take_home
```

- [x] **Step 2: Run to verify failure**

Run: `uv run pytest tests/test_engine.py -v`
Expected: `ModuleNotFoundError: No module named 'ember.engine'`

- [x] **Step 3: Implement**

`ember/engine.py`:
```python
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
```

- [x] **Step 4: Run to verify pass**

Run: `uv run pytest tests/test_engine.py -v`
Expected: `13 passed`

- [x] **Step 5: Commit**

```bash
git add ember/engine.py tests/test_engine.py
git commit -m "feat: engine — prompts, pick/probe/close contract, validation, fallbacks" \
  -m "Co-Authored-By: WOZCODE <contact@withwoz.com>" \
  -m "Claude-Session: https://claude.ai/code/session_011xY91ug8K4Ke8JHFsa5ekB"
```

---

### Task 10: Engine behaviour suite against the real model (recorded)

**Files:**
- Create: `tests/recording.py`, `tests/test_engine_recorded.py`, `tests/fixtures/transcripts/{vague,decliner,talker,terse,contradicts,family_q1}.json`, `tests/fixtures/recorded/` (populated on first run)

**Interfaces:**
- Consumes: `LLM` (Task 8), `Engine` (Task 9), real bank (Task 5).
- Produces: `RecordingLLM(inner: LLM, dir: Path)` — same `call_json` signature; keys recordings by SHA-256 of (system, user, schema, effort); replays if present; records if `EMBER_RECORD=1`; otherwise raises `pytest.skip`.

- [ ] **Step 1: Write the recording shim**

`tests/recording.py`:
```python
import hashlib, json, os
from pathlib import Path
import pytest

REC_DIR = Path(__file__).parent / "fixtures" / "recorded"


class RecordingLLM:
    def __init__(self, inner=None, dir: Path = REC_DIR):
        self.inner = inner
        self.dir = dir
        self.dir.mkdir(parents=True, exist_ok=True)
        self.last_meta: dict = {}

    @staticmethod
    def _key(system, user, schema, effort) -> str:
        blob = json.dumps([system, user, schema, effort], sort_keys=True).encode()
        return hashlib.sha256(blob).hexdigest()[:24]

    def call_json(self, *, system: str, user: str, schema: dict, effort: str) -> dict:
        f = self.dir / f"{self._key(system, user, schema, effort)}.json"
        if f.exists():
            return json.loads(f.read_text())
        if os.environ.get("EMBER_RECORD") != "1" or self.inner is None:
            pytest.skip(f"no recording {f.name}; run with EMBER_RECORD=1")
        out = self.inner.call_json(system=system, user=user, schema=schema, effort=effort)
        self.last_meta = self.inner.last_meta
        f.write_text(json.dumps(out, indent=2, ensure_ascii=False))
        return out
```

- [ ] **Step 2: Write six fixture transcripts**

Each file is a list of `{"slot", "question_id", "answer"}` for completed spine turns; the test builds the session from it. `tests/fixtures/transcripts/vague.json`:
```json
[{"slot": 1, "question_id": null, "answer": "I guess they just work harder than most people and they want it more. They're focused. I don't know, they just have that thing."}]
```
`decliner.json`:
```json
[{"slot": 1, "question_id": null, "answer": "My friend Omar. He wakes up at five, he doesn't drink, and he's shipped three things while the rest of us talked about it."},
 {"slot": 2, "question_id": "F1-b", "answer": "I'd rather not answer that one, honestly."}]
```
`talker.json`:
```json
[{"slot": 1, "question_id": null, "answer": "Okay so there's this girl from my course, Lena, and the thing about her is she doesn't wait for permission, like the rest of us will sit in a group chat for three weeks deciding whether to email a professor and she's already had the meeting, she's already been told no twice, she's already found the second professor, and I think what she does differently is she treats no as information rather than as a verdict, and I've watched her do this since first year and every single time I think I could do that and I don't, and I've started to wonder if the difference is that she genuinely doesn't care what the group chat thinks and I do, I care a lot, I care more than I'd like to admit, and that's probably the actual answer to your question."}]
```
`terse.json`:
```json
[{"slot": 1, "question_id": null, "answer": "They don't quit."}]
```
`contradicts.json`:
```json
[{"slot": 1, "question_id": null, "answer": "My cousin. She'll drop anything for the people she loves, and somehow she still ships. Loyalty first, always. That's what I want to be."},
 {"slot": 2, "question_id": "F1-a", "answer": "Two in the afternoon, money solved? I'd be in the workshop with the door locked. Phone off. Nobody gets in. That's the dream honestly, just me and the work and no one needing anything."}]
```
`family_q1.json`:
```json
[{"slot": 1, "question_id": null, "answer": "My older brother. My parents put everything into his education and he never once complained, he just took it and built a company out of it. He calls my mum every day. I don't know how he does both."}]
```

- [ ] **Step 3: Write the failing tests**

`tests/test_engine_recorded.py`:
```python
import json
from pathlib import Path
import pytest

from ember.bank import load_bank
from ember.engine import Engine
from ember.llm import LLM
from ember.session import Turn
from ember.text import extract_quote, contains_verbatim
from tests.conftest import make_session
from tests.recording import RecordingLLM

FIX = Path(__file__).parent / "fixtures" / "transcripts"
pytestmark = pytest.mark.api


def _session_from(name: str):
    s = make_session(now=0.0)
    at = 0.0
    for row in json.loads((FIX / f"{name}.json").read_text()):
        at += 40
        s.turns.append(Turn(slot=row["slot"], kind="spine", question_id=row["question_id"],
                            question=f"Q{row['slot']}", asked_at=at - 35, answer=row["answer"], answered_at=at))
    return s, at + 5


@pytest.fixture(scope="module")
def engine():
    return Engine(load_bank(), RecordingLLM(inner=LLM()))


@pytest.mark.parametrize("name", ["vague", "decliner", "talker", "terse", "contradicts", "family_q1"])
def test_next_produces_valid_turn(engine, name):
    s, now = _session_from(name)
    n = engine.next(s, now=now)
    assert n.kind in ("spine", "probe")
    if n.kind == "spine":
        assert n.question_id in n.log["offered"] or n.fallback_used
    else:
        q = extract_quote(n.text)
        assert q and contains_verbatim(s.last_answer(), q, min_words=3, max_words=6)
    assert all(t in {"named-project", "family", "money", "health", "loss", "faith", "relationship", "solitude",
                     "quit", "moved", "failure", "competition"} for t in s.surfaced_tags)


def test_family_answer_surfaces_family_tag(engine):
    s, now = _session_from("family_q1")
    engine.next(s, now=now)
    assert "family" in s.surfaced_tags


def test_close_on_talker_is_verbatim(engine):
    s, _ = _session_from("talker")
    out = engine.close(s)
    assert contains_verbatim(s.transcript_text(), out.mirror, min_words=5)
    assert out.take_home.endswith("?")
```

- [ ] **Step 4: Record — requires the operator's Claude Code login on this machine**

Run: `cd ~/Desktop/ember && EMBER_RECORD=1 uv run pytest tests/test_engine_recorded.py -v`
Expected: `8 passed` and new files under `tests/fixtures/recorded/`. Roughly 8 subscription calls, ~30 s.
If a test fails on a real model response (e.g. an over-long probe), that is a prompt-craft problem: adjust `build_system_prompt` wording in `ember/engine.py`, delete `tests/fixtures/recorded/*.json`, and re-record. Do not loosen the validators.

- [ ] **Step 5: Replay without the flag**

Run: `uv run pytest tests/test_engine_recorded.py -v`
Expected: `8 passed`, zero network calls.

- [ ] **Step 6: Commit (recordings included)**

```bash
git add tests/recording.py tests/test_engine_recorded.py tests/fixtures/
git commit -m "test: recorded engine behaviour suite across six subject archetypes" \
  -m "Co-Authored-By: WOZCODE <contact@withwoz.com>" \
  -m "Claude-Session: https://claude.ai/code/session_011xY91ug8K4Ke8JHFsa5ekB"
```

---

### Task 11: STT — in-process whisper with a warm model

**Files:**
- Create: `ember/audio.py`, `ember/stt.py`, `tests/test_stt.py`, `tests/fixtures/audio/` (generated, git-ignored)

**Interfaces:**
- Produces: `ember.audio.to_wav(src: Path, dst: Path) -> Path` (ffmpeg only, no mlx import); `ember.stt.MODEL_REPO = "mlx-community/whisper-large-v3-turbo"`; `class Transcriber(repo: str = MODEL_REPO)` with `warm() -> float` (seconds) and `transcribe(wav_path: Path) -> str`.

- [x] **Step 1: Write the failing tests**

`tests/test_stt.py`:
```python
import subprocess, time
from pathlib import Path
import pytest

from ember.audio import to_wav
from ember.stt import Transcriber

pytestmark = pytest.mark.slow
AUDIO = Path(__file__).parent / "fixtures" / "audio"


@pytest.fixture(scope="module")
def clip() -> Path:
    AUDIO.mkdir(parents=True, exist_ok=True)
    aiff = AUDIO / "clip.aiff"
    if not aiff.exists():
        subprocess.run(["say", "-o", str(aiff),
                        "I rebuilt the whole backend three times. Nobody asked me to. "
                        "My friends thought I was wasting my time, and by any normal measure I probably was."],
                       check=True)
    return aiff


def test_to_wav_produces_16k_mono(clip, tmp_path):
    wav = to_wav(clip, tmp_path / "clip.wav")
    info = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "stream=sample_rate,channels",
                           "-of", "csv=p=0", str(wav)], capture_output=True, text=True, check=True).stdout
    assert info.strip() == "16000,1"


def test_transcribe_after_warm(clip, tmp_path):
    wav = to_wav(clip, tmp_path / "clip.wav")
    t = Transcriber()
    warm_s = t.warm()
    t0 = time.perf_counter()
    text = t.transcribe(wav)
    dt = time.perf_counter() - t0
    print(f"\nwarm={warm_s:.1f}s  transcribe={dt:.2f}s  text={text!r}")
    assert "backend" in text.lower() and "wasting my time" in text.lower()   # whisper writes numbers as digits
    assert dt < 6.0
```

- [x] **Step 2: Run to verify failure**

Run: `uv run pytest tests/test_stt.py -v -s`
Expected: `ModuleNotFoundError: No module named 'ember.stt'`

- [x] **Step 3: Implement**

`ember/audio.py` — ffmpeg only, no mlx import, so store and server can use it cheaply:
```python
"""Audio conversion via the ffmpeg CLI."""
import subprocess
from pathlib import Path


def to_wav(src: Path, dst: Path) -> Path:
    dst.parent.mkdir(parents=True, exist_ok=True)
    subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-i", str(src), "-ar", "16000", "-ac", "1", str(dst)],
                   check=True)
    return dst
```

`ember/stt.py`:
```python
"""Local speech-to-text. The model is loaded once and stays resident (spec §8 STT)."""
import time
from pathlib import Path

import mlx_whisper
import numpy as np

MODEL_REPO = "mlx-community/whisper-large-v3-turbo"


class Transcriber:
    def __init__(self, repo: str = MODEL_REPO):
        self.repo = repo

    def warm(self) -> float:
        """Load the model by transcribing one second of silence. mlx_whisper caches it on its ModelHolder."""
        t0 = time.perf_counter()
        mlx_whisper.transcribe(np.zeros(16000, dtype=np.float32), path_or_hf_repo=self.repo, language="en")
        return time.perf_counter() - t0

    def transcribe(self, wav_path: Path) -> str:
        out = mlx_whisper.transcribe(str(wav_path), path_or_hf_repo=self.repo, language="en")
        return out["text"].strip()
```

- [x] **Step 4: Run to verify pass and record the number**

Run: `uv run pytest tests/test_stt.py -v -s`
Expected: `2 passed`, and a printed line like `warm=4.1s  transcribe=1.9s`. Append the measured `transcribe=` figure to spec Appendix B as a new line: `In-process, model resident: <N> s for the ~12 s test clip (build step 3, <date>).`

- [x] **Step 5: Commit**

```bash
git add ember/audio.py ember/stt.py tests/test_stt.py docs/superpowers/specs/2026-09-11-ember-v1-design.md
git commit -m "feat: in-process whisper transcriber with warm-up; record measured latency" \
  -m "Co-Authored-By: WOZCODE <contact@withwoz.com>" \
  -m "Claude-Session: https://claude.ai/code/session_011xY91ug8K4Ke8JHFsa5ekB"
```

---

### Task 12: Session store — folders, JSON, SQLite index

**Files:**
- Create: `ember/store.py`, `tests/test_store.py`

**Interfaces:**
- Consumes: `Session`, `Turn`, `new_session_id` (Task 6).
- Produces: `class SessionStore(root: Path)` with `create(subject_code: str, consent_at: float, now: float) -> Session`, `dir_for(session_id: str) -> Path`, `save(session: Session) -> None` (writes `session.json` + `transcript.json` + updates SQLite), `load(session_id: str) -> Session`, `append_engine_log(session_id: str, entry: dict) -> None`, `list_sessions() -> list[dict]`. SQLite file at `root.parent / "ember.sqlite"` (i.e. repo root when root is `./sessions`).

- [ ] **Step 1: Write the failing tests**

`tests/test_store.py`:
```python
import json
from pathlib import Path

from ember.session import Turn
from ember.store import SessionStore


def test_create_writes_meta_and_index(tmp_path: Path):
    st = SessionStore(tmp_path / "sessions")
    s = st.create("S03", consent_at=99.0, now=100.0)
    d = st.dir_for(s.session_id)
    meta = json.loads((d / "meta.json").read_text())
    assert meta["subject_code"] == "S03" and meta["consent_at"] == 99.0 and "rubric_version" in meta
    assert st.list_sessions()[0]["session_id"] == s.session_id


def test_save_load_round_trip_and_observer_file(tmp_path: Path):
    st = SessionStore(tmp_path / "sessions")
    s = st.create("S03", consent_at=99.0, now=100.0)
    s.turns.append(Turn(slot=1, kind="spine", question_id=None, question="Q1", asked_at=100, answer="hello there", answered_at=130))
    s.add_tags(["money"])
    st.save(s)
    back = st.load(s.session_id)
    assert back == s
    tr = json.loads((st.dir_for(s.session_id) / "transcript.json").read_text())
    assert tr["turns"][0]["answer"] == "hello there"
    assert "surfaced_tags" not in tr and "pending" not in tr


def test_engine_log_appends(tmp_path: Path):
    st = SessionStore(tmp_path / "sessions")
    s = st.create("S03", consent_at=99.0, now=100.0)
    st.append_engine_log(s.session_id, {"slot": 2, "offered": ["a"]})
    st.append_engine_log(s.session_id, {"slot": 3, "offered": ["b"]})
    log = json.loads((st.dir_for(s.session_id) / "engine_log.json").read_text())
    assert [e["slot"] for e in log] == [2, 3]

```

- [ ] **Step 2: Run to verify failure**

Run: `uv run pytest tests/test_store.py -v`
Expected: `ModuleNotFoundError: No module named 'ember.store'`

- [ ] **Step 3: Implement**

`ember/store.py`:
```python
"""Per-session folders and a SQLite index (spec §8 storage). transcript.json is the observer's only input."""
import json
import sqlite3
import time
from pathlib import Path

from .session import Session, new_session_id

RUBRIC_VERSION = "1.0.0"


class SessionStore:
    def __init__(self, root: Path):
        self.root = Path(root)
        self.root.mkdir(parents=True, exist_ok=True)
        self.db_path = self.root.parent / "ember.sqlite"
        with self._db() as db:
            db.execute("""CREATE TABLE IF NOT EXISTS sessions(
                session_id TEXT PRIMARY KEY, subject_code TEXT, started_at REAL, closed INTEGER,
                n_turns INTEGER, mirror TEXT, take_home TEXT, updated_at REAL)""")

    def _db(self):
        return sqlite3.connect(self.db_path)

    def dir_for(self, session_id: str) -> Path:
        return self.root / session_id

    def create(self, subject_code: str, consent_at: float, now: float) -> Session:
        s = Session(session_id=new_session_id(subject_code, now), subject_code=subject_code,
                    started_at=now, consent_at=consent_at)
        d = self.dir_for(s.session_id)
        (d / "audio").mkdir(parents=True, exist_ok=True)
        (d / "meta.json").write_text(json.dumps({
            "session_id": s.session_id, "subject_code": subject_code, "started_at": now,
            "consent_at": consent_at, "rubric_version": RUBRIC_VERSION, "operator_notes": ""}, indent=2))
        (d / "engine_log.json").write_text("[]")
        self.save(s)
        return s

    def save(self, session: Session) -> None:
        d = self.dir_for(session.session_id)
        (d / "session.json").write_text(json.dumps(session.to_dict(), indent=2, ensure_ascii=False))
        (d / "transcript.json").write_text(json.dumps({
            "session_id": session.session_id, "subject_code": session.subject_code,
            "started_at": session.started_at, "closed": session.closed,
            "mirror": session.mirror, "take_home": session.take_home,
            "turns": session.transcript_for_observer()}, indent=2, ensure_ascii=False))
        with self._db() as db:
            db.execute("""INSERT INTO sessions VALUES(?,?,?,?,?,?,?,?)
                ON CONFLICT(session_id) DO UPDATE SET closed=excluded.closed, n_turns=excluded.n_turns,
                mirror=excluded.mirror, take_home=excluded.take_home, updated_at=excluded.updated_at""",
                (session.session_id, session.subject_code, session.started_at, int(session.closed),
                 len(session.turns), session.mirror, session.take_home, time.time()))

    def load(self, session_id: str) -> Session:
        return Session.from_dict(json.loads((self.dir_for(session_id) / "session.json").read_text()))

    def append_engine_log(self, session_id: str, entry: dict) -> None:
        p = self.dir_for(session_id) / "engine_log.json"
        log = json.loads(p.read_text())
        log.append(entry)
        p.write_text(json.dumps(log, indent=2, ensure_ascii=False, default=str))

    def list_sessions(self) -> list[dict]:
        with self._db() as db:
            db.row_factory = sqlite3.Row
            return [dict(r) for r in db.execute("SELECT * FROM sessions ORDER BY started_at DESC")]
```

- [ ] **Step 4: Run to verify pass**

Run: `uv run pytest tests/test_store.py -v`
Expected: `3 passed`

- [ ] **Step 5: Commit**

```bash
git add ember/store.py tests/test_store.py
git commit -m "feat: session store with observer-only transcript.json and SQLite index" \
  -m "Co-Authored-By: WOZCODE <contact@withwoz.com>" \
  -m "Claude-Session: https://claude.ai/code/session_011xY91ug8K4Ke8JHFsa5ekB"
```

---

### Task 13: FastAPI server — session, answer, rephrase, close, state

**Files:**
- Create: `ember/server.py`, `tests/test_server.py`

**Interfaces:**
- Consumes: `SessionStore` (12), `Engine`, `Next`, `CloseOut` (9), `Transcriber` protocol `transcribe(Path) -> str` (11), `Turn` (6), `STT_MIN_WORDS`, `MAX_RETRIES` (7), `word_count` (3).
- Produces: `create_app(store: SessionStore, engine: Engine, transcriber) -> FastAPI` with routes:
  - `POST /api/session` body `{"subject_code": "S01"}` → `{"session_id", "kind": "spine", "question", "slot"}`
  - `POST /api/session/{sid}/answer` multipart `audio` → either `{"retry": true, "question", "message"}` or `{"kind": "spine"|"probe", "question", "slot"}` or `{"kind": "close", "mirror", "take_home"}`
  - `POST /api/session/{sid}/rephrase` → `{"question"}`
  - `POST /api/session/{sid}/resume` → the pending-question payload, or the close payload if already closed (crash recovery, spec §9)
  - `GET /api/session/{sid}/state` → operator JSON
  - `GET /` subject page, `GET /operator` operator page (Task 14 provides the files; this task serves them).

- [ ] **Step 1: Write the failing tests**

`tests/test_server.py`:
```python
import io
from pathlib import Path
from fastapi.testclient import TestClient

from ember.engine import Engine
from ember.server import create_app
from ember.store import SessionStore
from tests.conftest import FakeLLM

LONG = "I rebuilt the whole backend three times because the first two felt wrong and nobody asked me to do any of it honestly"


class FakeTranscriber:
    def __init__(self, texts):
        self.texts = list(texts)

    def transcribe(self, wav_path: Path) -> str:
        return self.texts.pop(0)


def _client(tmp_path, mini_bank, llm_responses, stt_texts):
    store = SessionStore(tmp_path / "sessions")
    app = create_app(store, Engine(mini_bank, FakeLLM(llm_responses)), FakeTranscriber(stt_texts))
    def _fake_wav(src, dst):                                  # skip ffmpeg in tests
        dst.write_bytes(b"RIFF")
        return dst
    app.state.to_wav = _fake_wav
    return TestClient(app), store


def _post_audio(client, sid):
    return client.post(f"/api/session/{sid}/answer", files={"audio": ("a.webm", io.BytesIO(b"\x00"), "audio/webm")})


def test_session_starts_with_opener(tmp_path, mini_bank):
    client, _ = _client(tmp_path, mini_bank, [], [])
    r = client.post("/api/session", json={"subject_code": "S01"})
    assert r.status_code == 200
    body = r.json()
    assert body["kind"] == "spine" and body["slot"] == 1 and body["question"] == mini_bank.opener.text


def test_answer_advances_and_persists(tmp_path, mini_bank):
    client, store = _client(tmp_path, mini_bank,
                            [{"action": "pick", "candidate_id": "S2-b", "surfaced_tags": ["money"], "reason": "r"}], [LONG])
    sid = client.post("/api/session", json={"subject_code": "S01"}).json()["session_id"]
    body = _post_audio(client, sid).json()
    assert body["kind"] == "spine" and body["slot"] == 2
    s = store.load(sid)
    assert s.turns[0].answer == LONG and s.pending.question_id == "S2-b" and s.surfaced_tags == ["money"]
    assert (store.dir_for(sid) / "audio" / "q1.wav").exists()


def test_short_answer_retries_then_skips(tmp_path, mini_bank):
    client, store = _client(tmp_path, mini_bank,
                            [{"action": "pick", "candidate_id": "S2-a", "surfaced_tags": [], "reason": "r"}],
                            ["uh", "hmm", "no"])
    sid = client.post("/api/session", json={"subject_code": "S01"}).json()["session_id"]
    assert _post_audio(client, sid).json()["retry"] is True
    assert _post_audio(client, sid).json()["retry"] is True
    body = _post_audio(client, sid).json()
    assert body["kind"] == "spine" and body["slot"] == 2
    s = store.load(sid)
    assert s.turns[0].skipped is True and s.retries == 0


def test_rephrase_returns_gentler_text(tmp_path, mini_bank):
    client, store = _client(tmp_path, mini_bank, [], [])
    sid = client.post("/api/session", json={"subject_code": "S01"}).json()["session_id"]
    r = client.post(f"/api/session/{sid}/rephrase").json()
    assert r["question"] == mini_bank.opener.rephrase
    assert store.load(sid).pending.rephrased is True


def test_close_path_writes_mirror(tmp_path, mini_bank):
    client, store = _client(tmp_path, mini_bank,
                            [{"mirror": "nobody asked me to do any of it", "take_home": "What would it take to stop?"}],
                            [LONG])
    sid = client.post("/api/session", json={"subject_code": "S01"}).json()["session_id"]
    s = store.load(sid)
    s.started_at -= 1000            # force the hard-close guard
    store.save(s)
    body = _post_audio(client, sid).json()
    assert body["kind"] == "close" and body["mirror"] == "nobody asked me to do any of it"
    assert store.load(sid).closed is True


def test_state_endpoint(tmp_path, mini_bank):
    client, _ = _client(tmp_path, mini_bank, [], [])
    sid = client.post("/api/session", json={"subject_code": "S01"}).json()["session_id"]
    st = client.get(f"/api/session/{sid}/state").json()
    assert st["slot"] == 1 and st["closed"] is False and "elapsed" in st and st["pending"]["question_id"] is None


def test_resume_returns_pending_question(tmp_path, mini_bank):
    client, _ = _client(tmp_path, mini_bank, [], [])
    sid = client.post("/api/session", json={"subject_code": "S01"}).json()["session_id"]
    r = client.post(f"/api/session/{sid}/resume").json()
    assert r["kind"] == "spine" and r["slot"] == 1 and r["question"] == mini_bank.opener.text
```

- [ ] **Step 2: Run to verify failure**

Run: `uv run pytest tests/test_server.py -v`
Expected: `ModuleNotFoundError: No module named 'ember.server'`

- [ ] **Step 3: Implement**

`ember/server.py`:
```python
"""HTTP surface for the subject screen and the operator view (spec §8, §9)."""
import asyncio
import tempfile
import time
from pathlib import Path

from fastapi import FastAPI, UploadFile, File, HTTPException
from fastapi.responses import FileResponse, JSONResponse
from pydantic import BaseModel

from .engine import Engine, Next
from .guards import STT_MIN_WORDS, MAX_RETRIES
from .session import Session, Turn
from .store import SessionStore
from .audio import to_wav
from .text import word_count

STATIC = Path(__file__).parent / "static"


class NewSession(BaseModel):
    subject_code: str


def create_app(store: SessionStore, engine: Engine, transcriber) -> FastAPI:
    app = FastAPI(title="ember")
    app.state.store, app.state.engine, app.state.transcriber = store, engine, transcriber
    app.state.to_wav = to_wav

    def _load(sid: str) -> Session:
        try:
            return store.load(sid)
        except FileNotFoundError:
            raise HTTPException(404, "unknown session")

    def _ask(session: Session, nxt: Next, now: float) -> dict:
        session.pending = Turn(slot=nxt.slot, kind=nxt.kind, question_id=nxt.question_id, question=nxt.text, asked_at=now)
        session.retries = 0
        store.append_engine_log(session.session_id, {"at": now, "kind": nxt.kind, "question_id": nxt.question_id,
                                                     "fallback_used": nxt.fallback_used, **nxt.log})
        store.save(session)
        return {"kind": nxt.kind, "question": nxt.text, "slot": nxt.slot}

    def _close(session: Session, now: float) -> dict:
        out = engine.close(session)
        session.pending = None
        session.closed, session.mirror, session.take_home = True, out.mirror, out.take_home
        store.append_engine_log(session.session_id, {"at": now, "kind": "close", "mirror": out.mirror, "take_home": out.take_home})
        store.save(session)
        return {"kind": "close", "mirror": out.mirror, "take_home": out.take_home}

    @app.post("/api/session")
    def new_session(body: NewSession):
        now = time.time()
        session = store.create(body.subject_code, consent_at=now, now=now)
        resp = _ask(session, engine.first(), now)
        return {"session_id": session.session_id, **resp}

    @app.post("/api/session/{sid}/answer")
    async def answer(sid: str, audio: UploadFile = File(...)):
        session = _load(sid)
        if session.closed or session.pending is None:
            raise HTTPException(409, "session is closed")
        now = time.time()
        idx = len(session.turns) + 1
        with tempfile.NamedTemporaryFile(suffix=".webm", delete=False) as tmp:
            tmp.write(await audio.read())
            src = Path(tmp.name)
        wav = app.state.to_wav(src, store.dir_for(sid) / "audio" / f"q{idx}.wav")
        src.unlink(missing_ok=True)
        text = await asyncio.to_thread(app.state.transcriber.transcribe, wav)

        if word_count(text) < STT_MIN_WORDS:
            session.retries += 1
            if session.retries <= MAX_RETRIES:
                store.save(session)
                return {"retry": True, "question": session.pending.question, "message": "Didn't catch that — once more?"}
            session.pending.skipped, session.pending.answer, session.pending.answered_at = True, "", now
        else:
            session.pending.answer, session.pending.answered_at = text, now
        session.turns.append(session.pending)
        session.pending, session.retries = None, 0
        store.save(session)

        nxt = await asyncio.to_thread(engine.next, session, now)
        if nxt.kind == "close":
            store.append_engine_log(sid, {"at": now, "kind": "close-decision", **nxt.log})
            return await asyncio.to_thread(_close, session, now)
        return _ask(session, nxt, now)

    @app.post("/api/session/{sid}/rephrase")
    def rephrase(sid: str):
        session = _load(sid)
        if session.pending is None:
            raise HTTPException(409, "nothing pending")
        p = session.pending
        if p.kind == "spine":
            p.question = engine.bank.opener.rephrase if p.question_id is None else engine.bank.by_id(p.question_id).rephrase
        p.rephrased = True
        store.save(session)
        return {"question": p.question}

    @app.post("/api/session/{sid}/resume")
    def resume(sid: str):
        s = _load(sid)
        if s.closed:
            return {"kind": "close", "mirror": s.mirror, "take_home": s.take_home}
        if s.pending is None:
            raise HTTPException(409, "no pending question")
        return {"kind": s.pending.kind, "question": s.pending.question, "slot": s.pending.slot}

    @app.get("/api/session/{sid}/state")
    def state(sid: str):
        s = _load(sid)
        return {"session_id": s.session_id, "subject_code": s.subject_code, "elapsed": time.time() - s.started_at,
                "slot": s.current_slot(), "closed": s.closed, "probes_used": s.probes_used,
                "surfaced_tags": s.surfaced_tags, "retries": s.retries,
                "pending": ({"question_id": s.pending.question_id, "question": s.pending.question, "kind": s.pending.kind}
                            if s.pending else None),
                "last_answer": s.last_answer()[:200], "mirror": s.mirror, "take_home": s.take_home}

    @app.get("/")
    def subject_page():
        return FileResponse(STATIC / "subject.html")

    @app.get("/operator")
    def operator_page():
        return FileResponse(STATIC / "operator.html")

    return app
```

- [ ] **Step 4: Run to verify pass**

Run: `uv run pytest tests/test_server.py -v`
Expected: `7 passed`

- [ ] **Step 5: Commit**

```bash
git add ember/server.py tests/test_server.py
git commit -m "feat: FastAPI session, answer, rephrase, state routes with retry and close flow" \
  -m "Co-Authored-By: WOZCODE <contact@withwoz.com>" \
  -m "Claude-Session: https://claude.ai/code/session_011xY91ug8K4Ke8JHFsa5ekB"
```

---

### Task 14: Subject and operator screens

**Files:**
- Create: `ember/static/subject.html`, `ember/static/operator.html`, `tests/test_static.py`

**Interfaces:**
- Consumes: routes from Task 13.
- Produces: the two pages. Subject page: consent → opener → hold-space recording → "…" → next question → close screen. Operator page polls `/api/session/{sid}/state` every 2 s.

- [ ] **Step 1: Write the failing test**

`tests/test_static.py`:
```python
from pathlib import Path
from fastapi.testclient import TestClient

from ember.engine import Engine
from ember.server import create_app
from ember.store import SessionStore
from tests.conftest import FakeLLM

STATIC = Path("ember/static")


def test_pages_served_and_wired(tmp_path, mini_bank):
    app = create_app(SessionStore(tmp_path / "s"), Engine(mini_bank, FakeLLM()), transcriber=None)
    c = TestClient(app)
    subj = c.get("/").text
    op = c.get("/operator").text
    for needle in ("/api/session", "/answer", "/rephrase", "/resume", "MediaRecorder", "keydown", "id=\"consent\"", "id=\"question\"", "id=\"close\""):
        assert needle in subj, needle
    assert "/state" in op and "setInterval" in op
    assert 'id="transcript"' not in subj and "last_answer" not in subj   # subject never sees their transcript
```

- [ ] **Step 2: Run to verify failure**

Run: `uv run pytest tests/test_static.py -v`
Expected: `RuntimeError: File at path … subject.html does not exist` (or 404 assertion).

- [ ] **Step 3: Write the subject page**

`ember/static/subject.html`:
```html
<!doctype html>
<meta charset="utf-8">
<title>ember</title>
<style>
  html,body{height:100%;margin:0;background:#0f0f10;color:#ececec;font:400 20px/1.4 -apple-system,system-ui,sans-serif}
  main{max-width:820px;margin:0 auto;padding:12vh 6vw;display:flex;flex-direction:column;min-height:100%;box-sizing:border-box}
  section{display:none}section.on{display:block}
  h1{font-size:2.4rem;line-height:1.25;font-weight:500;margin:0 0 1.2em}
  p{color:#bdbdbd}button{font:inherit;padding:.7em 1.3em;border:0;border-radius:10px;background:#ececec;color:#111;cursor:pointer}
  .hint{margin-top:auto;color:#7a7a7a;font-size:.9rem}
  .rec{color:#ff5a5a}.wait{color:#7a7a7a}
  #mirror{font-size:1.6rem;color:#ececec;margin:0 0 1.5em}#takehome{font-size:2rem;font-weight:500}
</style>
<main>
  <section id="consent" class="on">
    <h1>Before we start</h1>
    <p>1. This is a ~7-minute psychological interview. It's recorded and transcribed.</p>
    <p>2. Transcript text goes to Anthropic, through Malek's Claude subscription, to pick questions and score. Audio stays on this laptop.</p>
    <p>3. Your session goes into a graph Malek reads. Ask him and he'll delete it.</p>
    <p><label>Subject code <input id="code" placeholder="S01" style="font:inherit;padding:.4em"></label></p>
    <p><button id="accept">I understand — start</button></p>
  </section>
  <section id="question">
    <h1 id="qtext"></h1>
    <p id="status" class="hint">Hold <b>space</b> to speak. Release when you're done.</p>
  </section>
  <section id="close">
    <p id="mirror"></p>
    <p id="takehome"></p>
    <p class="hint">That's the interview.</p>
  </section>
</main>
<script>
const $ = id => document.getElementById(id);
let sid = null, rec = null, chunks = [], busy = false, silenceTimer = null, rephrased = false;
const SILENCE_MS = 25000;

function show(id){ for (const s of document.querySelectorAll('section')) s.classList.toggle('on', s.id === id); }
function setStatus(t, cls){ $('status').textContent = t; $('status').className = 'hint ' + (cls||''); }

function armSilence(){
  clearTimeout(silenceTimer); rephrased = false;
  silenceTimer = setTimeout(async () => {
    if (busy || rephrased) return;
    const r = await fetch(`/api/session/${sid}/rephrase`, {method:'POST'}).then(r=>r.json());
    $('qtext').textContent = r.question; rephrased = true;
  }, SILENCE_MS);
}

function showQuestion(body){
  if (body.kind === 'close'){ $('mirror').textContent = '“' + body.mirror + '”'; $('takehome').textContent = body.take_home; show('close'); return; }
  $('qtext').textContent = body.question; setStatus('Hold space to speak. Release when you\'re done.'); show('question'); armSilence();
}

$('accept').onclick = async () => {
  const code = $('code').value.trim() || 'S00';
  const stream = await navigator.mediaDevices.getUserMedia({audio:true});
  rec = new MediaRecorder(stream, {mimeType:'audio/webm'});
  rec.ondataavailable = e => chunks.push(e.data);
  rec.onstop = send;
  const body = await fetch('/api/session', {method:'POST', headers:{'content-type':'application/json'}, body: JSON.stringify({subject_code: code})}).then(r=>r.json());
  sid = body.session_id; showQuestion(body);
};

(async () => {                       // crash recovery: open /?sid=<session id> to resume at the pending question
  const sid0 = new URLSearchParams(location.search).get('sid');
  if (!sid0) return;
  const stream = await navigator.mediaDevices.getUserMedia({audio:true});
  rec = new MediaRecorder(stream, {mimeType:'audio/webm'}); rec.ondataavailable = e => chunks.push(e.data); rec.onstop = send;
  sid = sid0; showQuestion(await fetch(`/api/session/${sid}/resume`, {method:'POST'}).then(r=>r.json()));
})();

window.addEventListener('keydown', e => {
  if (e.code !== 'Space' || busy || !rec || rec.state === 'recording' || !$('question').classList.contains('on')) return;
  e.preventDefault(); clearTimeout(silenceTimer); chunks = []; rec.start(); setStatus('● recording — release space when done', 'rec');
});
window.addEventListener('keyup', e => {
  if (e.code !== 'Space' || !rec || rec.state !== 'recording') return;
  e.preventDefault(); rec.stop();
});

async function send(){
  busy = true; setStatus('…', 'wait');
  const blob = new Blob(chunks, {type:'audio/webm'});
  const fd = new FormData(); fd.append('audio', blob, 'answer.webm');
  const body = await fetch(`/api/session/${sid}/answer`, {method:'POST', body: fd}).then(r=>r.json());
  busy = false;
  if (body.retry){ setStatus(body.message + '  Hold space to speak.'); armSilence(); return; }
  showQuestion(body);
}
</script>
```

- [ ] **Step 4: Write the operator page**

`ember/static/operator.html`:
```html
<!doctype html>
<meta charset="utf-8">
<title>ember · operator</title>
<style>
  body{margin:0;background:#111;color:#ddd;font:14px/1.5 ui-monospace,Menlo,monospace;padding:24px}
  input{font:inherit;background:#222;color:#ddd;border:1px solid #444;padding:.3em .5em}
  dl{display:grid;grid-template-columns:140px 1fr;gap:.3em 1em}dt{color:#888}
  .big{font-size:2rem}.warn{color:#ff9a3c}
</style>
<p><label>session id <input id="sid" size="40"></label> <span id="err" class="warn"></span></p>
<dl>
  <dt>elapsed</dt><dd id="elapsed" class="big">–</dd>
  <dt>slot</dt><dd id="slot"></dd>
  <dt>pending</dt><dd id="pending"></dd>
  <dt>probes used</dt><dd id="probes"></dd>
  <dt>tags</dt><dd id="tags"></dd>
  <dt>retries</dt><dd id="retries"></dd>
  <dt>last answer</dt><dd id="last"></dd>
  <dt>closed</dt><dd id="closed"></dd>
  <dt>mirror</dt><dd id="mirror"></dd>
  <dt>take-home</dt><dd id="takehome"></dd>
</dl>
<script>
const $ = id => document.getElementById(id);
const mmss = s => `${String(Math.floor(s/60)).padStart(2,'0')}:${String(Math.floor(s%60)).padStart(2,'0')}`;
async function tick(){
  const sid = $('sid').value.trim(); if (!sid) return;
  const r = await fetch(`/api/session/${sid}/state`);
  if (!r.ok){ $('err').textContent = 'unknown session'; return; } $('err').textContent = '';
  const s = await r.json();
  $('elapsed').textContent = mmss(s.elapsed); $('elapsed').className = 'big' + (s.elapsed > 270 ? ' warn' : '');
  $('slot').textContent = s.slot; $('probes').textContent = s.probes_used; $('retries').textContent = s.retries;
  $('pending').textContent = s.pending ? `${s.pending.kind} ${s.pending.question_id || '(opener/probe)'} — ${s.pending.question}` : '—';
  $('tags').textContent = s.surfaced_tags.join(', ') || '—'; $('last').textContent = s.last_answer || '—';
  $('closed').textContent = s.closed; $('mirror').textContent = s.mirror || '—'; $('takehome').textContent = s.take_home || '—';
}
setInterval(tick, 2000);
</script>
```

- [ ] **Step 5: Run to verify pass**

Run: `uv run pytest tests/test_static.py -v`
Expected: `1 passed`

- [ ] **Step 6: Commit**

```bash
git add ember/static/ tests/test_static.py
git commit -m "feat: subject screen (consent, hold-space, close) and operator status page" \
  -m "Co-Authored-By: WOZCODE <contact@withwoz.com>" \
  -m "Claude-Session: https://claude.ai/code/session_011xY91ug8K4Ke8JHFsa5ekB"
```

---

### Task 15: CLI `ember serve` and a real end-to-end run

**Files:**
- Create: `ember/cli.py`, `tests/test_cli.py`

**Interfaces:**
- Consumes: `guard_environment`, `LLM` (8); `load_bank` (4); `Engine` (9); `Transcriber` (11); `SessionStore` (12); `create_app` (13).
- Produces: `main(argv: list[str] | None = None) -> int`; command `ember serve [--port 8765] [--sessions ./sessions]`.

- [ ] **Step 1: Write the failing test**

`tests/test_cli.py`:
```python
import subprocess, sys


def test_cli_help_lists_serve():
    out = subprocess.run([sys.executable, "-m", "ember.cli", "--help"], capture_output=True, text=True)
    assert out.returncode == 0 and "serve" in out.stdout


def test_cli_refuses_api_key(monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-test")
    from ember.cli import main
    import pytest
    with pytest.raises(SystemExit, match="ANTHROPIC_API_KEY"):
        main(["serve", "--no-warm", "--port", "0"])
```

- [ ] **Step 2: Run to verify failure**

Run: `uv run pytest tests/test_cli.py -v`
Expected: `No module named ember.cli`

- [ ] **Step 3: Implement**

`ember/cli.py`:
```python
"""Command line entry point. v1: `ember serve`. Plan B adds `observe` and `export`."""
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


if __name__ == "__main__":
    raise SystemExit(main())
```

- [ ] **Step 4: Run to verify pass**

Run: `uv run pytest tests/test_cli.py -v`
Expected: `2 passed`

- [ ] **Step 5: Full suite**

Run: `uv run pytest -v`
Expected: everything passes; `slow` and `api` tests included (recordings exist from Task 10; the STT tests take ~10 s).

- [ ] **Step 6: Real end-to-end run — manual checklist**

Run from a plain terminal (not inside Claude Code): `cd ~/Desktop/ember && uv run ember serve`

1. Open `http://127.0.0.1:8765/` in Chrome. Consent screen shows the three lines and a code field. Enter `S00`, click start, allow the microphone.
2. Opener appears. Hold space, speak a ~30-second answer, release. Status shows "…" then the next question within ~6 s.
3. Open `http://127.0.0.1:8765/operator` in a second tab, paste the session id from `sessions/` — elapsed, slot, tags, and last answer update every 2 s.
4. Answer with two words. "Didn't catch that — once more?" appears; the question stays. Do it twice more — it skips to the next question.
5. Stay silent 25 s on a question — the gentler rephrase appears.
6. Continue answering until the close. Mirror and take-home appear; the subject screen holds them.
7. Check `sessions/S00_*/`: `transcript.json` has only Q/A + timestamps; `engine_log.json` has one entry per turn with `offered`, `latency_ms`, `meta.usage`; `audio/` has one wav per answer.
8. Note the observed release-to-next-question gap in the spec Appendix B (`end-to-end turn latency, first real run: <N> s`).

- [ ] **Step 7: Commit**

```bash
git add ember/cli.py tests/test_cli.py docs/superpowers/specs/2026-09-11-ember-v1-design.md
git commit -m "feat: ember serve CLI; end-to-end interview loop verified" \
  -m "Co-Authored-By: WOZCODE <contact@withwoz.com>" \
  -m "Claude-Session: https://claude.ai/code/session_011xY91ug8K4Ke8JHFsa5ekB"
```

---

## What Plan B covers (not in this plan)

`ember observe <session_dir>` (spec §6, reads only `transcript.json` + `rubric.yaml`), the calibration harness against hand scores, `ember export` → `graph/data.json`, the static cohort-scatter → radar page (§7), and the pilot protocol document (§10). Plan B is written after this plan is executed, against the real `transcript.json` files it produces.
