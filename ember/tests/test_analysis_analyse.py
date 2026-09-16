import json

from ember.analysis import analyse
from ember.bank import load_bank
from ember.constructs import CONSTRUCTS


def _subject(code: str, **kw) -> dict:
    base = {c: 4 for c in CONSTRUCTS}
    base.update(kw)
    return {"subject_code": code, "session_id": f"{code}_t",
            "scores": {c: {"score": v, "signal": "med", "evidence": []} for c, v in base.items()}}


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
    """k=2 is the real structure here: six subjects in two opposing shapes."""
    groups = {frozenset(g["members"]) for g in analyse(_cohort(), load_bank(), k=2)["groups"]}
    assert frozenset({"H0", "H1", "H2"}) in groups
    assert frozenset({"L0", "L1", "L2"}) in groups


def test_f1_is_a_constant_because_nobody_varies_on_it():
    assert "F1" in analyse(_cohort(), load_bank())["constants"]


def test_bank_coverage_counts_questions_per_construct():
    cov = analyse(_cohort(), load_bank())["bank_coverage"]
    assert set(cov) == set(CONSTRUCTS)
    assert sum(cov.values()) > 0 and all(isinstance(v, int) for v in cov.values())


def test_analyse_is_deterministic():
    c = _cohort()
    assert analyse(c, load_bank()) == analyse(list(reversed(c)), load_bank())


def test_collect_embeds_analysis_without_dropping_existing_keys(tmp_path):
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


def test_pilot_runs_are_excluded_from_typing():
    """TEST and S00 are operator dry-runs, not study subjects."""
    cohort = _cohort() + [_subject("TEST", F1=7, G3=1), _subject("S00", F1=1, G3=7)]
    a = analyse(cohort, load_bank())
    assert "TEST" in a["excluded"] and "S00" in a["excluded"]
    assert "pilot" in a["excluded"]["TEST"].lower()
    assert "TEST" not in a["order"] and "S00" not in a["order"]


def test_pilot_list_is_overridable():
    a = analyse(_cohort(), load_bank(), pilots=("H0",))
    assert "H0" in a["excluded"] and "H0" not in a["order"]


def test_pilots_are_excluded_from_the_construct_split_too():
    """A dry-run's scores must not decide whether a construct is a cohort constant."""
    cohort = [_subject(f"S{i}", F1=1) for i in range(6)]
    assert "F1" in analyse(cohort, load_bank())["constants"]
    # one pilot scoring high on F1 must not flip it to a discriminator
    assert "F1" in analyse(cohort + [_subject("TEST", F1=7)], load_bank())["constants"]


def test_engagement_outliers_stay_in_the_construct_stats():
    """Spec §2.5: excluded from typing, but their scores are real data."""
    a = analyse(_cohort(), load_bank())
    assert a["stats"]["F1"]["n"] == a["n_total"], "stats should cover every non-pilot subject"
