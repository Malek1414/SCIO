from ember.bank import load_bank


def test_real_bank_loads_and_has_expected_shape():
    bank = load_bank()
    assert len(bank.candidates) == 21
    assert {c.slot for c in bank.candidates} == {2, 3, 4, 5, 6}
    fire_ids = {c.id for c in bank.candidates if c.cluster == "fire"}
    assert len(fire_ids) == 11
    assert all(c.prerequisites == [] for c in bank.for_slot(2))


def test_fire_threat_monotonicity_is_satisfiable():
    """For any Fire pick at slot s, slot s+1 must still offer at least one candidate with threat >= it."""
    bank = load_bank()
    for s in (2, 3):
        for c in bank.for_slot(s):
            assert any(n.threat >= c.threat for n in bank.for_slot(s + 1)), f"{c.id} strands slot {s + 1}"
