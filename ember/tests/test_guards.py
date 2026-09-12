import ember.guards as guards
from ember.guards import filter_candidates, probe_allowed, PROBE_WINDOW_S


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


def test_no_guard_truncates_the_spine_by_time():
    """The clock may cap probes; it may never cut the interview short or move a slot on."""
    for gone in ("resolve_slot", "q7_allowed", "should_hard_close",
                 "FIRE_GUARD_S", "Q7_GATE_S", "HARD_CLOSE_S"):
        assert not hasattr(guards, gone), f"{gone} still exists — time can still skip a question"
