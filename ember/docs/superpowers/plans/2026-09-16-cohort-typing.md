# Cohort Typing & Heat Signature Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the cohort scatter with a four-panel page driven by a deterministic, tested typing analysis, and fix the bug that invalidates `signal`/`declined` for 83% of the cohort.

**Architecture:** All statistics live in a new pure-function module `ember/analysis.py` — no I/O, no LLM, deterministic. `export.collect()` calls it and writes the result into `graph/data.js` under a new additive `analysis` key. `graph/index.html` renders what it is given and computes nothing but layout.

**Tech Stack:** Python 3.12 (`uv`), pytest, d3 (already vendored in `graph/index.html`), no new dependencies.

## Global Constraints

- **No new runtime dependencies.** No numpy, no scipy. Pure stdlib (`statistics`, `itertools`, `dataclasses`).
- **`ember/analysis.py` performs no file, network, or LLM access.** Pure functions over data passed in.
- **Deterministic output.** Same input → byte-identical output. Break every tie by subject code.
- **Additive data contract.** `data.js` keeps all existing keys. New material goes under `analysis`.
- **Construct order is fixed:** `("F1","F2","F3","C1","C2","C3","G1","G2","G3")` — import `CONSTRUCTS` from `ember.constructs`, never re-declare it.
- **Scores are 1–7 integers**, all oriented so high = stronger (F3's inversion is applied at scoring time, not here).
- Run tests with `unset ANTHROPIC_API_KEY && uv run pytest`.
- Commit after every task.

---

### Task 1: Fix the bank-language bug in the observe path

Independent of everything else. Do it first — it is the defect in §6 of the spec.

**Files:**
- Modify: `ember/observer.py` (`observe_session`, line 164)
- Modify: `ember/cli.py:110`
- Test: `tests/test_observer_language.py` (create)

**Interfaces:**
- Consumes: `ember.bank.load_bank(lang: str = "en")`, existing.
- Produces: `observe_session(session_dir, bank, llm, *, bank_for_language=None)` — resolves the bank from the transcript's `language` when the passed bank's language differs.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_observer_language.py
import json
from pathlib import Path

from ember.bank import load_bank
from ember.observer import coverage


def _de_transcript() -> dict:
    """A German spine turn whose question text comes from the German bank."""
    de = load_bank("de")
    q = de.candidates[0]
    return {"session_id": "X_1", "subject_code": "X", "language": "de", "turns": [
        {"kind": "spine", "question": q.text, "answer": "Eine ehrliche Antwort, lang genug.", "skipped": False}]}


def test_german_transcript_has_coverage_against_german_bank():
    cov = coverage(_de_transcript(), load_bank("de"))
    assert any(cov.values()), "German bank must register coverage for a German transcript"


def test_german_transcript_has_no_coverage_against_english_bank():
    """Documents the bug: this is what the observe path was doing for every German session."""
    cov = coverage(_de_transcript(), load_bank("en"))
    assert not any(cov.values())
```

- [ ] **Step 2: Run it to confirm the first test fails and the second passes**

Run: `unset ANTHROPIC_API_KEY && uv run pytest tests/test_observer_language.py -v`
Expected: `test_german_transcript_has_coverage_against_german_bank` PASSES (coverage works when given the right bank) and `..._english_bank` PASSES. If both pass, the unit is fine and the defect is purely in the caller — proceed to Step 3, which tests the caller.

- [ ] **Step 3: Write the failing caller test**

```python
# append to tests/test_observer_language.py
from ember.observer import observe_session


# Reuse the existing double from tests/conftest.py — it implements call_json(system=, user=,
# schema=, effort=), which is what observer.score() actually calls.
from tests.conftest import FakeLLM


def _observer_payload() -> dict:
    from ember.constructs import CONSTRUCTS
    return {"constructs": {c: {"score": 4, "evidence": [], "note": ""} for c in CONSTRUCTS},
            "declined": [], "flags": []}


def test_observe_session_uses_the_transcripts_language(tmp_path: Path):
    de = load_bank("de")
    q = de.candidates[0]
    d = tmp_path / "X_1"
    d.mkdir()
    (d / "transcript.json").write_text(json.dumps({
        "session_id": "X_1", "subject_code": "X", "language": "de", "started_at": 0, "closed": True,
        "mirror": "m", "take_home": "t",
        "turns": [{"kind": "spine", "question": q.text, "answer": "Eine ehrliche Antwort, lang genug.",
                   "skipped": False}]}), encoding="utf-8")

    observe_session(d, load_bank("en"), FakeLLM([_observer_payload()]))          # caller passes the WRONG bank, as cli.py does
    out = json.loads((d / "observer.json").read_text(encoding="utf-8"))
    assert len(out["declined"]) < 9, "all nine declined means coverage was computed against the wrong bank"
```

- [ ] **Step 4: Run it to verify it fails**

Run: `unset ANTHROPIC_API_KEY && uv run pytest tests/test_observer_language.py::test_observe_session_uses_the_transcripts_language -v`
Expected: FAIL — `assert 9 < 9`.

- [ ] **Step 5: Fix `observe_session` to resolve the bank from the transcript**

```python
# ember/observer.py — replace observe_session
def observe_session(session_dir: Path, bank: Bank, llm) -> Path:
    transcript = json.loads((session_dir / "transcript.json").read_text(encoding="utf-8"))
    lang = transcript.get("language", "en")
    if lang != bank.language:                    # coverage() keys on question TEXT, which is per-language
        from .bank import load_bank
        bank = load_bank(lang)
    result = score(transcript, bank, llm)
    out = session_dir / "observer.json"
    out.write_text(json.dumps(result.model_dump(), indent=2, ensure_ascii=False), encoding="utf-8")
    return out
```

- [ ] **Step 6: Run the test and the full suite**

Run: `unset ANTHROPIC_API_KEY && uv run pytest tests/test_observer_language.py -v && uv run pytest`
Expected: all PASS, no regressions.

- [ ] **Step 7: Commit**

```bash
git add ember/observer.py tests/test_observer_language.py
git commit -m "fix: score coverage against the transcript's own question bank

coverage() keys on question text, so a German transcript looked up in the
English bank matched nothing and every construct was marked declined,
collapsing signal for 83% of the cohort. Scores were never affected."
```

---

### Task 2: `analysis.py` — profile shape primitives

**Files:**
- Create: `ember/analysis.py`
- Test: `tests/test_analysis_shape.py` (create)

**Interfaces:**
- Consumes: `ember.constructs.CONSTRUCTS`.
- Produces:
  - `zprofile(scores: dict[str, int]) -> list[float]` — within-person z, in `CONSTRUCTS` order. A flat profile returns all zeros.
  - `shape_distance(a: list[float], b: list[float]) -> float` — `1 - pearson(a, b)`, in `[0.0, 2.0]`. Returns `1.0` if either vector has zero variance.
  - `FLAT_SD = 0.5` — within-person sd at or below this is "flat".

- [ ] **Step 1: Write the failing test**

```python
# tests/test_analysis_shape.py
import pytest

from ember.analysis import FLAT_SD, shape_distance, zprofile
from ember.constructs import CONSTRUCTS


def _scores(**kw) -> dict[str, int]:
    base = {c: 4 for c in CONSTRUCTS}
    base.update(kw)
    return base


def test_zprofile_is_in_construct_order_and_centred():
    z = zprofile(_scores(F1=7, G3=1))
    assert len(z) == len(CONSTRUCTS)
    assert z[CONSTRUCTS.index("F1")] > 0 > z[CONSTRUCTS.index("G3")]
    assert sum(z) == pytest.approx(0.0, abs=1e-9)


def test_flat_profile_is_all_zeros_not_a_crash():
    assert zprofile(_scores()) == [0.0] * len(CONSTRUCTS)


def test_identical_shapes_have_zero_distance():
    a = zprofile(_scores(F1=7, F2=6, G3=1))
    assert shape_distance(a, a) == pytest.approx(0.0, abs=1e-9)


def test_same_shape_different_level_is_still_zero_distance():
    """The whole point: level must not drive typing."""
    low = zprofile({"F1": 3, "F2": 2, "F3": 1, "C1": 2, "C2": 1, "C3": 3, "G1": 1, "G2": 2, "G3": 3})
    high = zprofile({"F1": 6, "F2": 5, "F3": 4, "C1": 5, "C2": 4, "C3": 6, "G1": 4, "G2": 5, "G3": 6})
    assert shape_distance(low, high) == pytest.approx(0.0, abs=1e-9)


def test_opposite_shapes_have_distance_two():
    a = zprofile(_scores(F1=7, G3=1))
    b = zprofile(_scores(F1=1, G3=7))
    assert shape_distance(a, b) == pytest.approx(2.0, abs=1e-9)


def test_flat_profile_distance_is_one_not_nan():
    flat = zprofile(_scores())
    other = zprofile(_scores(F1=7))
    assert shape_distance(flat, other) == 1.0


def test_flat_sd_constant_is_exposed():
    assert FLAT_SD == 0.5
```

- [ ] **Step 2: Run it to verify it fails**

Run: `unset ANTHROPIC_API_KEY && uv run pytest tests/test_analysis_shape.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'ember.analysis'`.

- [ ] **Step 3: Write the implementation**

```python
# ember/analysis.py
"""Cohort typing over observer scores (spec 2026-09-16-cohort-typing-design §4.1).

Pure functions. No file access, no network, no LLM. Deterministic: every tie is
broken by subject code so the same cohort always produces byte-identical output.
"""
from __future__ import annotations

import statistics as st
from dataclasses import dataclass

from .constructs import CONSTRUCTS

FLAT_SD = 0.5          # within-person sd at or below this: no shape to cluster on
FLOOR_MAX = 4          # cohort max at or below this: the construct floors
CEILING_MIN = 5        # "scored high" threshold, used for the ≥5 counts


def zprofile(scores: dict[str, int]) -> list[float]:
    """Within-person z-score, in CONSTRUCTS order. Isolates shape from overall level."""
    v = [float(scores[c]) for c in CONSTRUCTS]
    m = st.mean(v)
    sd = st.pstdev(v)
    if sd == 0:
        return [0.0] * len(v)
    return [(x - m) / sd for x in v]


def shape_distance(a: list[float], b: list[float]) -> float:
    """Correlation distance, 1 - r, in [0, 2]. A flat vector has no shape: distance 1.0."""
    ma, mb = st.mean(a), st.mean(b)
    da = sum((x - ma) ** 2 for x in a) ** 0.5
    db = sum((y - mb) ** 2 for y in b) ** 0.5
    if da == 0 or db == 0:
        return 1.0
    r = sum((x - ma) * (y - mb) for x, y in zip(a, b)) / (da * db)
    return 1.0 - r
```

- [ ] **Step 4: Run the test to verify it passes**

Run: `unset ANTHROPIC_API_KEY && uv run pytest tests/test_analysis_shape.py -v`
Expected: all 7 PASS.

- [ ] **Step 5: Commit**

```bash
git add ember/analysis.py tests/test_analysis_shape.py
git commit -m "feat: profile shape primitives for cohort typing"
```

---

### Task 3: `analysis.py` — linkage, seriation, cuts

**Files:**
- Modify: `ember/analysis.py`
- Test: `tests/test_analysis_linkage.py` (create)

**Interfaces:**
- Consumes: `zprofile`, `shape_distance` from Task 2.
- Produces:
  - `@dataclass(frozen=True) class Merge: height: float; left: tuple[str, ...]; right: tuple[str, ...]`
  - `linkage(profiles: dict[str, list[float]]) -> list[Merge]` — average linkage, ascending height, last merge joins everything.
  - `seriate(merges: list[Merge]) -> list[str]` — row order for the heat signature.
  - `cut(merges: list[Merge], k: int) -> list[tuple[str, ...]]` — k groups, each sorted, outer list sorted by first member.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_analysis_linkage.py
import pytest

from ember.analysis import Merge, cut, linkage, seriate, zprofile


def _profiles() -> dict[str, list[float]]:
    """A, B share a shape; C is their opposite. Expected: (A,B) merge first, then C."""
    a = {"F1": 7, "F2": 6, "F3": 5, "C1": 4, "C2": 4, "C3": 3, "G1": 2, "G2": 2, "G3": 1}
    b = {"F1": 6, "F2": 6, "F3": 5, "C1": 4, "C2": 3, "C3": 3, "G1": 2, "G2": 1, "G3": 1}
    c = {"F1": 1, "F2": 2, "F3": 2, "C1": 4, "C2": 4, "C3": 5, "G1": 6, "G2": 6, "G3": 7}
    return {"A": zprofile(a), "B": zprofile(b), "C": zprofile(c)}


def test_linkage_merges_the_similar_pair_first():
    m = linkage(_profiles())
    assert len(m) == 2
    assert set(m[0].left + m[0].right) == {"A", "B"}
    assert m[0].height < m[1].height


def test_last_merge_contains_everyone():
    m = linkage(_profiles())
    assert set(m[-1].left + m[-1].right) == {"A", "B", "C"}


def test_seriate_puts_similar_subjects_adjacent():
    order = seriate(linkage(_profiles()))
    assert order.index("A") - order.index("B") in (-1, 1)
    assert len(order) == 3


def test_cut_returns_k_groups():
    m = linkage(_profiles())
    assert [set(g) for g in cut(m, 2)] == [{"A", "B"}, {"C"}]
    assert len(cut(m, 3)) == 3
    assert len(cut(m, 1)) == 1


def test_cut_rejects_impossible_k():
    m = linkage(_profiles())
    with pytest.raises(ValueError):
        cut(m, 4)


def test_linkage_is_deterministic_regardless_of_input_order():
    p = _profiles()
    forward = linkage(p)
    backward = linkage({k: p[k] for k in reversed(list(p))})
    assert forward == backward
```

- [ ] **Step 2: Run it to verify it fails**

Run: `unset ANTHROPIC_API_KEY && uv run pytest tests/test_analysis_linkage.py -v`
Expected: FAIL — `ImportError: cannot import name 'Merge'`.

- [ ] **Step 3: Write the implementation**

```python
# append to ember/analysis.py
@dataclass(frozen=True)
class Merge:
    height: float
    left: tuple[str, ...]
    right: tuple[str, ...]

    @property
    def members(self) -> tuple[str, ...]:
        return self.left + self.right


def linkage(profiles: dict[str, list[float]]) -> list[Merge]:
    """Average-linkage agglomerative clustering on shape distance.

    Ties break by the lexically smallest member, so the result never depends on
    dict insertion order.
    """
    clusters: list[tuple[str, ...]] = [(c,) for c in sorted(profiles)]
    merges: list[Merge] = []
    while len(clusters) > 1:
        best = None
        for i in range(len(clusters)):
            for j in range(i + 1, len(clusters)):
                d = st.mean(shape_distance(profiles[a], profiles[b])
                            for a in clusters[i] for b in clusters[j])
                key = (round(d, 12), min(clusters[i]), min(clusters[j]))
                if best is None or key < best[0]:
                    best = (key, d, i, j)
        _, d, i, j = best
        left, right = clusters[i], clusters[j]
        merges.append(Merge(height=d, left=left, right=right))
        clusters = [c for k, c in enumerate(clusters) if k not in (i, j)] + [left + right]
    return merges


def seriate(merges: list[Merge]) -> list[str]:
    """Row order for the heat signature: the final merge's members, in merge order."""
    if not merges:
        return []
    return list(merges[-1].members)


def cut(merges: list[Merge], k: int) -> list[tuple[str, ...]]:
    """The k groups that exist after applying all but the last k-1 merges."""
    n = len(merges) + 1
    if not 1 <= k <= n:
        raise ValueError(f"k must be in 1..{n}, got {k}")
    clusters: list[tuple[str, ...]] = [(c,) for c in sorted(seriate(merges))] if merges else []
    for m in merges[: n - k]:
        clusters = [c for c in clusters if c != m.left and c != m.right] + [m.members]
    return sorted((tuple(sorted(c)) for c in clusters), key=lambda g: g[0])
```

- [ ] **Step 4: Run the test to verify it passes**

Run: `unset ANTHROPIC_API_KEY && uv run pytest tests/test_analysis_linkage.py -v`
Expected: all 6 PASS.

- [ ] **Step 5: Commit**

```bash
git add ember/analysis.py tests/test_analysis_linkage.py
git commit -m "feat: average-linkage clustering, seriation and tree cuts"
```

---

### Task 4: `analysis.py` — constants, discriminators, engagement outliers

**Files:**
- Modify: `ember/analysis.py`
- Test: `tests/test_analysis_split.py` (create)

**Interfaces:**
- Consumes: `FLAT_SD`, `FLOOR_MAX`, `CEILING_MIN` from Task 2.
- Produces:
  - `engagement_outliers(subjects: list[dict]) -> dict[str, str]` — `subject_code → reason`, for subjects whose within-person sd ≤ `FLAT_SD`.
  - `constants_and_discriminators(subjects: list[dict]) -> dict` — `{"constants": [...], "discriminators": [...], "stats": {cid: {...}}}`.
  - Subject dicts are the `graph/data.js` shape: `{"subject_code": str, "scores": {cid: {"score": int, ...}}, ...}`.
  - `score_of(subject: dict, cid: str) -> int` — tolerates both the nested `{"score": n}` and bare-int forms.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_analysis_split.py
from ember.analysis import constants_and_discriminators, engagement_outliers, score_of
from ember.constructs import CONSTRUCTS


def _subject(code: str, **kw) -> dict:
    base = {c: 4 for c in CONSTRUCTS}
    base.update(kw)
    return {"subject_code": code, "scores": {c: {"score": v, "signal": "med", "evidence": []}
                                             for c, v in base.items()}}


def test_score_of_reads_both_shapes():
    assert score_of(_subject("A", F1=6), "F1") == 6
    assert score_of({"subject_code": "B", "scores": {"F1": 3}}, "F1") == 3


def test_flat_subject_is_an_engagement_outlier():
    out = engagement_outliers([_subject("FLAT"), _subject("VARIED", F1=7, G3=1)])
    assert "FLAT" in out and "VARIED" not in out
    assert out["FLAT"]


def test_construct_that_never_exceeds_floor_is_a_constant():
    subs = [_subject(f"S{i}", F1=1, C3=6, F2=1 + (i % 6)) for i in range(8)]
    split = constants_and_discriminators(subs)
    assert "F1" in split["constants"], "F1 maxes at 1 across the cohort"
    assert "F2" in split["discriminators"], "F2 varies from 1 to 6"


def test_uniformly_high_construct_is_also_a_constant():
    subs = [_subject(f"S{i}", C3=6, F2=1 + (i % 6)) for i in range(8)]
    split = constants_and_discriminators(subs)
    assert "C3" in split["constants"], "a construct everyone scores 6 on distinguishes nobody"


def test_stats_report_mean_max_and_high_count():
    subs = [_subject(f"S{i}", F1=1) for i in range(4)]
    s = constants_and_discriminators(subs)["stats"]["F1"]
    assert s["mean"] == 1.0 and s["max"] == 1 and s["n_high"] == 0 and s["n"] == 4


def test_every_construct_lands_in_exactly_one_side():
    subs = [_subject(f"S{i}", F1=1 + (i % 6), C3=6) for i in range(8)]
    split = constants_and_discriminators(subs)
    assert sorted(split["constants"] + split["discriminators"]) == sorted(CONSTRUCTS)
    assert not set(split["constants"]) & set(split["discriminators"])
```

- [ ] **Step 2: Run it to verify it fails**

Run: `unset ANTHROPIC_API_KEY && uv run pytest tests/test_analysis_split.py -v`
Expected: FAIL — `ImportError: cannot import name 'score_of'`.

- [ ] **Step 3: Write the implementation**

```python
# append to ember/analysis.py
def score_of(subject: dict, cid: str) -> int:
    """Read one construct score. data.js nests it under "score"; older shapes store a bare int."""
    v = subject["scores"][cid]
    return int(v["score"]) if isinstance(v, dict) else int(v)


def engagement_outliers(subjects: list[dict]) -> dict[str, str]:
    """Subjects with no usable shape. A flat profile clusters arbitrarily, so it must not be typed."""
    out: dict[str, str] = {}
    for s in sorted(subjects, key=lambda x: x["subject_code"]):
        v = [score_of(s, c) for c in CONSTRUCTS]
        sd = st.pstdev(v)
        if sd <= FLAT_SD:
            out[s["subject_code"]] = (f"flat profile (sd {sd:.2f} ≤ {FLAT_SD}, mean {st.mean(v):.1f}) "
                                      f"— no shape to type on")
    return out


def constants_and_discriminators(subjects: list[dict]) -> dict:
    """Split the nine constructs into those that describe the cohort and those that separate it.

    A construct is a *constant* when the cohort never spreads across it — either it floors
    (max ≤ FLOOR_MAX) or everyone scores high (min ≥ CEILING_MIN).
    """
    stats: dict[str, dict] = {}
    constants: list[str] = []
    discriminators: list[str] = []
    for c in CONSTRUCTS:
        v = [score_of(s, c) for s in subjects]
        st_ = {"mean": round(st.mean(v), 2), "min": min(v), "max": max(v),
               "sd": round(st.pstdev(v), 2), "n": len(v),
               "n_high": sum(1 for x in v if x >= CEILING_MIN)}
        stats[c] = st_
        (constants if (st_["max"] <= FLOOR_MAX or st_["min"] >= CEILING_MIN)
         else discriminators).append(c)
    return {"constants": constants, "discriminators": discriminators, "stats": stats}
```

- [ ] **Step 4: Run the test to verify it passes**

Run: `unset ANTHROPIC_API_KEY && uv run pytest tests/test_analysis_split.py -v`
Expected: all 6 PASS.

- [ ] **Step 5: Commit**

```bash
git add ember/analysis.py tests/test_analysis_split.py
git commit -m "feat: split constructs into cohort constants and type discriminators"
```

---

### Task 5: `analyse()` and the `data.js` contract

**Files:**
- Modify: `ember/analysis.py`
- Modify: `ember/export.py` (`collect`)
- Test: `tests/test_analysis_analyse.py` (create)

**Interfaces:**
- Consumes: everything from Tasks 2–4, plus `ember.bank.Bank`.
- Produces: `analyse(subjects: list[dict], bank) -> dict` with exactly these keys:
  - `"order"`: `list[str]` — heat-signature row order
  - `"groups"`: `list[{"members": [...], "n": int, "mean_profile": {cid: float}, "high": [cid], "low": [cid]}]`
  - `"constants"`, `"discriminators"`, `"stats"` — from Task 4
  - `"bank_coverage"`: `{cid: int}` — questions targeting each construct
  - `"excluded"`: `{code: reason}` — from `engagement_outliers`
  - `"k"`: `int`, `"n_typed"`: `int`, `"n_total"`: `int`
- `collect()` gains `data["analysis"] = analyse(subjects, bank)`. Every existing key is untouched.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_analysis_analyse.py
from ember.analysis import analyse
from ember.bank import load_bank
from ember.constructs import CONSTRUCTS


def _subject(code: str, **kw) -> dict:
    base = {c: 4 for c in CONSTRUCTS}
    base.update(kw)
    return {"subject_code": code, "session_id": f"{code}_t", "scores":
            {c: {"score": v, "signal": "med", "evidence": []} for c, v in base.items()}}


def _cohort() -> list[dict]:
    hi = [_subject(f"H{i}", F2=6, F3=6, G2=2, G3=2, F1=1) for i in range(3)]
    lo = [_subject(f"L{i}", F2=2, F3=2, G2=6, G3=6, F1=1) for i in range(3)]
    return hi + lo + [_subject("FLAT")]


def test_analyse_excludes_flat_subjects_from_typing():
    a = analyse(_cohort(), load_bank())
    assert "FLAT" in a["excluded"]
    assert "FLAT" not in a["order"]
    assert all("FLAT" not in g["members"] for g in a["groups"])
    assert a["n_typed"] == 6 and a["n_total"] == 7


def test_analyse_separates_the_two_opposing_shapes():
    a = analyse(_cohort(), load_bank())
    groups = {frozenset(g["members"]) for g in a["groups"]}
    assert frozenset({"H0", "H1", "H2"}) in groups
    assert frozenset({"L0", "L1", "L2"}) in groups


def test_f1_is_a_constant_because_nobody_varies_on_it():
    a = analyse(_cohort(), load_bank())
    assert "F1" in a["constants"]


def test_bank_coverage_counts_questions_per_construct():
    a = analyse(_cohort(), load_bank())
    assert set(a["bank_coverage"]) == set(CONSTRUCTS)
    assert sum(a["bank_coverage"].values()) > 0
    assert all(isinstance(v, int) for v in a["bank_coverage"].values())


def test_analyse_is_deterministic():
    c = _cohort()
    assert analyse(c, load_bank()) == analyse(list(reversed(c)), load_bank())


def test_collect_embeds_analysis_without_dropping_existing_keys(tmp_path):
    import json
    from ember.export import collect
    d = tmp_path / "S1_t"
    d.mkdir()
    (d / "observer.json").write_text(json.dumps({
        "subject_id": "S1", "session_id": "S1_t", "scored_at": "2026-09-20T10:00:00+00:00",
        "rubric_version": "1.0.0",
        "constructs": {c: {"score": 4, "signal": "med", "evidence": [], "note": ""} for c in CONSTRUCTS},
        "declined": [], "flags": []}), encoding="utf-8")
    (d / "transcript.json").write_text(json.dumps(
        {"session_id": "S1_t", "subject_code": "S1", "started_at": 0, "closed": True,
         "mirror": "m", "take_home": "t", "turns": []}), encoding="utf-8")
    data = collect(tmp_path, load_bank(), now=1_757_600_000.0)
    assert {"generated_at", "rubric_version", "constructs", "subjects"} <= set(data)
    assert "analysis" in data
```

- [ ] **Step 2: Run it to verify it fails**

Run: `unset ANTHROPIC_API_KEY && uv run pytest tests/test_analysis_analyse.py -v`
Expected: FAIL — `ImportError: cannot import name 'analyse'`.

- [ ] **Step 3: Write `analyse` and `bank_coverage`**

```python
# append to ember/analysis.py
DEFAULT_K = 4


def bank_coverage(bank) -> dict[str, int]:
    """How many candidate questions target each construct. Drives the caveat annotations."""
    counts = {c: 0 for c in CONSTRUCTS}
    for q in bank.candidates:
        for t in q.targets:
            if t in counts:
                counts[t] += 1
    return counts


def analyse(subjects: list[dict], bank, *, k: int = DEFAULT_K) -> dict:
    """The whole analysis block for graph/data.js. Pure; deterministic; no I/O."""
    excluded = engagement_outliers(subjects)
    typed = sorted((s for s in subjects if s["subject_code"] not in excluded),
                   key=lambda s: s["subject_code"])
    split = constants_and_discriminators(subjects)          # stats span the FULL cohort

    groups: list[dict] = []
    order: list[str] = []
    if len(typed) >= 2:
        profiles = {s["subject_code"]: zprofile({c: score_of(s, c) for c in CONSTRUCTS}) for s in typed}
        merges = linkage(profiles)
        order = seriate(merges)
        by_code = {s["subject_code"]: s for s in typed}
        for members in cut(merges, min(k, len(typed))):
            mean_profile = {c: round(st.mean([score_of(by_code[m], c) for m in members]), 2)
                            for c in CONSTRUCTS}
            ranked = sorted(CONSTRUCTS, key=lambda c: -mean_profile[c])
            groups.append({"members": list(members), "n": len(members),
                           "mean_profile": mean_profile,
                           "high": ranked[:3], "low": ranked[-3:][::-1]})
    elif typed:
        order = [typed[0]["subject_code"]]

    return {"order": order, "groups": groups,
            "constants": split["constants"], "discriminators": split["discriminators"],
            "stats": split["stats"], "bank_coverage": bank_coverage(bank),
            "excluded": excluded, "k": len(groups),
            "n_typed": len(typed), "n_total": len(subjects)}
```

- [ ] **Step 4: Wire it into `collect()`**

In `ember/export.py`, add `from .analysis import analyse` at the top, then immediately before `collect()` returns its dict, add the `analysis` key. The existing return builds a dict of `generated_at`, `rubric_version`, `constructs` and `subjects` — add one more entry:

```python
            "analysis": analyse(subjects, bank),
```

- [ ] **Step 5: Run the tests and the full suite**

Run: `unset ANTHROPIC_API_KEY && uv run pytest tests/test_analysis_analyse.py -v && uv run pytest`
Expected: all PASS, no regressions in `test_export.py` or `test_graph_static.py`.

- [ ] **Step 6: Regenerate the real page data and eyeball it**

```bash
unset ANTHROPIC_API_KEY && uv run ember export
python3 -c "import re,json;d=json.loads(re.search(r'=\s*(\{.*\})\s*;?\s*$',open('graph/data.js').read(),re.S).group(1));a=d['analysis'];print('order',a['order']);print('constants',a['constants']);print('groups',[(g['n'],g['members']) for g in a['groups']]);print('excluded',a['excluded'])"
```

Expected: `S06` and `S10` in `excluded`; `F1`, `C2`, `G1`, `C3` among `constants`; four groups.

- [ ] **Step 7: Commit**

```bash
git add ember/analysis.py ember/export.py tests/test_analysis_analyse.py
git commit -m "feat: embed cohort typing analysis in graph data"
```

---

### Task 6: The four-panel page

**Files:**
- Modify: `graph/index.html` (full rewrite of the body and script; keep the vendored d3 tag)
- Test: `tests/test_graph_static.py` (extend)

**Interfaces:**
- Consumes: `window.EMBER_DATA.analysis` exactly as produced in Task 5. The page computes nothing but layout.

- [ ] **Step 1: Read the existing page and the existing static test**

Run: `sed -n '1,40p' graph/index.html && cat tests/test_graph_static.py`
Note how d3 is loaded and what the current test asserts, then keep both conventions.

- [ ] **Step 2: Write the failing test**

```python
# append to tests/test_graph_static.py
from pathlib import Path

PAGE = Path(__file__).resolve().parents[1] / "graph" / "index.html"


def test_page_renders_all_four_panels():
    html = PAGE.read_text(encoding="utf-8")
    for panel_id in ("panel-heat", "panel-split", "panel-groups", "panel-subject"):
        assert f'id="{panel_id}"' in html, f"missing {panel_id}"


def test_page_shows_the_data_quality_banner():
    html = PAGE.read_text(encoding="utf-8")
    assert 'id="banner"' in html


def test_page_reads_analysis_and_never_recomputes_it():
    html = PAGE.read_text(encoding="utf-8")
    assert "EMBER_DATA.analysis" in html
    for banned in ("Math.sqrt", "pstdev", "linkage("):
        assert banned not in html, f"page must not compute statistics itself ({banned})"


def test_page_makes_no_network_calls():
    html = PAGE.read_text(encoding="utf-8")
    for banned in ("fetch(", "XMLHttpRequest", "https://", "http://"):
        assert banned not in html, f"page must be offline-only ({banned})"
```

- [ ] **Step 3: Run it to verify it fails**

Run: `unset ANTHROPIC_API_KEY && uv run pytest tests/test_graph_static.py -v`
Expected: FAIL on the panel ids.

**Note:** if the existing page loads d3 from a CDN, `test_page_makes_no_network_calls` will fail for that reason. Vendor d3 into `graph/` as a local file and reference it relatively — the page must open from `file://` with no network.

- [ ] **Step 4: Build the page**

Structure, in order down the page:

```html
<div id="banner"></div>
<section id="panel-heat"></section>
<section id="panel-split"></section>
<section id="panel-groups"></section>
<section id="panel-subject"></section>
```

Render rules, each reading only from `const A = window.EMBER_DATA.analysis`:

- **`#banner`** — one line each: `n_typed` of `n_total` typed; every `excluded` entry as `code — reason`; and the fixed sentence *"signal and declined are suppressed for German sessions pending re-contribution (see spec §6)."*
- **`#panel-heat`** — a grid, one row per code in `A.order`, one column per construct in `EMBER_DATA.constructs` order. Cell fill from the score via `d3.scaleSequential(d3.interpolateYlOrRd).domain([1, 7])`. Draw a horizontal rule between rows that fall in different `A.groups`. Column headers are construct ids; put the full name in a `<title>` so hover explains it.
- **`#panel-split`** — two labelled lists from `A.constants` and `A.discriminators`. Each entry shows `stats[cid].mean`, `stats[cid].max`, `n_high/n`, and `bank_coverage[cid] + " of " + total` questions. Mark any construct whose `bank_coverage` is 1 with a visible caveat.
- **`#panel-groups`** — one card per entry in `A.groups`: `n`, members, and a small bar row of `mean_profile`, with bars for constructs in `A.discriminators` drawn in full colour and constructs in `A.constants` drawn muted.
- **`#panel-subject`** — clicking a heat row selects that subject and draws a nine-spoke radar from `EMBER_DATA.subjects`, then lists per-construct `evidence`, then `flags`, then `mirror` and `take_home`.

- [ ] **Step 5: Run the tests**

Run: `unset ANTHROPIC_API_KEY && uv run pytest tests/test_graph_static.py -v && uv run pytest`
Expected: all PASS.

- [ ] **Step 6: Open it and confirm it renders**

Run: `unset ANTHROPIC_API_KEY && uv run ember export && open graph/index.html`
Confirm by eye: four panels; the C3 column visibly lit and the F1/C2/G1 columns visibly dark across nearly every row; group separators present; clicking a row fills the subject panel.

- [ ] **Step 7: Commit**

```bash
git add graph/index.html tests/test_graph_static.py
git commit -m "feat: four-panel cohort page driven by the typing analysis"
```

---

### Task 7: Repair the two locally-held German sessions

**Files:**
- Modify: none
- Test: none (this is a data operation, verified by inspection)

**Interfaces:**
- Consumes: the Task 1 fix.

- [ ] **Step 1: Confirm both sessions currently show all nine declined**

```bash
python3 -c "
import json
for s in ('RAFAEL_2026-09-12T14-37-02','RUBEN_2026-09-12T14-53-17'):
    d=json.load(open(f'sessions/{s}/observer.json'))
    print(s, 'declined:', len(d['declined']))"
```
Expected: both print `declined: 9`.

- [ ] **Step 2: Re-observe both with the fixed path**

This calls the model and uses the operator's Claude subscription — roughly 30 seconds each.

```bash
unset ANTHROPIC_API_KEY && uv run ember observe sessions/RAFAEL_2026-09-12T14-37-02
unset ANTHROPIC_API_KEY && uv run ember observe sessions/RUBEN_2026-09-12T14-53-17
```

- [ ] **Step 3: Confirm the repair**

Re-run the Step 1 command. Expected: both now print fewer than 9. If either still prints 9, the Task 1 fix is not reaching this path — stop and re-check `observe_session`.

- [ ] **Step 4: Rebuild and commit the regenerated data**

```bash
unset ANTHROPIC_API_KEY && uv run ember export
git add graph/data.js
git commit -m "data: repair RAFAEL and RUBEN coverage with the language-correct bank"
```

**Note:** `graph/data.js` is currently gitignored. If it is still ignored, skip the `git add` and simply regenerate — do not un-ignore it, because it embeds subject quotes and the repo is public.

---

## Out of scope for this plan

Per spec §3: re-collecting the 15 contributed German sessions from interviewers, a traina-style standalone product, and any change to the engine, rubric or question bank.
