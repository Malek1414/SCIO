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
    assert "F1" in split["constants"]
    assert "F2" in split["discriminators"]


def test_uniformly_high_construct_is_also_a_constant():
    subs = [_subject(f"S{i}", C3=6, F2=1 + (i % 6)) for i in range(8)]
    assert "C3" in constants_and_discriminators(subs)["constants"]


def test_stats_report_mean_max_and_high_count():
    s = constants_and_discriminators([_subject(f"S{i}", F1=1) for i in range(4)])["stats"]["F1"]
    assert s["mean"] == 1.0 and s["max"] == 1 and s["n_high"] == 0 and s["n"] == 4


def test_every_construct_lands_in_exactly_one_side():
    subs = [_subject(f"S{i}", F1=1 + (i % 6), C3=6) for i in range(8)]
    split = constants_and_discriminators(subs)
    assert sorted(split["constants"] + split["discriminators"]) == sorted(CONSTRUCTS)
    assert not set(split["constants"]) & set(split["discriminators"])


def test_near_floor_subject_is_excluded_even_when_not_perfectly_flat():
    """S10 in the real cohort: mean 1.33, sd 0.67 — above the flatness bar, still no signal."""
    near_floor = _subject("FLOOR", **{c: 1 for c in CONSTRUCTS} | {"F3": 3, "G3": 2})
    normal = _subject("OK", F1=2, F2=5, F3=3, C1=3, C2=2, C3=5, G1=3, G2=4, G3=2)
    out = engagement_outliers([near_floor, normal])
    assert "FLOOR" in out and "OK" not in out


def test_subject_missing_a_construct_is_excluded_not_crashed_on():
    partial = {"subject_code": "PART", "scores": {"F1": {"score": 4}}}
    out = engagement_outliers([partial])
    assert "PART" in out and "missing" in out["PART"]
