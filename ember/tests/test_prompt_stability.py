"""The English system prompts are the cache key for every recorded API fixture.

If one changes by even a newline, every recording orphans and its test silently
SKIPs — the suite still reports all-green while the API tests stop running.
That happened once (an empty {lang_note} inserted a blank line).

When you intend to change a prompt: update the hash here AND re-record with
EMBER_RECORD=1 in the same commit.
"""
import hashlib

from ember.bank import load_bank
from ember.engine import build_system_prompt
from ember.observer import build_observer_system


def _h(s: str) -> str:
    return hashlib.sha256(s.encode()).hexdigest()[:16]


def test_english_prompts_are_stable():
    bank = load_bank("en")
    assert _h(build_system_prompt(bank)) == "ebfad6fde5647409", "engine prompt changed — re-record the fixtures"
    assert _h(build_observer_system(bank.rubric, "en")) == "6151e6c33b87a9c7", "observer prompt changed — re-record the fixtures"


def test_german_prompts_differ_from_english():
    bank = load_bank("en")
    de = bank.model_copy(update={"language": "de"})
    assert _h(build_system_prompt(de)) != _h(build_system_prompt(bank))
    assert _h(build_observer_system(bank.rubric, "de")) != _h(build_observer_system(bank.rubric, "en"))
