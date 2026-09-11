import pytest

from ember.bank import load_bank
from ember.constructs import CONSTRUCTS
from ember.llm import LLM, guard_environment
from ember.observer import score
from ember.text import contains_verbatim
from tests.recording import RecordingLLM

pytestmark = pytest.mark.api

# A synthetic subject. Question ids follow the default path through the bank.
ANSWERS = [
    (None, "My flatmate Karim. Everyone in our year talks about starting something and he just starts. He got rejected "
           "from the accelerator twice and both times had a new version the next week. He doesn't wait to feel ready. "
           "I keep waiting to feel ready and he treats it like a Tuesday."),
    ("F1-a", "If money was handled I'd be in the workshop. There's a half-finished synth on my desk I haven't touched in "
             "two months because of the internship. Two in the afternoon I'd have the soldering iron out and nobody "
             "would be able to reach me. Not travelling, not resting. Building the thing nobody asked for."),
    ("F2-a", "I gave up the graduate scheme. Everyone thought I was insane, my parents especially. Safe money and a title "
             "and I walked away to keep working on this. I don't regret it but I can't fully explain it to them and "
             "I've stopped trying. That's the real cost. Not the money. The explaining."),
    ("F2-c", "I'd have to become someone who doesn't pick up the phone. I already see it a bit. My sister called three "
             "times last month and I let it ring because I was in the middle of something. If it works I think that "
             "becomes normal and I'm not sure I want normal to look like that."),
    ("C3-a", "The guy at the reunion who is still talking about the thing he was going to build. Ten years on, same "
             "story, better excuses. I can picture him exactly. Sometimes I catch myself using his sentences."),
    ("G1-a", "Forty minutes in I've stopped pretending to read. That's when the synth shows up in my head, and the calls "
             "I didn't return, in that order. I'd probably start sketching something just to not sit with the second one."),
    ("G3-a", "When I'm at my best they're doing their own thing and they know I'll surface. My sister sends photos and "
             "doesn't expect a reply until Sunday. That's the version I want. The version I've got is them waiting."),
]


def full_transcript(bank):
    turns = []
    for i, (qid, a) in enumerate(ANSWERS):
        q = bank.opener.text if qid is None else bank.by_id(qid).text
        turns.append({"slot": i + 1, "kind": "spine", "question": q, "answer": a,
                      "asked_at": 45.0 * i, "answered_at": 45.0 * i + 40, "skipped": False})
    return {"session_id": "SYN_2026-09-11T00-00-00", "subject_code": "SYN", "started_at": 0.0, "closed": True,
            "mirror": "I'm not sure I want normal to look like that", "take_home": "Who is waiting?", "turns": turns}


@pytest.fixture(scope="module")
def llm():
    guard_environment()
    return RecordingLLM(inner=LLM())


def test_observer_scores_full_session(llm):
    bank = load_bank()
    tr = full_transcript(bank)
    out = score(tr, bank, llm, now=0.0)
    text = "\n".join(t["answer"] for t in tr["turns"])
    assert set(out.constructs) == set(CONSTRUCTS)
    assert all(1 <= c.score <= 7 for c in out.constructs.values())
    assert all(contains_verbatim(text, q, min_words=3) for c in out.constructs.values() for q in c.evidence)
    assert {"C1", "C2", "G2"} <= set(out.declined)                 # never asked → declined, low
    assert all(out.constructs[c].signal == "low" for c in ("C1", "C2", "G2"))
    assert sum(c.signal != "low" for c in out.constructs.values()) >= 3   # the six covered constructs should mostly have evidence
    assert all(out.constructs[c].note for c in ("F1", "F2", "F3", "C3", "G1", "G3"))   # covered constructs carry a note
