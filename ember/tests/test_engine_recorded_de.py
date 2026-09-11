import pytest

from ember.bank import load_bank
from ember.engine import Engine
from ember.llm import LLM, guard_environment
from ember.session import Turn
from ember.text import contains_verbatim, extract_quote
from tests.conftest import make_session
from tests.recording import RecordingLLM

pytestmark = pytest.mark.api

ANSWER = ("Mein Mitbewohner Karim. Alle in unserem Jahrgang reden davon, etwas zu starten, und er fängt einfach an. "
          "Er wurde zweimal abgelehnt und hatte beide Male eine Woche später eine neue Version. Er wartet nicht "
          "darauf, sich bereit zu fühlen. Ich warte ständig darauf, mich bereit zu fühlen.")


@pytest.fixture(scope="module")
def engine():
    guard_environment()
    return Engine(load_bank("de"), RecordingLLM(inner=LLM()))


def test_german_turn_is_german_and_verbatim(engine):
    s = make_session(now=0.0)
    s.language = "de"
    s.turns.append(Turn(slot=1, kind="spine", question_id=None, question=engine.bank.opener.text,
                        asked_at=0.0, answer=ANSWER, answered_at=40.0))
    n = engine.next(s, now=45.0)
    assert n.kind in ("spine", "probe")
    if n.kind == "probe":
        q = extract_quote(n.text)
        assert q and contains_verbatim(ANSWER, q, min_words=3, max_words=6)
        assert any(w in n.text.lower() for w in ("du", "gesagt", "hast")), n.text
    else:
        assert n.question_id in n.log["offered"] or n.fallback_used
        assert engine.bank.by_id(n.question_id).language == "de"
