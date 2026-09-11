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


def test_language_is_recorded_in_meta_and_transcript(tmp_path: Path):
    st = SessionStore(tmp_path / "sessions")
    s = st.create("S05", consent_at=99.0, now=100.0, language="de")
    assert s.language == "de"
    assert json.loads((st.dir_for(s.session_id) / "meta.json").read_text())["language"] == "de"
    st.save(s)
    assert json.loads((st.dir_for(s.session_id) / "transcript.json").read_text())["language"] == "de"
    assert st.load(s.session_id).language == "de"
    assert st.create("S06", consent_at=1.0, now=2.0).language == "en"      # default unchanged
