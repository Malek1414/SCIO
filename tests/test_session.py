from ember.session import Turn, Session, new_session_id
from tests.conftest import make_session


def test_session_id_format():
    assert new_session_id("S07", 1_757_600_000.0).startswith("S07_2025")


def test_slot_counting_ignores_probes_and_pending():
    s = make_session()
    assert s.current_slot() == 1
    s.turns.append(Turn(slot=1, kind="spine", question_id=None, question="Q1", asked_at=0, answer="a b c", answered_at=5))
    s.turns.append(Turn(slot=1, kind="probe", question_id=None, question="p", asked_at=6, answer="d e", answered_at=9))
    s.pending = Turn(slot=2, kind="spine", question_id="F1-a", question="Q2", asked_at=10)
    assert s.current_slot() == 2
    assert s.last_answer() == "d e"
    assert s.last_spine().question == "Q1"


def test_used_ids_fire_answers_and_tags():
    s = make_session()
    s.turns += [
        Turn(slot=1, kind="spine", question_id=None, question="Q1", asked_at=0, answer="one", answered_at=1),
        Turn(slot=2, kind="spine", question_id="F1-a", question="Q2", asked_at=2, answer="two", answered_at=3),
        Turn(slot=5, kind="spine", question_id="C1-a", question="Q5", asked_at=4, answer="five", answered_at=5),
        Turn(slot=3, kind="spine", question_id="F2-a", question="Q3", asked_at=6, answer="", answered_at=7, skipped=True),
    ]
    assert s.used_ids() == {"F1-a", "C1-a", "F2-a"}
    assert s.fire_answers() == ["one", "two"]
    s.add_tags(["money", "money", "family"])
    s.add_tags(["family"])
    assert s.surfaced_tags == ["money", "family"]


def test_round_trip_and_observer_view():
    s = make_session()
    s.turns.append(Turn(slot=1, kind="spine", question_id=None, question="Q1", asked_at=0, answer="x", answered_at=1))
    s.add_tags(["quit"])
    s.probes_used = 1
    d = s.to_dict()
    back = Session.from_dict(d)
    assert back == s
    view = s.transcript_for_observer()
    assert view == [{"slot": 1, "kind": "spine", "question": "Q1", "answer": "x", "asked_at": 0, "answered_at": 1, "skipped": False}]
    assert "surfaced_tags" not in view[0]
