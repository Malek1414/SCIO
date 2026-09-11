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


def _client(tmp_path, mini_bank, llm_responses, stt_texts, language="en"):
    store = SessionStore(tmp_path / "sessions")
    engines = {"en": Engine(mini_bank, FakeLLM(llm_responses)),
               "de": Engine(mini_bank.model_copy(update={"language": "de"}), FakeLLM(list(llm_responses)))}
    transcribers = {"en": FakeTranscriber(stt_texts), "de": FakeTranscriber(list(stt_texts))}
    app = create_app(store, engines, transcribers)

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


def test_next_question_asked_at_is_after_answer(tmp_path, mini_bank):
    client, store = _client(tmp_path, mini_bank,
                            [{"action": "pick", "candidate_id": "S2-a", "surfaced_tags": [], "reason": "r"}], [LONG])
    sid = client.post("/api/session", json={"subject_code": "S01"}).json()["session_id"]
    _post_audio(client, sid)
    s = store.load(sid)
    assert s.pending.asked_at > s.turns[-1].answered_at      # speaking time must not include processing time


def test_copy_endpoint_serves_both_languages(tmp_path, mini_bank):
    client, _ = _client(tmp_path, mini_bank, [], [])
    en = client.get("/api/copy/en").json()
    de = client.get("/api/copy/de").json()
    assert en["start"] == "I understand — start" and de["start"] == "Verstanden — los"
    assert set(en) == set(de)
    assert client.get("/api/copy/fr").json() == en          # unknown language falls back


def test_session_language_selects_store_and_state(tmp_path, mini_bank):
    client, store = _client(tmp_path, mini_bank, [], [])
    sid = client.post("/api/session", json={"subject_code": "S01", "language": "de"}).json()["session_id"]
    assert store.load(sid).language == "de"
    assert client.get(f"/api/session/{sid}/state").json()["language"] == "de"


def test_language_defaults_to_english_when_omitted(tmp_path, mini_bank):
    client, store = _client(tmp_path, mini_bank, [], [])
    sid = client.post("/api/session", json={"subject_code": "S01"}).json()["session_id"]
    assert store.load(sid).language == "en"


def test_answer_uses_the_session_language_transcriber(tmp_path, mini_bank):
    client, store = _client(tmp_path, mini_bank,
                            [{"action": "pick", "candidate_id": "S2-a", "surfaced_tags": [], "reason": "r"}],
                            [LONG])
    sid = client.post("/api/session", json={"subject_code": "S01", "language": "de"}).json()["session_id"]
    _post_audio(client, sid)
    assert store.load(sid).turns[0].answer == LONG          # the "de" transcriber was the one consulted
