from pathlib import Path
from fastapi.testclient import TestClient

from ember.engine import Engine
from ember.server import create_app
from ember.store import SessionStore
from tests.conftest import FakeLLM

STATIC = Path("ember/static")


def test_pages_served_and_wired(tmp_path, mini_bank):
    engines = {"en": Engine(mini_bank, FakeLLM()), "de": Engine(mini_bank, FakeLLM())}
    app = create_app(SessionStore(tmp_path / "s"), engines, {"en": None, "de": None})
    c = TestClient(app)
    subj = c.get("/").text
    op = c.get("/operator").text
    for needle in ("/api/session", "/answer", "/rephrase", "/resume", "/api/copy/", "MediaRecorder", "keydown",
                   'id="consent"', 'id="question"', 'id="close"', 'id="langbar"', 'data-lang="de"'):
        assert needle in subj, needle
    assert "/state" in op and "setInterval" in op and "language" in op
    assert 'id="transcript"' not in subj and "last_answer" not in subj   # subject never sees their transcript
