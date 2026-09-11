from ember.guards import (filter_candidates, probe_allowed, resolve_slot, q7_allowed, should_hard_close,
                          PROBE_WINDOW_S, FIRE_GUARD_S, Q7_GATE_S, HARD_CLOSE_S)


def test_filter_prerequisites_and_threat(mini_bank):
    slot3 = mini_bank.for_slot(3)                       # S3-a t3, S3-b t4, S3-c t5 (needs family)
    assert [c.id for c in filter_candidates(slot3, set(), 0)] == ["S3-a", "S3-b"]
    assert [c.id for c in filter_candidates(slot3, {"family"}, 0)] == ["S3-a", "S3-b", "S3-c"]
    assert [c.id for c in filter_candidates(slot3, {"family"}, 4)] == ["S3-b", "S3-c"]
    assert filter_candidates(slot3, set(), 9) == []


def test_probe_gate():
    assert probe_allowed(10, 0, 15)
    assert not probe_allowed(10, 0, 14)
    assert not probe_allowed(10, 2, 40)
    assert probe_allowed(PROBE_WINDOW_S - 1, 1, 40)
    assert not probe_allowed(PROBE_WINDOW_S, 1, 40)


def test_fire_guard_jumps_to_compass():
    assert resolve_slot(3, FIRE_GUARD_S) == 3
    assert resolve_slot(3, FIRE_GUARD_S + 1) == 5
    assert resolve_slot(4, FIRE_GUARD_S + 1) == 5
    assert resolve_slot(6, FIRE_GUARD_S + 1) == 6
    assert resolve_slot(7, 0) == 7


def test_q7_and_hard_close():
    assert q7_allowed(Q7_GATE_S - 1) and not q7_allowed(Q7_GATE_S)
    assert not should_hard_close(HARD_CLOSE_S - 1) and should_hard_close(HARD_CLOSE_S)
