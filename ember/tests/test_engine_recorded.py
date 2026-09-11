import json
from pathlib import Path
import pytest

from ember.bank import load_bank
from ember.engine import Engine
from ember.llm import LLM, guard_environment
from ember.session import Turn
from ember.text import extract_quote, contains_verbatim
from tests.conftest import make_session
from tests.recording import RecordingLLM

FIX = Path(__file__).parent / "fixtures" / "transcripts"
pytestmark = pytest.mark.api


def _session_from(name: str):
    s = make_session(now=0.0)
    at = 0.0
    for row in json.loads((FIX / f"{name}.json").read_text()):
        at += 40
        s.turns.append(Turn(slot=row["slot"], kind="spine", question_id=row["question_id"],
                            question=f"Q{row['slot']}", asked_at=at - 35, answer=row["answer"], answered_at=at))
    return s, at + 5


@pytest.fixture(scope="module")
def engine():
    guard_environment()          # strip nested Claude Code vars when run from inside a session
    return Engine(load_bank(), RecordingLLM(inner=LLM()))


@pytest.mark.parametrize("name", ["vague", "decliner", "talker", "terse", "contradicts", "family_q1"])
def test_next_produces_valid_turn(engine, name):
    s, now = _session_from(name)
    n = engine.next(s, now=now)
    assert n.kind in ("spine", "probe")
    if n.kind == "spine":
        assert n.question_id in n.log["offered"] or n.fallback_used
    else:
        q = extract_quote(n.text)
        assert q and contains_verbatim(s.last_answer(), q, min_words=3, max_words=6)
    assert all(t in {"named-project", "family", "money", "health", "loss", "faith", "relationship", "solitude",
                     "quit", "moved", "failure", "competition"} for t in s.surfaced_tags)


def test_family_answer_surfaces_family_tag(engine):
    s, now = _session_from("family_q1")
    engine.next(s, now=now)
    assert "family" in s.surfaced_tags


def test_close_on_talker_is_verbatim(engine):
    s, _ = _session_from("talker")
    out = engine.close(s)
    assert contains_verbatim(s.transcript_text(), out.mirror, min_words=5)
    assert out.take_home.endswith("?")
