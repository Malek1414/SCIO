from ember.bank import load_bank


def test_german_bank_mirrors_the_english_structure():
    en, de = load_bank("en"), load_bank("de")
    assert de.language == "de" and len(de.candidates) == len(en.candidates) == 21
    by_id_en = {c.id: c for c in en.candidates}
    for c in de.candidates:
        e = by_id_en[c.id]
        assert (c.slot, c.cluster, tuple(c.targets), c.threat, tuple(c.prerequisites), c.default, c.framing) == \
               (e.slot, e.cluster, tuple(e.targets), e.threat, tuple(e.prerequisites), e.default, e.framing), c.id
    assert set(de.rubric) == set(en.rubric)           # shared English rubric


def test_german_bank_is_du_and_open():
    de = load_bank("de")
    everything = " ".join([de.opener.text, de.opener.rephrase, de.opener.fallback_take_home] +
                          [c.text for c in de.candidates] + [c.rephrase for c in de.candidates])
    for formal in (" Sie ", " Ihre ", " Ihnen ", " Ihr "):
        assert formal not in everything, f"formal register found: {formal!r}"
    assert de.opener.fallback_take_home.strip().endswith("?")


def test_fire_threat_monotonicity_is_satisfiable_in_german():
    de = load_bank("de")
    for s in (2, 3):
        for c in de.for_slot(s):
            assert any(n.threat >= c.threat for n in de.for_slot(s + 1)), f"{c.id} strands slot {s + 1}"
