from ember.bank import LANGUAGES
from ember.copy import COPY, copy_for

KEYS = {"consent_title", "consent_1", "consent_2", "consent_3", "code_label", "start",
        "hint_idle", "hint_recording", "hint_waiting", "retry", "closing"}


def test_every_language_has_every_key():
    assert set(COPY) == set(LANGUAGES)
    for lang, strings in COPY.items():
        assert set(strings) == KEYS, f"{lang} key mismatch: {set(strings) ^ KEYS}"
        assert all(v.strip() for v in strings.values()), f"{lang} has an empty string"


def test_german_copy_uses_du_not_sie():
    de = " ".join(COPY["de"].values())
    assert " Sie " not in de and " Ihre " not in de and " Ihnen " not in de
    assert "du" in de.lower()


def test_copy_for_falls_back_to_english():
    assert copy_for("de")["start"] == COPY["de"]["start"]
    assert copy_for("fr") == COPY["en"]
