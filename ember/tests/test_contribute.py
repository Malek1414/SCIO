import json
from pathlib import Path

import pytest

from ember.contribute import ContributeError, build_result, write_result
from ember.export import collect

OBS = {
    "subject_id": "KAI", "session_id": "KAI_2026-09-12T10-00-00", "scored_at": "2026-09-12T10:05:00+00:00",
    "rubric_version": "1.0.0", "language": "de",
    "constructs": {"F1": {"score": 4, "signal": "med", "evidence": ["ich baue etwas"], "note": "n"}},
    "declined": ["F2"], "flags": ["a flag"],
}
TR = {"language": "de", "mirror": "ich baue etwas", "take_home": "Woran genau?"}


def _session(tmp_path: Path, *, scored=True) -> Path:
    d = tmp_path / "sessions" / OBS["session_id"]
    d.mkdir(parents=True)
    if scored:
        (d / "observer.json").write_text(json.dumps(OBS), encoding="utf-8")
    (d / "transcript.json").write_text(json.dumps(TR), encoding="utf-8")
    return d


def test_build_result_is_already_in_the_cohort_page_shape(tmp_path):
    r = build_result(_session(tmp_path))
    assert r["subject_code"] == "KAI" and r["session_id"] == OBS["session_id"]
    assert r["scores"]["F1"]["score"] == 4 and r["declined"] == ["F2"] and r["flags"] == ["a flag"]
    assert r["language"] == "de" and r["mirror"] == "ich baue etwas" and r["take_home"] == "Woran genau?"


def test_the_quotes_travel_because_that_is_what_was_chosen(tmp_path):
    r = build_result(_session(tmp_path))
    assert r["scores"]["F1"]["evidence"] == ["ich baue etwas"]


def test_an_unscored_session_is_refused_with_the_command_to_fix_it(tmp_path):
    with pytest.raises(ContributeError, match="ember observe"):
        build_result(_session(tmp_path, scored=False))


def test_write_result_names_the_file_after_the_session(tmp_path):
    out = write_result(build_result(_session(tmp_path)), tmp_path / "results")
    assert out.name == f"{OBS['session_id']}.json"
    assert json.loads(out.read_text(encoding="utf-8"))["subject_code"] == "KAI"


def test_a_contributed_result_reaches_the_cohort_page(tmp_path, mini_bank):
    """The receiving machine has the result file but never had the session."""
    write_result(build_result(_session(tmp_path)), tmp_path / "results")
    elsewhere = tmp_path / "no-sessions-here"
    elsewhere.mkdir()
    data = collect(elsewhere, mini_bank, results_root=tmp_path / "results")
    assert [s["session_id"] for s in data["subjects"]] == [OBS["session_id"]]
    assert data["subjects"][0]["contributed"] is True


def test_a_local_session_wins_over_a_contribution_of_the_same_id(tmp_path, mini_bank):
    d = _session(tmp_path)
    write_result(build_result(d), tmp_path / "results")
    (d / "observer.json").write_text(json.dumps({**OBS, "flags": ["local wins"]}), encoding="utf-8")
    data = collect(tmp_path / "sessions", mini_bank, results_root=tmp_path / "results")
    assert len(data["subjects"]) == 1 and data["subjects"][0]["flags"] == ["local wins"]
    assert "contributed" not in data["subjects"][0]


def test_a_broken_contribution_is_skipped_not_fatal(tmp_path, mini_bank, capsys):
    (tmp_path / "results").mkdir(parents=True)
    (tmp_path / "results" / "bad.json").write_text("{not json", encoding="utf-8")
    (tmp_path / "results" / "thin.json").write_text(json.dumps({"subject_code": "X"}), encoding="utf-8")
    (tmp_path / "sessions").mkdir(parents=True)
    data = collect(tmp_path / "sessions", mini_bank, results_root=tmp_path / "results")
    assert data["subjects"] == []
    out = capsys.readouterr().out
    assert "skipping bad.json" in out and "skipping thin.json" in out


# ── ingest: the receiving end. Everything here arrives from someone else's machine ──────────

from ember.contribute import ingest


def _sent(tmp_path: Path, payload: dict, name="sent.json") -> Path:
    f = tmp_path / name
    f.write_text(json.dumps(payload), encoding="utf-8")
    return f


def test_ingest_files_a_result_under_its_session_id(tmp_path):
    out = ingest(_sent(tmp_path, build_result(_session(tmp_path))), tmp_path / "results")
    assert out.name == f"{OBS['session_id']}.json"
    assert json.loads(out.read_text(encoding="utf-8"))["subject_code"] == "KAI"


def test_ingest_names_the_file_from_the_payload_not_the_sender(tmp_path):
    """A sender cannot choose where their file lands."""
    out = ingest(_sent(tmp_path, build_result(_session(tmp_path)), name="anything-at-all.json"),
                 tmp_path / "results")
    assert out.name == f"{OBS['session_id']}.json"


def test_ingest_refuses_a_session_id_that_would_escape_the_results_dir(tmp_path):
    bad = {**build_result(_session(tmp_path)), "session_id": "../../etc/passwd"}
    with pytest.raises(ContributeError, match="unusable session_id"):
        ingest(_sent(tmp_path, bad), tmp_path / "results")
    assert not (tmp_path / "results").exists() or list((tmp_path / "results").glob("*")) == []


def test_ingest_refuses_junk(tmp_path):
    (tmp_path / "junk.json").write_text("{not json", encoding="utf-8")
    with pytest.raises(ContributeError, match="not valid JSON"):
        ingest(tmp_path / "junk.json", tmp_path / "results")

    with pytest.raises(ContributeError, match="missing"):
        ingest(_sent(tmp_path, {"subject_code": "X"}, name="thin.json"), tmp_path / "results")

    with pytest.raises(ContributeError, match="not a file"):
        ingest(tmp_path / "nope.json", tmp_path / "results")


def test_an_ingested_result_reaches_the_cohort_page(tmp_path, mini_bank):
    ingest(_sent(tmp_path, build_result(_session(tmp_path))), tmp_path / "results")
    elsewhere = tmp_path / "no-sessions-here"
    elsewhere.mkdir()
    data = collect(elsewhere, mini_bank, results_root=tmp_path / "results")
    assert [s["session_id"] for s in data["subjects"]] == [OBS["session_id"]]
    assert data["subjects"][0]["scores"]["F1"]["evidence"] == ["ich baue etwas"]
