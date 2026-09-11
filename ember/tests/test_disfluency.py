from ember.disfluency import clean_disfluencies


def test_strips_fillers_and_immediate_repeats_english():
    raw = "uh a person who's alone I guess. I don't I don't I'm not afraid of being lonely, um, really."
    assert clean_disfluencies(raw) == "a person who's alone I guess. I don't I'm not afraid of being lonely, really."


def test_strips_german_fillers():
    assert clean_disfluencies("ähm ich weiß äh nicht so genau", "de") == "ich weiß nicht so genau"
    assert clean_disfluencies("ich ich habe das gemacht", "de") == "ich habe das gemacht"


def test_leaves_clean_text_alone():
    clean = "I rebuilt the whole backend three times because the first two felt wrong"
    assert clean_disfluencies(clean) == clean
    assert clean_disfluencies("") == ""


def test_does_not_eat_meaningful_repetition_across_a_boundary():
    assert clean_disfluencies("That is that is what I said") == "That is what I said"     # immediate repeat, collapsed
    assert clean_disfluencies("I had had enough") == "I had enough"                       # documented limitation
