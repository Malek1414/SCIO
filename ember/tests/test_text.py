from ember.text import normalize, word_count, contains_verbatim, extract_quote, longest_sentence

ANSWER = "Honestly, I couldn't stop. I rebuilt the whole backend three times — nobody asked me to."


def test_normalize_strips_punctuation_and_case():
    assert normalize("I couldn't STOP.") == ["i", "couldn't", "stop"]


def test_word_count():
    assert word_count(ANSWER) == 15


def test_contains_verbatim_hit_and_bounds():
    assert contains_verbatim(ANSWER, "I couldn't stop", min_words=3, max_words=6)
    assert contains_verbatim(ANSWER, "rebuilt the whole backend three times", min_words=3, max_words=6)
    assert not contains_verbatim(ANSWER, "couldn't stop", min_words=3, max_words=6)        # too short
    assert not contains_verbatim(ANSWER, "I rebuilt the whole backend three times", min_words=3, max_words=6)  # 7 words
    assert not contains_verbatim(ANSWER, "I could not stop", min_words=3, max_words=6)     # not verbatim
    assert contains_verbatim(ANSWER, "nobody asked me to", min_words=3)                   # no max


def test_extract_quote_double_and_curly():
    assert extract_quote('You said "I couldn\'t stop."') == "I couldn't stop."
    assert extract_quote("You said “nobody asked me to”.") == "nobody asked me to"
    assert extract_quote("You said it plainly.") is None


def test_longest_sentence():
    assert longest_sentence(ANSWER) == "I rebuilt the whole backend three times — nobody asked me to"
    assert longest_sentence("") == ""


GERMAN = "Ich hätte es schön gefunden, aber mein Größenwahn stand im Weg."


def test_umlauts_and_eszett_count_as_one_word_each():
    assert normalize("Ich möchte größer träumen") == ["ich", "möchte", "größer", "träumen"]
    assert word_count("Ich möchte größer träumen") == 4
    assert word_count("hätte es schön") == 3
    assert word_count("Straße") == 1


def test_verbatim_bounds_hold_for_german():
    assert contains_verbatim(GERMAN, "hätte es schön", min_words=3, max_words=6)
    assert not contains_verbatim(GERMAN, "es schön", min_words=3, max_words=6)          # 2 words, too short
    assert contains_verbatim(GERMAN, "mein Größenwahn stand im Weg", min_words=3, max_words=6)
    assert not contains_verbatim(GERMAN, "hatte es schon", min_words=3, max_words=6)    # umlauts are not optional


def test_longest_sentence_picks_by_real_word_count():
    text = "Ich weiß nicht. Mein Größenwahn stand mir wirklich im Weg."
    assert longest_sentence(text) == "Mein Größenwahn stand mir wirklich im Weg"
