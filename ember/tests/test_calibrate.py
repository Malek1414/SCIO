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
