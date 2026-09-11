import pytest

from ember.engine import Engine, Next, ACTION_SCHEMA, CLOSE_SCHEMA, build_system_prompt
from ember.llm import LLMError
from ember.session import Turn
from ember.guards import FIRE_GUARD_S, HARD_CLOSE_S, PROBE_WINDOW_S
from tests.conftest import FakeLLM, make_session

LONG = "I rebuilt the whole backend three times because the first two felt wrong and nobody asked me to do any of it honestly"


def _answered(s, slot, qid, answer, at):
    s.turns.append(Turn(slot=slot, kind="spine", question_id=qid, question=f"Q{slot}", asked_at=at - 30, answer=answer, answered_at=at))


def test_first_is_opener_without_llm(mini_bank):
    eng = Engine(mini_bank, FakeLLM())
    n = eng.first()
    assert n.kind == "spine" and n.slot == 1 and n.question_id is None
    assert n.text == mini_bank.opener.text


def test_system_prompt_lists_bank_and_tags(mini_bank):
    sp = build_system_prompt(mini_bank)
    assert "S3-b" in sp and "named-project" in sp and "yes/no" in sp.lower()


def test_pick_valid_candidate_and_tags(mini_bank):
    llm = FakeLLM([{"action": "pick", "candidate_id": "S2-b", "surfaced_tags": ["money", "bogus"], "reason": "r"}])
    s = make_session(now=0.0)
    _answered(s, 1, None, LONG, 40.0)
    n = Engine(mini_bank, llm).next(s, now=45.0)
    assert n.kind == "spine" and n.slot == 2 and n.question_id == "S2-b" and n.fallback_used is False
    assert s.surfaced_tags == ["money"]                      # unknown tag dropped
    assert llm.calls[0]["effort"] == "low" and llm.calls[0]["schema"] is ACTION_SCHEMA
    assert "S2-a" in llm.calls[0]["user"] and "S2-b" in llm.calls[0]["user"]


def test_pick_outside_offered_falls_back_to_default(mini_bank):
    llm = FakeLLM([{"action": "pick", "candidate_id": "S5-a", "surfaced_tags": [], "reason": "r"}])
    s = make_session(now=0.0)
    _answered(s, 1, None, LONG, 40.0)
    n = Engine(mini_bank, llm).next(s, now=45.0)
    assert n.question_id == "S2-a" and n.fallback_used is True and n.log["validation_error"]


def test_llm_error_falls_back_to_default(mini_bank):
    s = make_session(now=0.0)
    _answered(s, 1, None, LONG, 40.0)
    n = Engine(mini_bank, FakeLLM([LLMError("down")])).next(s, now=45.0)
    assert n.question_id == "S2-a" and n.fallback_used is True and "down" in n.log["error"]


def test_valid_probe_quotes_answer_and_spends_budget(mini_bank):
    llm = FakeLLM([{"action": "probe", "probe_text": 'You said "nobody asked me to".', "surfaced_tags": [], "reason": "r"}])
    s = make_session(now=0.0)
    _answered(s, 1, None, LONG, 40.0)
    n = Engine(mini_bank, llm).next(s, now=45.0)
    assert n.kind == "probe" and n.slot == 1 and n.question_id is None and s.probes_used == 1
    assert n.text == 'You said "nobody asked me to".'


def test_probe_without_verbatim_quote_is_rejected(mini_bank):
    llm = FakeLLM([{"action": "probe", "probe_text": 'You said "nobody ever asked".', "surfaced_tags": [], "reason": "r"}])
    s = make_session(now=0.0)
    _answered(s, 1, None, LONG, 40.0)
    n = Engine(mini_bank, llm).next(s, now=45.0)
    assert n.kind == "spine" and n.question_id == "S2-a" and n.fallback_used and s.probes_used == 0


def test_probe_not_offered_when_answer_short_or_window_closed(mini_bank):
    llm = FakeLLM([{"action": "probe", "probe_text": 'You said "a b c".', "surfaced_tags": [], "reason": "r"}] * 2)
    s = make_session(now=0.0)
    _answered(s, 1, None, "a b c d e f", 40.0)
    n = Engine(mini_bank, llm).next(s, now=45.0)
    assert n.kind == "spine" and "Probe allowed: no" in llm.calls[0]["user"]
    s2 = make_session(now=0.0)
    _answered(s2, 1, None, LONG, PROBE_WINDOW_S + 1)
    n2 = Engine(mini_bank, llm).next(s2, now=PROBE_WINDOW_S + 2)
    assert n2.kind == "spine"


def test_fire_threat_monotonic_filters_offered(mini_bank):
    llm = FakeLLM([{"action": "pick", "candidate_id": "S3-b", "surfaced_tags": [], "reason": "r"}])
    s = make_session(now=0.0)
    _answered(s, 1, None, LONG, 30.0)
    _answered(s, 2, "S2-c", LONG, 60.0)                       # S2-c has threat 4
    Engine(mini_bank, llm).next(s, now=65.0)
    assert "S3-a" not in llm.calls[0]["user"] and "S3-b" in llm.calls[0]["user"]


def test_fire_guard_jumps_to_compass(mini_bank):
    llm = FakeLLM([{"action": "pick", "candidate_id": "S5-b", "surfaced_tags": [], "reason": "r"}])
    s = make_session(now=0.0)
    _answered(s, 1, None, LONG, 30.0)
    _answered(s, 2, "S2-a", LONG, FIRE_GUARD_S + 5)
    n = Engine(mini_bank, llm).next(s, now=FIRE_GUARD_S + 10)
    assert n.slot == 5 and n.question_id == "S5-b"


def test_hard_close_returns_close_without_llm(mini_bank):
    s = make_session(now=0.0)
    _answered(s, 1, None, LONG, HARD_CLOSE_S + 1)
    n = Engine(mini_bank, FakeLLM()).next(s, now=HARD_CLOSE_S + 2)
    assert n.kind == "close"


def test_close_validates_mirror_and_take_home(mini_bank):
    llm = FakeLLM([{"mirror": "nobody asked me to do any of it", "take_home": "Who would you have to disappoint to keep going?"}])
    s = make_session(now=0.0)
    _answered(s, 1, None, LONG, 40.0)
    out = Engine(mini_bank, llm).close(s)
    assert out.mirror == "nobody asked me to do any of it"
    assert llm.calls[0]["effort"] == "high" and llm.calls[0]["schema"] is CLOSE_SCHEMA


def test_close_fallback_uses_longest_fire_sentence(mini_bank):
    llm = FakeLLM([{"mirror": "this was never said", "take_home": "Why?"}])
    s = make_session(now=0.0)
    _answered(s, 1, None, "Short one. " + LONG + ".", 40.0)
    out = Engine(mini_bank, llm).close(s)
    assert out.mirror == LONG
    assert out.take_home == mini_bank.opener.fallback_take_home
