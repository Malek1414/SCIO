import json
from pathlib import Path
import pytest

from ember.bank import load_bank
from ember.observer import (OBSERVER_SCHEMA, ObserverResult, coverage, validate)

A1 = "They just work a lot more than everyone else and they never wait to feel ready before they start something"
A2 = "I would be in the workshop with the door locked building the synth nobody asked for and no one could reach me"
A3 = "I gave up the graduate scheme and my parents thought I was insane but I have stopped trying to explain it"
ALL = ("F1", "F2", "F3", "C1", "C2", "C3", "G1", "G2", "G3")


@pytest.fixture(scope="module")
def bank():
    return load_bank()


def transcript(bank, answers=(A1, A2, A3), *, skip=(), questions=None):
    qs = questions or [bank.opener.text, bank.by_id("F1-a").text, bank.by_id("F2-a").text]
    turns = [{"slot": i + 1, "kind": "spine", "question": q, "answer": "" if i in skip else a,
              "asked_at": 10.0 * i, "answered_at": 10.0 * i + 8, "skipped": i in skip}
             for i, (q, a) in enumerate(zip(qs, answers))]
    return {"session_id": "S01_x", "subject_code": "S01", "started_at": 0.0, "closed": True,
            "mirror": None, "take_home": None, "turns": turns}


def raw(**over):
    base = {c: {"score": 4, "evidence": [], "note": "n"} for c in ALL}
    base.update(over)
    return {"constructs": base, "declined": [], "flags": []}


def _validate(bank, r, tr):
    return validate(r, tr, bank, subject_id="S01", session_id="S01_x", scored_at="t", rubric_version="1.0.0")


def test_schema_requires_all_nine_constructs():
    assert set(OBSERVER_SCHEMA["properties"]["constructs"]["required"]) == set(ALL)
    assert OBSERVER_SCHEMA["properties"]["constructs"]["properties"]["F1"]["properties"]["score"]["maximum"] == 7


def test_coverage_from_question_text_including_rephrase(bank):
    cov = coverage(transcript(bank), bank)
    assert cov == {"F1": True, "F2": True, "F3": True, "C1": False, "C2": False, "C3": False, "G1": False, "G2": False, "G3": False}
    assert coverage(transcript(bank, skip=(2,)), bank)["F2"] is False
    rephrased = transcript(bank, questions=[bank.opener.rephrase, bank.by_id("F1-a").rephrase, bank.by_id("F2-a").rephrase])
    assert coverage(rephrased, bank)["F2"] is True
    probe_only = transcript(bank)
    probe_only["turns"][2]["kind"] = "probe"
    assert coverage(probe_only, bank)["F2"] is False


def test_validate_keeps_only_verbatim_evidence_and_computes_signal(bank):
    r = raw(F1={"score": 6, "evidence": ["never wait to feel ready", "made-up quote here", "work a lot more"], "note": "x"},
            F2={"score": 5, "evidence": ["gave up the graduate scheme", "door locked building", "stopped trying to explain"], "note": "y"})
    out = _validate(bank, r, transcript(bank))
    assert out.constructs["F1"].evidence == ["never wait to feel ready", "work a lot more"]
    assert out.constructs["F1"].signal == "med"                     # 2 quotes, one answer
    assert out.constructs["F2"].signal == "high"                    # 3 quotes across 2 answers
    assert any("F1: 1 evidence quote(s) not verbatim" in f for f in out.flags)
    assert out.constructs["F3"].signal == "low"                     # covered by the opener, but no evidence
    assert "C1" in out.declined and out.constructs["C1"].signal == "low"


def test_validate_declined_bad_score_and_clamp(bank):
    r = raw(F2={"score": 5, "evidence": ["gave up the graduate scheme", "stopped trying to explain", "door locked building"], "note": ""},
            C2={"score": "x", "evidence": [], "note": ""},
            G1={"score": 9, "evidence": [], "note": ""})
    r["declined"] = ["F2", "ZZ"]
    r["flags"] = ["subject paused 30 s before F2"]
    out = _validate(bank, r, transcript(bank))
    assert out.constructs["F2"].signal == "low" and "F2" in out.declined
    assert out.constructs["C2"].score == 1 and any("C2: model returned no valid score" in f for f in out.flags)
    assert out.constructs["G1"].score == 7
    assert "ZZ" not in out.declined and out.flags[0] == "subject paused 30 s before F2"
    assert isinstance(out, ObserverResult) and out.rubric_version == "1.0.0"


from ember.observer import score, observe_session, load_results, build_observer_system, build_observer_user
from tests.conftest import FakeLLM


def test_score_calls_llm_with_rubric_high_effort_and_stamps_version(bank):
    llm = FakeLLM([raw(F1={"score": 6, "evidence": ["never wait to feel ready"], "note": "n"})])
    out = score(transcript(bank), bank, llm, now=1_757_600_000.0)
    call = llm.calls[0]
    assert call["effort"] == "high" and call["schema"] is OBSERVER_SCHEMA
    assert "F3 — Mediocrity tolerance (inverse" in call["system"] and "watching someone fall asleep" in call["system"]
    assert A2 in call["user"] and "[2] spine slot 2" in call["user"]
    assert out.rubric_version == "1.0.0" and out.scored_at.startswith("2025-09-11")
    assert out.constructs["F1"].score == 6 and out.constructs["F1"].signal == "low"      # one quote → low


def test_observe_session_reads_only_transcript_and_overwrites(tmp_path: Path, bank):
    d = tmp_path / "S01_x"
    d.mkdir()
    (d / "transcript.json").write_text(json.dumps(transcript(bank)))
    (d / "engine_log.json").write_text('[{"secret": "engine reasoning must never be read"}]')
    p = observe_session(d, bank, FakeLLM([raw(G1={"score": 2, "evidence": [], "note": ""})]))
    first = json.loads(p.read_text())
    assert p.name == "observer.json" and first["constructs"]["G1"]["score"] == 2 and first["subject_id"] == "S01"
    observe_session(d, bank, FakeLLM([raw(G1={"score": 5, "evidence": [], "note": ""})]))
    assert json.loads(p.read_text())["constructs"]["G1"]["score"] == 5
    assert load_results(tmp_path) == {"S01_x": json.loads(p.read_text())}


def test_import_wall():
    src = (Path(__file__).parent.parent / "ember" / "observer.py").read_text()
    for forbidden in ("from .engine", "from .guards", "from .session", "from .server", "from .llm", "import ember.engine"):
        assert forbidden not in src, forbidden
