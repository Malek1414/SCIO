import json
from pathlib import Path

from ember.bank import load_bank
from ember.constructs import CONSTRUCTS
from ember.observer import coverage, observe_session
from tests.conftest import FakeLLM


def _de_turn() -> dict:
    de = load_bank("de")
    q = de.candidates[0]
    return {"session_id": "X_1", "subject_code": "X", "language": "de", "turns": [
        {"kind": "spine", "slot": 1, "question": q.text, "answer": "Eine ehrliche Antwort, lang genug.", "skipped": False}]}


def _observer_payload() -> dict:
    return {"constructs": {c: {"score": 4, "evidence": [], "note": ""} for c in CONSTRUCTS},
            "declined": [], "flags": []}


def test_german_transcript_has_coverage_against_german_bank():
    assert any(coverage(_de_turn(), load_bank("de")).values())


def test_german_transcript_has_no_coverage_against_english_bank():
    """Documents the bug: this is what the observe path did for every German session."""
    assert not any(coverage(_de_turn(), load_bank("en")).values())


def test_observe_session_uses_the_transcripts_language(tmp_path: Path):
    de = load_bank("de")
    q = de.candidates[0]
    d = tmp_path / "X_1"
    d.mkdir()
    (d / "transcript.json").write_text(json.dumps({
        "session_id": "X_1", "subject_code": "X", "language": "de", "started_at": 0, "closed": True,
        "mirror": "m", "take_home": "t",
        "turns": [{"kind": "spine", "slot": 1, "question": q.text,
                   "answer": "Eine ehrliche Antwort, lang genug.", "skipped": False}]}), encoding="utf-8")

    observe_session(d, load_bank("en"), FakeLLM([_observer_payload()]))   # caller passes the WRONG bank
    out = json.loads((d / "observer.json").read_text(encoding="utf-8"))
    assert len(out["declined"]) < 9, "all nine declined means coverage ran against the wrong bank"
