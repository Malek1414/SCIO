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
