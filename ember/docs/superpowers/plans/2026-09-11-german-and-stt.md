# ember v2 — German Support & Pluggable STT Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Run a complete ember session in German — German bank, German UI, German STT, German probes and close — selected before the session starts, with the STT model per language a measured config value rather than a hard-coded string.

**Architecture:** Six bug fixes first (five of them block German outright), then the seams: `bank/<lang>/` with `load_bank(lang)`, a `Transcriber` protocol with whisper and Parakeet implementations behind `STT_CONFIG`, a `COPY` dict served to the page, and `language` threaded through session → store → observer → graph. The German bank is authored last, before the toggle, so it hits a human review gate with everything else already green.

**Tech Stack:** Python 3.12 (`uv`), `mlx-whisper` 0.4.3, `parakeet-mlx` ≥ 0.5.2 (new), `claude-agent-sdk`, FastAPI, pydantic v2, PyYAML, pytest.

**Spec:** `docs/superpowers/specs/2026-09-11-german-and-stt-design.md`. v1 is merged on `main` (PRs #1, #2). Branch `ember/v2-german-stt` already exists with the spec committed.

## Global Constraints

Copied from the spec. Every task's requirements include these.

- **Repo:** git root `~/Desktop/SCIO`, project `~/Desktop/SCIO/ember`; all commands run from the project dir. Branch: `ember/v2-german-stt` (exists).
- **Python 3.12 via `uv`.** All commands `uv run …`.
- **Languages:** exactly `"en"` and `"de"`. `"en"` is the default everywhere a language is optional, so every existing call site keeps working unchanged.
- **Register:** the German bank and all German copy address the subject as **du**, never Sie.
- **Transcripts are clean** — no disfluencies. Whisper is the default backend for both languages; Parakeet is implemented but never a default.
- **`STT_CONFIG`** ships as `{"en": ("whisper", "mlx-community/whisper-large-v3-turbo"), "de": ("whisper", "mlx-community/whisper-large-v3-turbo")}`. German is provisional pending real German speech.
- **The rubric stays English and shared** at `ember/bank/rubric.yaml`, outside the per-language dirs. Scores, notes and flags are English in both languages.
- **Language is fixed at session start.** It selects bank, transcriber and copy. No mid-session switching.
- **The German bank is crafted, not translated**, and carries the same ids, slots, `targets`, `prerequisites` and threat ladder as the English one.
- **Out of scope here:** cleanup findings B7–B12 (duplicated UTC timestamp, observer/engine transcript rendering, test fixture duplication, hard-coded `120.0`). A separate pass.
- **Commits:** every commit message ends with the two trailer lines shown in Task 1 Step 5. Use them verbatim.

---

## File Structure

```
ember/
  ember/
    text.py            B1: Unicode tokeniser (no new helpers — disfluencies are stripped, so word_count stays the one counter)
    bank.py            B2: per-language yes/no prefixes; load_bank(lang) reads bank/<lang>/
    bank/
      en/{opener,questions}.yaml     moved from bank/*.yaml, content unchanged
      de/{opener,questions}.yaml     new, authored in Task 7
      rubric.yaml                    stays put, shared, English
    stt.py             Transcriber protocol, WhisperTranscriber, ParakeetTranscriber, STT_CONFIG, for_language()
    disfluency.py      clean_disfluencies() — used only by ParakeetTranscriber
    copy.py            COPY dict, both languages, every UI string
    session.py         B4: Session.language
    store.py           B4: language in meta.json / transcript.json; create(..., language=)
    observer.py        B6 one-liner; language line in the system prompt
    engine.py          language line in the system prompt
    export.py          language into graph/data.js
    server.py          B5: copy endpoint; language on POST /api/session; per-language transcribers
    static/subject.html  top bar with EN | DE, copy rendered from the API
    static/operator.html shows the session language
    cli.py             serve builds a transcriber per language; new `stt-eval`
    stt_eval.py        wer(), evaluate() — the measurement command's engine
  calibration/stt_clips.yaml   reference clips for stt-eval
  tests/               one new test module per task, plus edits to existing ones
```

Dependency direction unchanged: `text ← bank`, `stt ← server`, `copy ← server`. `disfluency` and `stt_eval` are leaves. `observer.py` still imports nothing from the engine side — the import wall test in `tests/test_observer.py` stays green.

---

### Task 1: B1 — Unicode tokeniser

**Files:**
- Modify: `ember/text.py:4`
- Modify: `tests/test_text.py` (append)

**Interfaces:**
- Produces: `normalize`, `word_count`, `contains_verbatim`, `longest_sentence` unchanged in signature, correct for non-ASCII letters.

- [x] **Step 1: Write the failing test**

Append to `tests/test_text.py`:
```python


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
```

- [x] **Step 2: Run to verify it fails**

Run: `cd ~/Desktop/SCIO/ember && uv run pytest tests/test_text.py -v`
Expected: `test_umlauts_and_eszett_count_as_one_word_each` FAILS — `normalize` returns `['ich', 'm', 'chte', 'gr', 'er', 'tr', 'umen']`.

- [x] **Step 3: Fix the regex**

In `ember/text.py`, replace line 4:
```python
_WORD = re.compile(r"[a-z0-9']+")
```
with:
```python
_WORD = re.compile(r"[\w']+", re.UNICODE)      # \w covers umlauts, ß, accents — ASCII-only silently split them
```

- [x] **Step 4: Run the whole text suite and the engine suite**

Run: `uv run pytest tests/test_text.py tests/test_engine.py -v`
Expected: all pass. (`normalize` lowercases first, so `\w` never sees uppercase; the English assertions are unaffected because `\w` also matches `[a-z0-9]` plus `_`.)

- [x] **Step 5: Commit**

```bash
git add ember/text.py tests/test_text.py
git commit -m "fix: Unicode-correct word tokeniser (B1 — umlauts split words, corrupting every word bound)" \
  -m "Co-Authored-By: WOZCODE <contact@withwoz.com>" \
  -m "Claude-Session: https://claude.ai/code/session_011xY91ug8K4Ke8JHFsa5ekB"
```

---

### Task 2: B6 — declined and signal cannot desync

**Files:**
- Modify: `ember/observer.py:139`
- Modify: `tests/test_observer.py` (append)

**Interfaces:**
- Consumes: `validate` from `ember.observer`, unchanged signature.
- Produces: the §6 invariant — every id in `declined` carries `signal == "low"` — enforced by construction.

- [x] **Step 1: Write the failing test**

Append to `tests/test_observer.py`:
```python


def test_every_declined_construct_has_low_signal(bank):
    """Spec §6 invariant. The two must never be derived separately."""
    r = raw(F1={"score": 6, "evidence": ["never wait to feel ready", "work a lot more", "they just work"], "note": "x"})
    r["declined"] = ["F1"]                    # model declines a construct that HAS three verbatim quotes
    out = _validate(bank, r, transcript(bank))
    assert "F1" in out.declined
    assert out.constructs["F1"].signal == "low"
    assert all(out.constructs[c].signal == "low" for c in out.declined)
```

- [x] **Step 2: Run to verify it passes today but for the wrong reason, then make the coupling explicit**

Run: `uv run pytest tests/test_observer.py -v`
Expected: PASSES — today's expression happens to agree. The test pins the invariant so the refactor in Step 3 is safe and any future third decline-reason keeps it.

- [x] **Step 3: Derive `skipped` from `declined`**

In `ember/observer.py`, replace:
```python
        skipped = (not cov[cid]) or (cid in declined_raw)
```
with:
```python
        skipped = cid in declined          # one source of truth: §6 says declined ⇒ low signal
```

- [x] **Step 4: Run to verify it still passes**

Run: `uv run pytest tests/test_observer.py -v`
Expected: all pass, including the four original validate tests.

- [x] **Step 5: Commit**

```bash
git add ember/observer.py tests/test_observer.py
git commit -m "fix: derive skipped from declined so signal cannot desync (B6)" \
  -m "Co-Authored-By: WOZCODE <contact@withwoz.com>" \
  -m "Claude-Session: https://claude.ai/code/session_011xY91ug8K4Ke8JHFsa5ekB"
```

---

### Task 3: B2 + per-language banks on disk

**Files:**
- Modify: `ember/bank.py` (YES_NO_STARTS → per-language; `load_bank(lang)`; `Bank.language`)
- Move: `ember/bank/{opener,questions}.yaml` → `ember/bank/en/`
- Modify: `tests/conftest.py` (`write_mini_bank` writes the new layout), `tests/test_bank.py`, `tests/test_real_bank.py`

**Interfaces:**
- Produces: `LANGUAGES = ("en", "de")`; `YES_NO_STARTS: dict[str, tuple[str, ...]]`; `Bank.language: str`; `load_bank(lang: str = "en", root: Path = BANK_DIR) -> Bank` reading `root/<lang>/opener.yaml`, `root/<lang>/questions.yaml` and the shared `root/rubric.yaml`. Every existing no-arg `load_bank()` call keeps working.

- [x] **Step 1: Write the failing tests**

Append to `tests/test_bank.py`:
```python


import pytest as _pytest
from ember.bank import LANGUAGES, YES_NO_STARTS


def test_languages_and_prefix_tables():
    assert LANGUAGES == ("en", "de")
    assert set(YES_NO_STARTS) == {"en", "de"}
    assert "do " in YES_NO_STARTS["en"] and "hast du " in YES_NO_STARTS["de"]


def test_german_yes_no_questions_are_rejected():
    base = dict(id="X", slot=3, cluster="fire", targets=["F2"], threat=5, framing="cost-already-paid",
                prerequisites=[], default=False, language="de")
    with _pytest.raises(ValidationError, match="yes/no"):
        Candidate(**base, text="Hast du jemals etwas aufgegeben?", rephrase="Was hast du aufgegeben?")
    with _pytest.raises(ValidationError, match="yes/no"):
        Candidate(**base, text="Würdest du das nochmal machen?", rephrase="Was würdest du nochmal machen?")
    ok = Candidate(**base, text="Was hast du dafür schon aufgegeben?", rephrase="Was hat es dich gekostet?")
    assert ok.language == "de"


def test_english_candidate_unaffected_by_german_prefixes():
    c = Candidate(id="Y", slot=3, cluster="fire", targets=["F2"], threat=5, framing="cost-already-paid",
                  prerequisites=[], default=False, text="What did it cost you?", rephrase="What was the cost?")
    assert c.language == "en"
```

Append to `tests/test_real_bank.py`:
```python


def test_english_bank_loads_from_the_language_dir():
    bank = load_bank("en")
    assert bank.language == "en" and len(bank.candidates) == 21
    assert load_bank().candidates[0].id == bank.candidates[0].id       # default arg is still English
    assert set(bank.rubric) == {"F1", "F2", "F3", "C1", "C2", "C3", "G1", "G2", "G3"}
```

- [x] **Step 2: Run to verify failure**

Run: `uv run pytest tests/test_bank.py tests/test_real_bank.py -v`
Expected: `ImportError: cannot import name 'LANGUAGES' from 'ember.bank'`.

- [x] **Step 3: Move the English bank files**

```bash
cd ~/Desktop/SCIO/ember
mkdir -p ember/bank/en
git mv ember/bank/opener.yaml ember/bank/en/opener.yaml
git mv ember/bank/questions.yaml ember/bank/en/questions.yaml
# rubric.yaml stays at ember/bank/rubric.yaml — shared, English, operator-facing
ls ember/bank ember/bank/en
```

- [x] **Step 4: Make the language a first-class field**

In `ember/bank.py`, replace the module-level constant block:
```python
YES_NO_STARTS = ("do ", "does ", "did ", "are ", "is ", "was ", "were ", "have ", "has ", "had ",
                 "can ", "could ", "will ", "would ", "should ")


def _open_question(text: str) -> str:
    if text.strip().lower().startswith(YES_NO_STARTS):
        raise ValueError(f"yes/no question not allowed: {text[:50]!r}")
    return text
```
with:
```python
LANGUAGES = ("en", "de")

YES_NO_STARTS: dict[str, tuple[str, ...]] = {
    "en": ("do ", "does ", "did ", "are ", "is ", "was ", "were ", "have ", "has ", "had ",
           "can ", "could ", "will ", "would ", "should "),
    # German inverts verb and subject to form a yes/no question, so the verb leads.
    "de": ("hast ", "hat ", "hattest ", "hattet ", "bist ", "ist ", "war ", "warst ", "warst du ",
           "kannst ", "kann ", "könntest ", "willst ", "wirst ", "würdest ", "möchtest ",
           "hältst ", "glaubst ", "denkst ", "fühlst ", "gibt es ", "bereust ", "machst ", "gehst "),
}


def _open_question(text: str, language: str = "en") -> str:
    if text.strip().lower().startswith(YES_NO_STARTS[language]):
        raise ValueError(f"yes/no question not allowed in {language}: {text[:50]!r}")
    return text
```

Add `language` to `Candidate` (after `default`) and to `Opener`, and route the validators through it. In `class Candidate`:
```python
    default: bool = False
    language: str = "en"
    text: str
    rephrase: str
```
Replace `Candidate`'s text validator:
```python
    @field_validator("text", "rephrase")
    @classmethod
    def _open(cls, v: str) -> str:
        return _open_question(v)
```
with a model-level check (a field validator cannot see sibling fields):
```python
    @field_validator("language")
    @classmethod
    def _lang_known(cls, v: str) -> str:
        if v not in LANGUAGES:
            raise ValueError(f"unknown language {v!r}")
        return v
```
and add these two lines at the top of the existing `_consistency` model validator, before the target-cluster loop:
```python
    @model_validator(mode="after")
    def _consistency(self) -> "Candidate":
        _open_question(self.text, self.language)
        _open_question(self.rephrase, self.language)
        for t in self.targets:
```

Do the same for `Opener` — add `language: str = "en"` as its first field, delete its `@field_validator("text", "rephrase")` `_open` method, and add:
```python
    @model_validator(mode="after")
    def _open_questions(self) -> "Opener":
        _open_question(self.text, self.language)
        _open_question(self.rephrase, self.language)
        return self
```

Add `language: str = "en"` to `class Bank` (first field), and replace `load_bank`:
```python
def load_bank(lang: str = "en", root: Path = BANK_DIR) -> Bank:
    if lang not in LANGUAGES:
        raise ValueError(f"unknown language {lang!r}")
    d = root / lang
    opener = yaml.safe_load((d / "opener.yaml").read_text(encoding="utf-8"))
    qs = yaml.safe_load((d / "questions.yaml").read_text(encoding="utf-8"))
    rub = yaml.safe_load((root / "rubric.yaml").read_text(encoding="utf-8"))   # shared, English
    return Bank(language=lang,
                opener={**opener, "language": lang},
                candidates=[{**c, "language": lang} for c in qs["candidates"]],
                rubric={r["construct"]: r for r in rub["rubric"]})
```

- [x] **Step 5: Update the test fixture to the new layout**

In `tests/conftest.py`, `write_mini_bank(d)` currently writes three files into `d`. Change its last three lines from:
```python
    (d / "opener.yaml").write_text(yaml.safe_dump(opener, sort_keys=False))
    (d / "questions.yaml").write_text(yaml.safe_dump({"candidates": cands}, sort_keys=False))
    (d / "rubric.yaml").write_text(yaml.safe_dump({"rubric": rubric}, sort_keys=False))
```
to:
```python
    (d / "en").mkdir(parents=True, exist_ok=True)
    (d / "en" / "opener.yaml").write_text(yaml.safe_dump(opener, sort_keys=False))
    (d / "en" / "questions.yaml").write_text(yaml.safe_dump({"candidates": cands}, sort_keys=False))
    (d / "rubric.yaml").write_text(yaml.safe_dump({"rubric": rubric}, sort_keys=False))
```
and change the `mini_bank` fixture's body from `return load_bank(mini_bank_dir)` to `return load_bank("en", mini_bank_dir)`.

In `tests/test_bank.py`, the two structural tests call `load_bank(tmp_path)` and edit `tmp_path / "questions.yaml"`. Update both: the edited file is now `tmp_path / "en" / "questions.yaml"`, and the call is `load_bank("en", tmp_path)`.

- [x] **Step 6: Run the full suite**

Run: `uv run pytest -q`
Expected: all pass. If `test_real_bank.py` fails on a missing file, the `git mv` in Step 3 did not run.

- [x] **Step 7: Commit**

```bash
git add ember/bank.py ember/bank/ tests/conftest.py tests/test_bank.py tests/test_real_bank.py
git commit -m "feat: per-language banks and yes/no prefixes (B2); move English bank to bank/en/" \
  -m "Co-Authored-By: WOZCODE <contact@withwoz.com>" \
  -m "Claude-Session: https://claude.ai/code/session_011xY91ug8K4Ke8JHFsa5ekB"
```

---

### Task 4: B3 — pluggable STT

**Files:**
- Create: `ember/disfluency.py`, `tests/test_disfluency.py`
- Modify: `ember/stt.py`, `tests/test_stt.py`
- Modify: `pyproject.toml` (add `parakeet-mlx>=0.5.2`)

**Interfaces:**
- Produces: `clean_disfluencies(text: str, language: str = "en") -> str`; `Transcriber` Protocol with `language: str`, `warm() -> float`, `transcribe(wav_path: Path, prime: str | None = None) -> str`; `WhisperTranscriber(language: str = "en", repo: str = …)`; `ParakeetTranscriber(language: str = "en", repo: str = "mlx-community/parakeet-tdt-0.6b-v3")`; `STT_CONFIG: dict[str, tuple[str, str]]`; `for_language(lang: str) -> Transcriber`; `MODEL_REPO` kept as the English whisper repo for back-compat.
- Consumes: nothing from earlier tasks.

- [x] **Step 1: Write the failing disfluency test**

`tests/test_disfluency.py`:
```python
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
```

- [x] **Step 2: Run to verify failure**

Run: `uv run pytest tests/test_disfluency.py -v`
Expected: `ModuleNotFoundError: No module named 'ember.disfluency'`.

- [x] **Step 3: Implement the cleaner**

`ember/disfluency.py`:
```python
"""Filler and stutter removal. Used only by ParakeetTranscriber — whisper strips these natively
and contextually, which is why whisper is the default backend (spec §3.2)."""
import re

FILLERS: dict[str, frozenset[str]] = {
    "en": frozenset({"uh", "um", "erm", "eh", "hm", "hmm", "mhm", "uhh", "umm"}),
    "de": frozenset({"äh", "ähm", "ehm", "hm", "hmm", "öh", "ähh", "mhm"}),
}

_TOKEN = re.compile(r"\s+")
_MAX_STUTTER = 3          # collapse repeats up to three words long: "I don't I don't", "das ist das ist"


def _key(tok: str) -> str:
    return tok.strip(".,!?;:—–\"'").lower()


def clean_disfluencies(text: str, language: str = "en") -> str:
    """Drop filler words and collapse immediately repeated 1–3 word runs.

    Known limitation: a genuine immediate repetition ("I had had enough") loses one copy.
    Acceptable because this runs only on Parakeet output, which is not a default backend.
    """
    fillers = FILLERS.get(language, FILLERS["en"])
    toks = [t for t in _TOKEN.split(text.strip()) if t and _key(t) not in fillers]
    out: list[str] = []
    i = 0
    while i < len(toks):
        for size in range(_MAX_STUTTER, 0, -1):
            if len(out) >= size and i + size <= len(toks) \
                    and [_key(x) for x in out[-size:]] == [_key(x) for x in toks[i:i + size]]:
                i += size
                break
        else:
            out.append(toks[i])
            i += 1
    return " ".join(out)
```

- [x] **Step 4: Run to verify it passes**

Run: `uv run pytest tests/test_disfluency.py -v`
Expected: `4 passed`.

- [x] **Step 5: Write the failing STT test**

Replace `tests/test_stt.py` entirely:
```python
import subprocess, time
from pathlib import Path
import pytest

from ember.audio import to_wav
from ember.stt import STT_CONFIG, Transcriber, WhisperTranscriber, for_language

AUDIO = Path(__file__).parent / "fixtures" / "audio"


def test_config_covers_both_languages_and_dispatches():
    assert set(STT_CONFIG) == {"en", "de"}
    for lang, (backend, repo) in STT_CONFIG.items():
        assert backend in ("whisper", "parakeet") and repo.startswith("mlx-community/")
    t = for_language("de")
    assert isinstance(t, WhisperTranscriber) and t.language == "de"
    assert for_language("en").language == "en"
    with pytest.raises(ValueError, match="unknown language"):
        for_language("fr")


@pytest.mark.slow
class TestRealAudio:
    @pytest.fixture(scope="class")
    def clip(self) -> Path:
        AUDIO.mkdir(parents=True, exist_ok=True)
        aiff = AUDIO / "clip.aiff"
        if not aiff.exists():
            subprocess.run(["say", "-o", str(aiff),
                            "I rebuilt the whole backend three times. Nobody asked me to. "
                            "My friends thought I was wasting my time, and by any normal measure I probably was."],
                           check=True)
        return aiff

    @pytest.fixture(scope="class")
    def german_clip(self) -> Path:
        AUDIO.mkdir(parents=True, exist_ok=True)
        aiff = AUDIO / "clip_de.aiff"
        if not aiff.exists():
            subprocess.run(["say", "-v", "Anna", "-o", str(aiff),
                            "Ich habe das ganze Backend dreimal neu gebaut. Niemand hat mich darum gebeten. "
                            "Meine Freunde dachten, ich verschwende meine Zeit."], check=True)
        return aiff

    def test_to_wav_produces_16k_mono(self, clip, tmp_path):
        wav = to_wav(clip, tmp_path / "clip.wav")
        info = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "stream=sample_rate,channels",
                               "-of", "csv=p=0", str(wav)], capture_output=True, text=True, check=True).stdout
        assert info.strip() == "16000,1"

    def test_english_transcribe_after_warm(self, clip, tmp_path):
        wav = to_wav(clip, tmp_path / "clip.wav")
        t = for_language("en")
        warm_s = t.warm()
        t0 = time.perf_counter()
        text = t.transcribe(wav)
        dt = time.perf_counter() - t0
        print(f"\nen warm={warm_s:.1f}s transcribe={dt:.2f}s text={text!r}")
        assert "wasting my time" in text.lower() and "nobody asked me" in text.lower()
        assert dt < 6.0

    def test_german_transcribe_and_priming(self, german_clip, tmp_path):
        wav = to_wav(german_clip, tmp_path / "clip_de.wav")
        t = for_language("de")
        t.warm()
        text = t.transcribe(wav)
        primed = t.transcribe(wav, prime="Was hast du dafür schon aufgegeben?")
        print(f"\nde text={text!r}\nde primed={primed!r}")
        assert "backend" in text.lower() and "freunde" in text.lower()
        assert "ich" in primed.lower()                      # priming must not break the transcript
```

- [x] **Step 6: Run to verify failure**

Run: `uv run pytest tests/test_stt.py -v`
Expected: `ImportError: cannot import name 'STT_CONFIG' from 'ember.stt'`.

- [x] **Step 7: Add the dependency**

In `pyproject.toml`, add to `dependencies` after `"mlx-whisper>=0.4.3",`:
```toml
    "parakeet-mlx>=0.5.2",
```
Then: `uv sync`

- [x] **Step 8: Rewrite `ember/stt.py`**

```python
"""Local speech-to-text. One transcriber per language; the model is loaded once and stays resident.

Backend choice per language lives in STT_CONFIG and is set by measurement — run `ember stt-eval`.
Whisper is the default for both languages because it strips disfluencies natively (spec §3.2).
"""
import time
from pathlib import Path
from typing import Protocol

import mlx_whisper
import numpy as np

from .disfluency import clean_disfluencies

MODEL_REPO = "mlx-community/whisper-large-v3-turbo"
PARAKEET_REPO = "mlx-community/parakeet-tdt-0.6b-v3"

# language -> (backend, model repo). German is provisional until real German speech is measured.
STT_CONFIG: dict[str, tuple[str, str]] = {
    "en": ("whisper", MODEL_REPO),
    "de": ("whisper", MODEL_REPO),
}


class Transcriber(Protocol):
    language: str

    def warm(self) -> float: ...
    def transcribe(self, wav_path: Path, prime: str | None = None) -> str: ...


class WhisperTranscriber:
    def __init__(self, language: str = "en", repo: str = MODEL_REPO):
        self.language = language
        self.repo = repo

    def warm(self) -> float:
        """Load the model by transcribing one second of silence; mlx_whisper caches it on its ModelHolder."""
        t0 = time.perf_counter()
        mlx_whisper.transcribe(np.zeros(16000, dtype=np.float32), path_or_hf_repo=self.repo, language=self.language)
        return time.perf_counter() - t0

    def transcribe(self, wav_path: Path, prime: str | None = None) -> str:
        out = mlx_whisper.transcribe(str(wav_path), path_or_hf_repo=self.repo, language=self.language,
                                     initial_prompt=prime)
        return out["text"].strip()


class ParakeetTranscriber:
    """Faster than whisper but transcribes disfluencies verbatim, so its output is cleaned.
    Not a default backend — kept so `ember stt-eval` can keep comparing it (spec §3.2)."""

    def __init__(self, language: str = "en", repo: str = PARAKEET_REPO):
        self.language = language
        self.repo = repo
        self._model = None

    def _load(self):
        if self._model is None:
            from parakeet_mlx import from_pretrained
            self._model = from_pretrained(self.repo)
        return self._model

    def warm(self) -> float:
        t0 = time.perf_counter()
        self._load()
        return time.perf_counter() - t0

    def transcribe(self, wav_path: Path, prime: str | None = None) -> str:
        # Parakeet auto-detects language and takes no prompt; `prime` is accepted for interface parity.
        return clean_disfluencies(self._load().transcribe(str(wav_path)).text.strip(), self.language)


def for_language(lang: str) -> Transcriber:
    if lang not in STT_CONFIG:
        raise ValueError(f"unknown language {lang!r}")
    backend, repo = STT_CONFIG[lang]
    if backend == "whisper":
        return WhisperTranscriber(lang, repo)
    if backend == "parakeet":
        return ParakeetTranscriber(lang, repo)
    raise ValueError(f"unknown backend {backend!r} for {lang!r}")
```

- [x] **Step 9: Run the STT tests and record the numbers**

Run: `uv run pytest tests/test_stt.py -v -s`
Expected: `5 passed`, with printed German and English latencies. Note the German figure — it goes into the spec in Task 9.

- [x] **Step 10: Commit**

```bash
git add ember/stt.py ember/disfluency.py tests/test_stt.py tests/test_disfluency.py pyproject.toml uv.lock
git commit -m "feat: pluggable STT backends with per-language config and question priming (B3)" \
  -m "Co-Authored-By: WOZCODE <contact@withwoz.com>" \
  -m "Claude-Session: https://claude.ai/code/session_011xY91ug8K4Ke8JHFsa5ekB"
```

---

### Task 5: B4 — language threaded through session, store, observer, export

**Files:**
- Modify: `ember/session.py`, `ember/store.py`, `ember/observer.py`, `ember/export.py`
- Modify: `tests/test_session.py`, `tests/test_store.py`, `tests/test_observer.py`, `tests/test_export.py`

**Interfaces:**
- Consumes: `load_bank(lang)` (Task 3).
- Produces: `Session.language: str = "en"` (field order: after `consent_at`, before `turns`); `SessionStore.create(subject_code, consent_at, now, language="en")`; `language` in `meta.json`, `session.json`, `transcript.json`, `observer.json` and each `graph/data.js` subject; `ObserverResult.language: str`; `score(transcript, bank, llm, *, now=None)` reads `transcript.get("language", "en")`.

- [x] **Step 1: Write the failing tests**

Append to `tests/test_session.py`:
```python


def test_language_defaults_to_english_and_round_trips():
    s = make_session()
    assert s.language == "en"
    s.language = "de"
    assert Session.from_dict(s.to_dict()).language == "de"
```

Append to `tests/test_store.py`:
```python


def test_language_is_recorded_in_meta_and_transcript(tmp_path: Path):
    st = SessionStore(tmp_path / "sessions")
    s = st.create("S05", consent_at=99.0, now=100.0, language="de")
    assert s.language == "de"
    assert json.loads((st.dir_for(s.session_id) / "meta.json").read_text())["language"] == "de"
    st.save(s)
    assert json.loads((st.dir_for(s.session_id) / "transcript.json").read_text())["language"] == "de"
    assert st.load(s.session_id).language == "de"
    assert st.create("S06", consent_at=1.0, now=2.0).language == "en"      # default unchanged
```

Append to `tests/test_observer.py`:
```python


def test_observer_carries_language_and_tells_the_model(bank):
    tr = transcript(bank)
    tr["language"] = "de"
    llm = FakeLLM([raw()])
    out = score(tr, bank, llm, now=0.0)
    assert out.language == "de"
    assert "German" in llm.calls[0]["system"]
    tr_en = transcript(bank)
    llm_en = FakeLLM([raw()])
    assert score(tr_en, bank, llm_en, now=0.0).language == "en"
    assert "German" not in llm_en.calls[0]["system"]
```

Append to `tests/test_export.py`:
```python


def test_language_reaches_the_graph(tmp_path: Path):
    _session(tmp_path, "S01_x", "S01", 4, "first")
    p = tmp_path / "S01_x"
    tr = json.loads((p / "transcript.json").read_text())
    tr["language"] = "de"
    (p / "transcript.json").write_text(json.dumps(tr))
    data = collect(tmp_path, load_bank(), now=0.0)
    assert data["subjects"][0]["language"] == "de"
```

- [x] **Step 2: Run to verify failure**

Run: `uv run pytest tests/test_session.py tests/test_store.py tests/test_observer.py tests/test_export.py -v`
Expected: four failures — `Session` has no `language`, `create()` rejects the keyword, `ObserverResult` has no `language`, subjects have no `language`.

- [x] **Step 3: Add the field to `Session`**

In `ember/session.py`, inside `class Session`, insert after `consent_at: float`:
```python
    language: str = "en"
```

- [x] **Step 4: Record it in the store**

In `ember/store.py`, change the `create` signature and the two writes:
```python
    def create(self, subject_code: str, consent_at: float, now: float, language: str = "en") -> Session:
        s = Session(session_id=new_session_id(subject_code, now), subject_code=subject_code,
                    started_at=now, consent_at=consent_at, language=language)
        d = self.dir_for(s.session_id)
        (d / "audio").mkdir(parents=True, exist_ok=True)
        (d / "meta.json").write_text(json.dumps({
            "session_id": s.session_id, "subject_code": subject_code, "started_at": now,
            "consent_at": consent_at, "language": language,
            "rubric_version": RUBRIC_VERSION, "operator_notes": ""}, indent=2))
```
and in `save`, add `language` to the `transcript.json` payload:
```python
        (d / "transcript.json").write_text(json.dumps({
            "session_id": session.session_id, "subject_code": session.subject_code,
            "started_at": session.started_at, "closed": session.closed, "language": session.language,
            "mirror": session.mirror, "take_home": session.take_home,
            "turns": session.transcript_for_observer()}, indent=2, ensure_ascii=False))
```

- [x] **Step 5: Tell the observer**

In `ember/observer.py`, add `language: str = "en"` to `class ObserverResult` (after `rubric_version`). Change `build_observer_system` to take the language and append one line — replace its signature and final return:
```python
def build_observer_system(rubric: dict[str, RubricEntry], language: str = "en") -> str:
```
and immediately before the closing `"""` of the returned f-string, after the `Rubric:` block, append:
```python
    note = ("\nThe transcript is in German. Score against the English rubric above; quote evidence verbatim "
            "in German, exactly as the subject said it. Write every note and flag in English — the operator reads them.\n"
            if language == "de" else "")
    return f"""...existing text...

Rubric:
{joined}
{note}"""
```
In `validate`, accept and pass the language — change its signature to add `language: str = "en"` after `rubric_version: str`, and add `language=language` to the `ObserverResult(...)` construction. In `score`, read it from the transcript and pass it both places:
```python
def score(transcript: dict, bank: Bank, llm, *, now: float | None = None) -> ObserverResult:
    language = transcript.get("language", "en")
    raw = llm.call_json(system=build_observer_system(bank.rubric, language), user=build_observer_user(transcript),
                        schema=OBSERVER_SCHEMA, effort="high")
    ts = datetime.fromtimestamp(now if now is not None else time.time(), tz=timezone.utc).isoformat()
    return validate(raw, transcript, bank, subject_id=transcript["subject_code"],
                    session_id=transcript["session_id"], scored_at=ts, rubric_version=RUBRIC_VERSION,
                    language=language)
```

- [x] **Step 6: Carry it to the graph**

In `ember/export.py`, inside `collect`'s subject dict, add after `"rubric_version": r["rubric_version"],`:
```python
                         "language": tr.get("language", r.get("language", "en")),
```

- [x] **Step 7: Run the full suite**

Run: `uv run pytest -q`
Expected: all pass.

- [x] **Step 8: Commit**

```bash
git add ember/session.py ember/store.py ember/observer.py ember/export.py \
        tests/test_session.py tests/test_store.py tests/test_observer.py tests/test_export.py
git commit -m "feat: record session language end to end and tell the observer (B4)" \
  -m "Co-Authored-By: WOZCODE <contact@withwoz.com>" \
  -m "Claude-Session: https://claude.ai/code/session_011xY91ug8K4Ke8JHFsa5ekB"
```

---

### Task 6: B5 — UI copy in both languages, and the engine told the language

**Files:**
- Create: `ember/copy.py`, `tests/test_copy.py`
- Modify: `ember/engine.py`, `tests/test_engine.py`

**Interfaces:**
- Consumes: `LANGUAGES` from `ember.bank` (Task 3).
- Produces: `COPY: dict[str, dict[str, str]]` with identical key sets per language; `copy_for(lang: str) -> dict[str, str]`; `Engine(bank, llm)` unchanged in signature but its system prompt carries a German line when `bank.language == "de"`.

- [x] **Step 1: Write the failing tests**

`tests/test_copy.py`:
```python
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
```

Append to `tests/test_engine.py`:
```python


def test_german_bank_puts_a_german_instruction_in_the_system_prompt(mini_bank):
    from ember.engine import build_system_prompt
    assert "German" not in build_system_prompt(mini_bank)
    german = mini_bank.model_copy(update={"language": "de"})
    sp = build_system_prompt(german)
    assert "German" in sp and "du" in sp
```

- [x] **Step 2: Run to verify failure**

Run: `uv run pytest tests/test_copy.py tests/test_engine.py -v`
Expected: `ModuleNotFoundError: No module named 'ember.copy'` and the engine test failing on a missing German line.

- [x] **Step 3: Write the copy module**

`ember/copy.py`:
```python
"""Every user-facing string on the subject screen, per language (spec §4.3).
German is du throughout — the register the bank uses."""

COPY: dict[str, dict[str, str]] = {
    "en": {
        "consent_title": "Before we start",
        "consent_1": "1. This is a ~7-minute psychological interview. It's recorded and transcribed.",
        "consent_2": "2. Transcript text goes to Anthropic, through Malek's Claude subscription, to pick questions and score. Audio stays on this laptop.",
        "consent_3": "3. Your session goes into a graph Malek reads. Ask him and he'll delete it.",
        "code_label": "Subject code",
        "start": "I understand — start",
        "hint_idle": "Hold space to speak. Release when you're done.",
        "hint_recording": "● recording — release space when done",
        "hint_waiting": "…",
        "retry": "Didn't catch that — once more?",
        "closing": "That's the interview.",
    },
    "de": {
        "consent_title": "Bevor wir anfangen",
        "consent_1": "1. Das ist ein etwa 7-minütiges psychologisches Interview. Es wird aufgenommen und transkribiert.",
        "consent_2": "2. Der transkribierte Text geht über Maleks Claude-Abo an Anthropic, um Fragen auszuwählen und auszuwerten. Die Audioaufnahme bleibt auf diesem Laptop.",
        "consent_3": "3. Deine Sitzung landet in einer Auswertung, die Malek liest. Sag ihm Bescheid, dann löscht er sie.",
        "code_label": "Teilnehmer-Code",
        "start": "Verstanden — los",
        "hint_idle": "Halte die Leertaste gedrückt, um zu sprechen. Loslassen, wenn du fertig bist.",
        "hint_recording": "● Aufnahme läuft — Leertaste loslassen, wenn du fertig bist",
        "hint_waiting": "…",
        "retry": "Das habe ich nicht verstanden — nochmal?",
        "closing": "Das war das Interview.",
    },
}


def copy_for(lang: str) -> dict[str, str]:
    return COPY.get(lang, COPY["en"])
```

- [x] **Step 4: Tell the engine the language**

In `ember/engine.py`, inside `build_system_prompt(bank)`, add before the `return`:
```python
    lang_note = ("\nThe subject speaks German. Every probe you write and the close must be in German, "
                 "addressing them as du. The candidate questions below are already German — pick by id as usual.\n"
                 if bank.language == "de" else "")
```
and insert `{lang_note}` into the returned f-string immediately after the `Actions:` block and before the `surfaced_tags:` line.

- [x] **Step 5: Run to verify both pass**

Run: `uv run pytest tests/test_copy.py tests/test_engine.py -v`
Expected: `3 passed` and `14 passed`.

- [x] **Step 6: Commit**

```bash
git add ember/copy.py ember/engine.py tests/test_copy.py tests/test_engine.py
git commit -m "feat: per-language UI copy and a German instruction for the engine (B5)" \
  -m "Co-Authored-By: WOZCODE <contact@withwoz.com>" \
  -m "Claude-Session: https://claude.ai/code/session_011xY91ug8K4Ke8JHFsa5ekB"
```

---

### Task 7: The German bank — HUMAN GATE at the end

**Files:**
- Create: `ember/bank/de/opener.yaml`, `ember/bank/de/questions.yaml`, `tests/test_german_bank.py`

**Interfaces:**
- Consumes: `load_bank("de")` (Task 3).
- Produces: the shipped German bank — same ids, slots, targets, prerequisites and threat values as `bank/en/questions.yaml`.

- [ ] **Step 1: Write the failing test**

`tests/test_german_bank.py`:
```python
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
```

- [ ] **Step 2: Run to verify failure**

Run: `uv run pytest tests/test_german_bank.py -v`
Expected: `FileNotFoundError: … ember/bank/de/opener.yaml`.

- [ ] **Step 3: Write the German opener**

`ember/bank/de/opener.yaml`:
```yaml
text: >-
  Denk an jemanden, den du kennst und von dem du sicher bist, dass er es schaffen wird.
  Nicht berühmt — jemand, den du wirklich kennst. Was macht diese Person anders als alle anderen?
rephrase: >-
  Jemand, den du kennst und der es schaffen wird. Was ist anders daran, wie diese Person
  einen ganz normalen Dienstag verbringt?
fallback_take_home: >-
  Was müsstest du aufhören zu tun, um die Person zu werden, die du zuerst beschrieben hast?
```

- [ ] **Step 4: Write the German spine questions**

`ember/bank/de/questions.yaml`:
```yaml
candidates:
  # ── Slot 2 · Fire · threat 4–5 · keine Voraussetzungen erlaubt ──────────────
  - id: F1-a
    slot: 2
    cluster: fire
    targets: [F1]
    threat: 4
    framing: counterfactual-removal
    default: true
    text: >-
      Geld ist gelöst. Miete, Essen, Familie — für immer geregelt. Es ist ein Dienstag.
      Was machst du um zwei Uhr nachmittags?
    rephrase: >-
      Wenn Geld nie wieder ein Problem wäre — was würdest du an einem ganz normalen
      Nachmittag tatsächlich tun?
  - id: F1-b
    slot: 2
    cluster: fire
    targets: [F1]
    threat: 5
    framing: envy-locator
    text: Wessen Leben macht dich neidisch, auf eine Art, die du dir ungern eingestehst?
    rephrase: Auf wessen Leben schaust du und spürst etwas, das du nicht gerne spürst?
  - id: F3-c
    slot: 2
    cluster: fire
    targets: [F3]
    threat: 4
    framing: third-person-projection
    text: >-
      Denk an die talentierteste Person, die du kennst und die trotzdem nicht vorankommt.
      Was ist die eine Sache, die sie nicht tut?
    rephrase: Die begabteste Person, die du kennst und die feststeckt — wovor drückt sie sich?

  # ── Slot 3 · Fire · threat 5–6 ──────────────────────────────────────────────
  - id: F2-a
    slot: 3
    cluster: fire
    targets: [F2]
    threat: 5
    framing: cost-already-paid
    default: true
    text: >-
      Was hast du dafür schon aufgegeben, das die Leute um dich herum nicht verstanden haben?
    rephrase: >-
      Was hat es dich gekostet — Zeit, Menschen, Geld — etwas zu verfolgen, das dir
      wichtig war?
  - id: F2-b
    slot: 3
    cluster: fire
    targets: [F2]
    threat: 6
    framing: cost-already-paid
    prerequisites: [relationship]
    text: Du hast jemanden erwähnt, der dir nahesteht. Was hat das, was du verfolgst, dich bei dieser Person gekostet?
    rephrase: Die Person, die du erwähnt hast — wo ist dir dein Ehrgeiz dort in die Quere gekommen?
  - id: F3-a
    slot: 3
    cluster: fire
    targets: [F3]
    threat: 5
    framing: settled-person-read
    text: >-
      Denk an jemanden, der sich eingerichtet hat. Bequemes Leben, hat aufgehört zu drücken.
      Wie ist es, mit dieser Person Zeit zu verbringen?
    rephrase: Jemand, der aufgehört hat, es zu versuchen — wie fühlt sich ein Abend mit ihm an?
  - id: F1-d
    slot: 3
    cluster: fire
    targets: [F1]
    threat: 5
    framing: discrepancy
    prerequisites: [money]
    text: Du hast vorhin Geld erwähnt. Wenn die Sache, die du willst, damit nichts einbringen würde — was ändert sich?
    rephrase: Nimm Geld komplett raus. Was bleibt von dem Wollen übrig?
  - id: F1-c
    slot: 3
    cluster: fire
    targets: [F1, F3]
    threat: 5
    framing: third-person-projection
    prerequisites: [named-project]
    text: >-
      Du hast etwas erwähnt, das du baust. Wenn es funktioniert — wie fühlt sich das
      körperlich an?
    rephrase: Das, woran du arbeitest — was ist das Gefühl, wenn es klickt?

  # ── Slot 4 · Fire tief · threat 6–7 ─────────────────────────────────────────
  - id: F2-c
    slot: 4
    cluster: fire
    targets: [F2, F3]
    threat: 7
    framing: cost-already-paid
    default: true
    text: >-
      Sagen wir, es klappt. Du bekommst genau das, was du beschrieben hast. Wozu musstest du
      dafür werden, von dem du nicht sicher bist, dass du es sein willst?
    rephrase: Wenn du alles bekommst, was du willst — was wird es dich als Mensch gekostet haben?
  - id: F3-b
    slot: 4
    cluster: fire
    targets: [F3]
    threat: 6
    framing: forking
    prerequisites: [failure]
    text: Du hast etwas erwähnt, das nicht funktioniert hat. War das das Scheitern — oder war es, dass du aufgehört hast?
    rephrase: Diese Sache, die gescheitert ist — was hat sie wirklich beendet, das Scheitern oder das Aufhören?
  - id: F1-e
    slot: 4
    cluster: fire
    targets: [F1]
    threat: 7
    framing: aftermath-not-event
    prerequisites: [quit]
    text: Du hast gesagt, du hast etwas hingeschmissen. Was hast du eigentlich verlassen?
    rephrase: Als du aufgehört hast — wovon bist du in Wirklichkeit weggegangen?

  # ── Slot 5 · Compass ────────────────────────────────────────────────────────
  - id: C1-a
    slot: 5
    cluster: compass
    targets: [C1]
    threat: 6
    framing: pressure-decision
    default: true
    text: >-
      Das letzte Mal, als du dich schnell entscheiden musstest und es jemanden etwas gekostet hat.
      Wofür hast du dich entschieden?
    rephrase: Eine schnelle Entscheidung, die etwas gekostet hat — wie hast du entschieden, und warum so?
  - id: C2-a
    slot: 5
    cluster: compass
    targets: [C2]
    threat: 5
    framing: scale-of-things
    text: Was ist das Größte, von dem du ein kleiner Teil bist?
    rephrase: Wozu gehörst du, das größer ist als dein eigenes Leben?
  - id: C2-b
    slot: 5
    cluster: compass
    targets: [C2]
    threat: 6
    framing: forking
    prerequisites: [faith]
    text: Du hast Glauben erwähnt. Wenn er und das, was du willst, in verschiedene Richtungen zeigen — was gibt nach?
    rephrase: Wenn Glaube und Ehrgeiz sich widersprechen — welcher von beiden weicht?
  - id: C3-a
    slot: 5
    cluster: compass
    targets: [C3]
    threat: 6
    framing: fear-of-self
    text: Was für ein Mensch hast du Angst zu werden?
    rephrase: Welche Version von dir selbst versuchst du zu vermeiden?
  - id: C1-b
    slot: 5
    cluster: compass
    targets: [C1]
    threat: 6
    framing: discrepancy
    prerequisites: [family]
    text: Deine Familie kam vorhin vor. Was ist eine Regel, nach der du lebst, von der sie sagen würden, dass du sie brichst?
    rephrase: Etwas, das du übers Leben glaubst — von dem deine Familie sagen würde, dass du dich nicht daran hältst?

  # ── Slot 6 · Ground ─────────────────────────────────────────────────────────
  - id: G1-a
    slot: 6
    cluster: ground
    targets: [G1]
    threat: 5
    framing: empty-room
    default: true
    text: Handy ist leer. Sechs Stunden kommt niemand. Du bist vierzig Minuten drin. Was passiert?
    rephrase: Sechs Stunden allein, kein Handy. Wie sieht die Mitte davon aus?
  - id: G2-a
    slot: 6
    cluster: ground
    targets: [G2]
    threat: 6
    framing: aftermath-not-event
    text: Etwas hat dich mal aus der Bahn geworfen. Nicht die Sache selbst — was hast du danach aufgebaut?
    rephrase: Nach dem Schlimmsten, das dir passiert ist — was hast du danach anders gemacht?
  - id: G2-b
    slot: 6
    cluster: ground
    targets: [G2]
    threat: 7
    framing: aftermath-not-event
    prerequisites: [loss]
    text: Du hast erwähnt, dass du etwas verloren hast. Was hast du danach entschieden, das du nie laut gesagt hast?
    rephrase: Nach diesem Verlust — was hast du still für dich beschlossen?
  - id: G3-a
    slot: 6
    cluster: ground
    targets: [G3]
    threat: 5
    framing: people-as
    text: Wenn du am besten bist — was machen die Menschen, die dir am nächsten stehen?
    rephrase: An deinem besten Tag — wo sind die Menschen, die du liebst, und was tun sie?
  - id: G3-b
    slot: 6
    cluster: ground
    targets: [G3]
    threat: 6
    framing: people-as
    prerequisites: [solitude]
    text: Du hast gesagt, du verbringst viel Zeit allein. Wer weiß das?
    rephrase: So viel allein zu sein — wer weiß das eigentlich von dir?
```

- [ ] **Step 5: Run to verify it passes**

Run: `uv run pytest tests/test_german_bank.py tests/test_bank.py -v`
Expected: `3 passed` and `12 passed`. If a German question trips the yes/no validator, rewrite the question — never weaken the validator.

- [ ] **Step 6: Commit**

```bash
git add ember/bank/de/ tests/test_german_bank.py
git commit -m "feat: German question bank — opener, 21 spine questions, du register" \
  -m "Co-Authored-By: WOZCODE <contact@withwoz.com>" \
  -m "Claude-Session: https://claude.ai/code/session_011xY91ug8K4Ke8JHFsa5ekB"
```

- [ ] **Step 7: STOP — human review gate**

Spec §4.2 and v1 spec §5.1: the bank is reviewed line by line before any session runs. Send Malek `ember/bank/de/questions.yaml` and `opener.yaml` **rendered as a table** (id · framing · fires-when · question · rephrase), the way the English bank was presented. He reads it as a German speaker — the test only proves structure, never that a question lands. Do not start Task 8 until he has approved or given edits. Edits ship as a follow-up commit `bank: German revisions from review`.

---

### Task 8: The toggle — server, subject page, operator page

**Files:**
- Modify: `ember/server.py`, `ember/static/subject.html`, `ember/static/operator.html`, `ember/cli.py`
- Modify: `tests/test_server.py`, `tests/test_static.py`

**Interfaces:**
- Consumes: `copy_for` (Task 6); `for_language` (Task 4); `load_bank(lang)` (Task 3); `SessionStore.create(..., language=)` (Task 5).
- Produces: `create_app(store, engines: dict[str, Engine], transcribers: dict[str, Transcriber]) -> FastAPI` — **both are now dicts keyed by language**; `GET /api/copy/{lang}`; `POST /api/session` accepts `{"subject_code", "language"}`; `GET /api/session/{sid}/state` includes `language`.

- [ ] **Step 1: Write the failing tests**

In `tests/test_server.py`, replace the `_client` helper so it builds the per-language dicts, and append the new tests:
```python
def _client(tmp_path, mini_bank, llm_responses, stt_texts, language="en"):
    store = SessionStore(tmp_path / "sessions")
    engines = {"en": Engine(mini_bank, FakeLLM(llm_responses)),
               "de": Engine(mini_bank.model_copy(update={"language": "de"}), FakeLLM(list(llm_responses)))}
    transcribers = {"en": FakeTranscriber(stt_texts), "de": FakeTranscriber(list(stt_texts))}
    app = create_app(store, engines, transcribers)

    def _fake_wav(src, dst):                                  # skip ffmpeg in tests
        dst.write_bytes(b"RIFF")
        return dst
    app.state.to_wav = _fake_wav
    return TestClient(app), store
```
and append:
```python


def test_copy_endpoint_serves_both_languages(tmp_path, mini_bank):
    client, _ = _client(tmp_path, mini_bank, [], [])
    en = client.get("/api/copy/en").json()
    de = client.get("/api/copy/de").json()
    assert en["start"] == "I understand — start" and de["start"] == "Verstanden — los"
    assert set(en) == set(de)
    assert client.get("/api/copy/fr").json() == en          # unknown language falls back


def test_session_language_selects_store_and_state(tmp_path, mini_bank):
    client, store = _client(tmp_path, mini_bank, [], [])
    sid = client.post("/api/session", json={"subject_code": "S01", "language": "de"}).json()["session_id"]
    assert store.load(sid).language == "de"
    assert client.get(f"/api/session/{sid}/state").json()["language"] == "de"


def test_language_defaults_to_english_when_omitted(tmp_path, mini_bank):
    client, store = _client(tmp_path, mini_bank, [], [])
    sid = client.post("/api/session", json={"subject_code": "S01"}).json()["session_id"]
    assert store.load(sid).language == "en"


def test_answer_uses_the_session_language_transcriber(tmp_path, mini_bank):
    client, store = _client(tmp_path, mini_bank,
                            [{"action": "pick", "candidate_id": "S2-a", "surfaced_tags": [], "reason": "r"}],
                            [LONG])
    sid = client.post("/api/session", json={"subject_code": "S01", "language": "de"}).json()["session_id"]
    _post_audio(client, sid)
    assert store.load(sid).turns[0].answer == LONG          # the "de" transcriber was the one consulted
```

In `tests/test_static.py`, replace the single test's body with:
```python
def test_pages_served_and_wired(tmp_path, mini_bank):
    engines = {"en": Engine(mini_bank, FakeLLM()), "de": Engine(mini_bank, FakeLLM())}
    app = create_app(SessionStore(tmp_path / "s"), engines, {"en": None, "de": None})
    c = TestClient(app)
    subj = c.get("/").text
    op = c.get("/operator").text
    for needle in ("/api/session", "/answer", "/rephrase", "/resume", "/api/copy/", "MediaRecorder", "keydown",
                   'id="consent"', 'id="question"', 'id="close"', 'id="langbar"', 'data-lang="de"'):
        assert needle in subj, needle
    assert "/state" in op and "setInterval" in op and "language" in op
    assert 'id="transcript"' not in subj and "last_answer" not in subj   # subject never sees their transcript
```

- [ ] **Step 2: Run to verify failure**

Run: `uv run pytest tests/test_server.py tests/test_static.py -v`
Expected: `TypeError` — `create_app()` gets a dict where it expects an `Engine`.

- [ ] **Step 3: Make the server language-aware**

In `ember/server.py`: add `from .copy import copy_for` to the imports, add `language` to `NewSession`, and change `create_app` and the three affected routes.

```python
class NewSession(BaseModel):
    subject_code: str
    language: str = "en"


def create_app(store: SessionStore, engines: dict, transcribers: dict) -> FastAPI:
    app = FastAPI(title="ember")
    app.state.store, app.state.engines, app.state.transcribers = store, engines, transcribers
    app.state.to_wav = to_wav

    def _engine(session: Session):
        return engines.get(session.language, engines["en"])
```
Every existing `engine.` call inside a route becomes `_engine(session).`, and `_ask`/`_close` take the engine from the session they are given. Concretely, replace the body of `_close` and `new_session`, and the two `engine.` uses in `answer` and `rephrase`:
```python
    def _close(session: Session, now: float) -> dict:
        out = _engine(session).close(session)
        session.pending = None
        session.closed, session.mirror, session.take_home = True, out.mirror, out.take_home
        store.append_engine_log(session.session_id, {"at": now, "kind": "close", "mirror": out.mirror, "take_home": out.take_home})
        store.save(session)
        return {"kind": "close", "mirror": out.mirror, "take_home": out.take_home}

    @app.get("/api/copy/{lang}")
    def copy(lang: str):
        return copy_for(lang)

    @app.post("/api/session")
    def new_session(body: NewSession):
        now = time.time()
        lang = body.language if body.language in engines else "en"
        session = store.create(body.subject_code, consent_at=now, now=now, language=lang)
        resp = _ask(session, engines[lang].first(), now)
        return {"session_id": session.session_id, "language": lang, **resp}
```
In `answer`, the transcriber lookup and the engine call become:
```python
        transcriber = transcribers.get(session.language, transcribers["en"])
        text = await asyncio.to_thread(transcriber.transcribe, wav)
```
and
```python
        nxt = await asyncio.to_thread(_engine(session).next, session, now)
```
In `answer`'s retry branch, the message comes from copy:
```python
                return {"retry": True, "question": session.pending.question,
                        "message": copy_for(session.language)["retry"]}
```
In `rephrase`, the bank lookup becomes `_engine(session).bank`. In `state`, add `"language": s.language,` to the returned dict.

- [ ] **Step 4: Build one engine and transcriber per language in the CLI**

In `ember/cli.py`, inside the `serve` branch, replace the transcriber/app construction:
```python
        from .bank import LANGUAGES, load_bank
        transcribers = {lang: for_language(lang) for lang in LANGUAGES}
        if not args.no_warm:
            for lang, t in transcribers.items():
                print(f"loading {lang} speech model… {t.warm():.1f}s")
        engines = {lang: Engine(load_bank(lang), LLM()) for lang in LANGUAGES}
        app = create_app(SessionStore(args.sessions), engines, transcribers)
```
changing the import line `from .stt import Transcriber` to `from .stt import for_language`.

- [ ] **Step 5: Add the language bar to the subject page**

In `ember/static/subject.html`, add to the `<style>` block:
```css
  #langbar{position:fixed;top:0;left:0;right:0;display:flex;justify-content:space-between;align-items:center;
           padding:10px 18px;font-size:.85rem;color:#7a7a7a}
  #langbar button{background:none;border:0;color:#7a7a7a;font:inherit;cursor:pointer;padding:2px 6px;border-radius:4px}
  #langbar button[aria-pressed="true"]{color:#ececec;background:#222}
```
Insert immediately after `<main>` opens, before `<section id="consent">`:
```html
  <div id="langbar"><span>ember</span>
    <span><button data-lang="en" aria-pressed="true">EN</button><button data-lang="de" aria-pressed="false">DE</button></span>
  </div>
```
Add to the `<script>`, above `$('accept').onclick`:
```javascript
let lang = new URLSearchParams(location.search).get('lang') === 'de' ? 'de' : 'en';
let C = {};

async function loadCopy(){
  C = await fetch(`/api/copy/${lang}`).then(r=>r.json());
  $('consent').querySelector('h1').textContent = C.consent_title;
  const ps = $('consent').querySelectorAll('p');
  ps[0].textContent = C.consent_1; ps[1].textContent = C.consent_2; ps[2].textContent = C.consent_3;
  $('consent').querySelector('label').childNodes[0].textContent = C.code_label + ' ';
  $('accept').textContent = C.start;
  $('close').querySelector('.hint').textContent = C.closing;
  setStatus(C.hint_idle);
  for (const b of document.querySelectorAll('#langbar button')) b.setAttribute('aria-pressed', String(b.dataset.lang === lang));
}
for (const b of document.querySelectorAll('#langbar button')) b.onclick = () => { lang = b.dataset.lang; loadCopy(); };
loadCopy();
```
Then replace the three hard-coded strings in the existing script: in `showQuestion` use `setStatus(C.hint_idle)`, in the `keydown` handler use `setStatus(C.hint_recording, 'rec')`, in `send` use `setStatus(C.hint_waiting, 'wait')` and `setStatus(body.message + '  ' + C.hint_idle)`. In `$('accept').onclick`, send the language and hide the bar:
```javascript
  const body = await fetch('/api/session', {method:'POST', headers:{'content-type':'application/json'}, body: JSON.stringify({subject_code: code, language: lang})}).then(r=>r.json());
  $('langbar').style.display = 'none';
  sid = body.session_id; showQuestion(body);
```
In the resume IIFE, add `$('langbar').style.display = 'none';` before `showQuestion`.

- [ ] **Step 6: Show the language on the operator page**

In `ember/static/operator.html`, add a row to the `<dl>` after the `slot` row:
```html
  <dt>language</dt><dd id="language"></dd>
```
and in `tick()`, after the `slot` assignment:
```javascript
  $('language').textContent = s.language || 'en';
```

- [ ] **Step 7: Run the full suite**

Run: `uv run pytest -q`
Expected: all pass.

- [ ] **Step 8: Commit**

```bash
git add ember/server.py ember/cli.py ember/static/ tests/test_server.py tests/test_static.py
git commit -m "feat: EN | DE toggle, per-language engines and transcribers, copy endpoint" \
  -m "Co-Authored-By: WOZCODE <contact@withwoz.com>" \
  -m "Claude-Session: https://claude.ai/code/session_011xY91ug8K4Ke8JHFsa5ekB"
```

---

### Task 9: `ember stt-eval`, a recorded German engine turn, and a live German session

**Files:**
- Create: `ember/stt_eval.py`, `calibration/stt_clips.yaml`, `tests/test_stt_eval.py`, `tests/test_engine_recorded_de.py`
- Modify: `ember/cli.py`, `docs/superpowers/specs/2026-09-11-german-and-stt-design.md`

**Interfaces:**
- Consumes: `for_language`, `WhisperTranscriber`, `ParakeetTranscriber`, `STT_CONFIG` (Task 4); `load_bank("de")` (Task 7); `RecordingLLM` (`tests/recording.py`).
- Produces: `wer(reference: str, hypothesis: str) -> float`; `Clip` dataclass (`path: Path, language: str, reference_text: str`); `load_clips(path: Path) -> list[Clip]`; `evaluate(clips, backends: list[tuple[str, str, str]]) -> list[dict]`; `render(rows) -> str`; `ember stt-eval [--clips …] [--lang …]`.

- [ ] **Step 1: Write the failing eval test**

`tests/test_stt_eval.py`:
```python
from pathlib import Path
import yaml

from ember.stt_eval import wer, load_clips, render


def test_wer_is_edit_distance_over_reference_length():
    assert wer("the cat sat on the mat", "the cat sat on the mat") == 0.0
    assert wer("the cat sat", "the cat") == 1 / 3
    assert wer("the cat sat", "the dog sat") == 1 / 3
    assert wer("hätte es schön", "hatte es schon") == 2 / 3        # umlauts are errors, not matches
    assert wer("", "anything") == 0.0                              # empty reference cannot be scored


def test_load_clips_round_trip(tmp_path: Path):
    (tmp_path / "a.wav").write_bytes(b"RIFF")
    y = tmp_path / "clips.yaml"
    y.write_text(yaml.safe_dump({"clips": [{"path": "a.wav", "language": "de", "reference_text": "Hallo Welt"}]}))
    clips = load_clips(y)
    assert len(clips) == 1 and clips[0].language == "de" and clips[0].path == tmp_path / "a.wav"


def test_render_table_has_a_row_per_backend_and_clip():
    rows = [{"backend": "whisper", "repo": "mlx-community/whisper-large-v3-turbo", "language": "de",
             "clip": "a.wav", "wer": 0.05, "seconds": 1.2, "rtf": 12.0}]
    out = render(rows)
    assert "whisper" in out and "5.0%" in out and "1.20s" in out and "de" in out
```

- [ ] **Step 2: Run to verify failure**

Run: `uv run pytest tests/test_stt_eval.py -v`
Expected: `ModuleNotFoundError: No module named 'ember.stt_eval'`.

- [ ] **Step 3: Implement the eval**

`ember/stt_eval.py`:
```python
"""Measure STT backends against reference clips (spec §3.4). `ember stt-eval`."""
import re
import subprocess
import time
from dataclasses import dataclass
from pathlib import Path

import yaml

from .stt import PARAKEET_REPO, STT_CONFIG, MODEL_REPO, ParakeetTranscriber, WhisperTranscriber

LARGE_V3_REPO = "mlx-community/whisper-large-v3-mlx"
_WORD = re.compile(r"[\w']+", re.UNICODE)


def _words(s: str) -> list[str]:
    return _WORD.findall(s.lower())


def wer(reference: str, hypothesis: str) -> float:
    """Levenshtein word distance over reference length. 0.0 for an empty reference."""
    r, h = _words(reference), _words(hypothesis)
    if not r:
        return 0.0
    d = list(range(len(h) + 1))
    for i in range(1, len(r) + 1):
        prev, d[0] = d[0], i
        for j in range(1, len(h) + 1):
            cur = d[j]
            d[j] = min(d[j] + 1, d[j - 1] + 1, prev + (r[i - 1] != h[j - 1]))
            prev = cur
    return d[len(h)] / len(r)


@dataclass
class Clip:
    path: Path
    language: str
    reference_text: str


def load_clips(path: Path) -> list[Clip]:
    path = Path(path)
    data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    return [Clip(path=(path.parent / c["path"]).resolve(), language=c["language"], reference_text=c["reference_text"])
            for c in (data.get("clips") or [])]


def _duration(p: Path) -> float:
    out = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", str(p)],
                         capture_output=True, text=True).stdout.strip()
    return float(out) if out else 0.0


def evaluate(clips: list[Clip], backends: list[tuple[str, str, str]]) -> list[dict]:
    """backends: (label, kind, repo). Returns one row per (backend, clip)."""
    rows = []
    for label, kind, repo in backends:
        for clip in clips:
            t = WhisperTranscriber(clip.language, repo) if kind == "whisper" else ParakeetTranscriber(clip.language, repo)
            try:
                t.warm()
                t.transcribe(clip.path)                      # discard the first run
                t0 = time.perf_counter()
                text = t.transcribe(clip.path)
                dt = time.perf_counter() - t0
                dur = _duration(clip.path)
                rows.append({"backend": label, "repo": repo, "language": clip.language, "clip": clip.path.name,
                             "wer": wer(clip.reference_text, text), "seconds": dt,
                             "rtf": (dur / dt) if dt else 0.0, "text": text})
            except Exception as e:
                rows.append({"backend": label, "repo": repo, "language": clip.language, "clip": clip.path.name,
                             "wer": None, "seconds": None, "rtf": None, "text": f"ERROR {e!r}"[:120]})
    return rows


def render(rows: list[dict]) -> str:
    out = [f"{'backend':22s} {'lang':4s} {'clip':18s} {'WER':>7s} {'time':>8s} {'RTF':>6s}"]
    for r in rows:
        w = f"{r['wer'] * 100:6.1f}%" if r["wer"] is not None else "    n/a"
        s = f"{r['seconds']:7.2f}s" if r["seconds"] is not None else "    n/a"
        f = f"{r['rtf']:5.0f}x" if r["rtf"] else "   n/a"
        out.append(f"{r['backend']:22s} {r['language']:4s} {r['clip']:18s} {w} {s} {f}")
    out.append("\ncurrent defaults: " + ", ".join(f"{k}={v[0]}:{v[1].split('/')[-1]}" for k, v in STT_CONFIG.items()))
    return "\n".join(out)


DEFAULT_BACKENDS = [("whisper turbo", "whisper", MODEL_REPO),
                    ("whisper large-v3", "whisper", LARGE_V3_REPO),
                    ("parakeet v3", "parakeet", PARAKEET_REPO)]
```

- [ ] **Step 4: Create the reference clips**

```bash
cd ~/Desktop/SCIO/ember && mkdir -p calibration/clips
say -v Anna -o /tmp/de1.aiff "Ehrlich gesagt komme ich immer wieder auf dieses Projekt zurück, das ich vor zwei Jahren angefangen habe. Niemand hat mich darum gebeten. Ich habe es dreimal neu gebaut, weil sich die ersten Versionen falsch angefühlt haben."
say -o /tmp/en1.aiff "Honestly the thing I keep coming back to is this project I started two years ago. Nobody asked me to. I rebuilt it three times because the first versions felt wrong."
uv run python -c "
from pathlib import Path
from ember.audio import to_wav
to_wav(Path('/tmp/de1.aiff'), Path('calibration/clips/de1.wav'))
to_wav(Path('/tmp/en1.aiff'), Path('calibration/clips/en1.wav'))
print('clips written')"
cat > calibration/stt_clips.yaml <<'YAML'
# Reference clips for `ember stt-eval`. Synthetic macOS voices bootstrap the set;
# replace with hand-corrected real session audio once German pilots exist — synthetic speech
# is a floor and does not separate models (spec §3.2).
clips:
  - path: clips/de1.wav
    language: de
    reference_text: >-
      Ehrlich gesagt komme ich immer wieder auf dieses Projekt zurück, das ich vor zwei Jahren
      angefangen habe. Niemand hat mich darum gebeten. Ich habe es dreimal neu gebaut, weil sich
      die ersten Versionen falsch angefühlt haben.
  - path: clips/en1.wav
    language: en
    reference_text: >-
      Honestly the thing I keep coming back to is this project I started two years ago.
      Nobody asked me to. I rebuilt it three times because the first versions felt wrong.
YAML
```

- [ ] **Step 5: Wire the CLI subcommand**

In `ember/cli.py`, add the parser after the `calibrate` one:
```python
    v = sub.add_parser("stt-eval", help="measure STT backends against reference clips")
    v.add_argument("--clips", type=Path, default=Path("calibration/stt_clips.yaml"))
    v.add_argument("--lang", default=None, help="restrict to one language")
```
and the branch after the `calibrate` branch:
```python
    if args.cmd == "stt-eval":
        from .stt_eval import DEFAULT_BACKENDS, evaluate, load_clips, render

        clips = [c for c in load_clips(args.clips) if args.lang is None or c.language == args.lang]
        if not clips:
            print(f"no clips in {args.clips}" + (f" for language {args.lang}" if args.lang else ""))
            return 1
        print(render(evaluate(clips, DEFAULT_BACKENDS)))
        return 0
```

- [ ] **Step 6: Run the eval and record the numbers**

Run: `uv run pytest tests/test_stt_eval.py -v && uv run ember stt-eval`
Expected: `3 passed`, then a table of six rows. Paste the table into the spec's **Appendix A** under a new heading `### Re-run <date> — bootstrap clips, all backends`, and commit the spec change with the code.

- [ ] **Step 7: Write the recorded German engine test**

`tests/test_engine_recorded_de.py`:
```python
import pytest

from ember.bank import load_bank
from ember.engine import Engine
from ember.llm import LLM, guard_environment
from ember.session import Turn
from ember.text import contains_verbatim, extract_quote
from tests.conftest import make_session
from tests.recording import RecordingLLM

pytestmark = pytest.mark.api

ANSWER = ("Mein Mitbewohner Karim. Alle in unserem Jahrgang reden davon, etwas zu starten, und er fängt einfach an. "
          "Er wurde zweimal abgelehnt und hatte beide Male eine Woche später eine neue Version. Er wartet nicht "
          "darauf, sich bereit zu fühlen. Ich warte ständig darauf, mich bereit zu fühlen.")


@pytest.fixture(scope="module")
def engine():
    guard_environment()
    return Engine(load_bank("de"), RecordingLLM(inner=LLM()))


def test_german_turn_is_german_and_verbatim(engine):
    s = make_session(now=0.0)
    s.language = "de"
    s.turns.append(Turn(slot=1, kind="spine", question_id=None, question=engine.bank.opener.text,
                        asked_at=0.0, answer=ANSWER, answered_at=40.0))
    n = engine.next(s, now=45.0)
    assert n.kind in ("spine", "probe")
    if n.kind == "probe":
        q = extract_quote(n.text)
        assert q and contains_verbatim(ANSWER, q, min_words=3, max_words=6)
        assert any(w in n.text.lower() for w in ("du", "gesagt", "hast")), n.text
    else:
        assert n.question_id in n.log["offered"] or n.fallback_used
        assert engine.bank.by_id(n.question_id).language == "de"
```

- [ ] **Step 8: Record it, then replay**

Run: `EMBER_RECORD=1 uv run pytest tests/test_engine_recorded_de.py -v`
Expected: `1 passed`, one new file in `tests/fixtures/recorded/`. Then `uv run pytest tests/test_engine_recorded_de.py -v` — passes offline.
If the probe comes back in English, strengthen the German line in `build_system_prompt` (Task 6 Step 4), delete the recording, re-record.

- [ ] **Step 9: Full suite, then commit**

Run: `uv run pytest -q`
Expected: all pass.

```bash
git add ember/stt_eval.py ember/cli.py calibration/ tests/test_stt_eval.py tests/test_engine_recorded_de.py \
        tests/fixtures/recorded/ docs/superpowers/specs/2026-09-11-german-and-stt-design.md
git commit -m "feat: ember stt-eval; recorded German engine turn; measured numbers into the spec" \
  -m "Co-Authored-By: WOZCODE <contact@withwoz.com>" \
  -m "Claude-Session: https://claude.ai/code/session_011xY91ug8K4Ke8JHFsa5ekB"
```

- [ ] **Step 10: Live German session — operator verification**

Run from a plain terminal: `uv run ember serve`, then open `http://127.0.0.1:8765/` in Chrome.

1. The top bar shows `ember` and `EN | DE`. Click **DE** — the three consent lines, the code field label and the button turn German.
2. Enter `DE00`, start, allow the mic. The opener appears in German; the bar is gone.
3. Answer in German for ~30 s. Check the next question is German and the gap is ~5 s.
4. Answer with two words → the German retry message appears.
5. Continue to the close — mirror and take-home are German, and the mirror is something you actually said.
6. `sessions/DE00_*/transcript.json` has `"language": "de"` and umlauts intact (not mojibake).
7. `uv run ember observe sessions/DE00_*` — scores and notes come back in **English**, evidence quotes in **German**.
8. Note the German transcription quality. If it is poor, that is the signal to move `STT_CONFIG["de"]` to `whisper-large-v3-mlx` — record the judgement in the spec either way.

---

## Self-review notes

**Spec coverage.** §2 B1→T1, B2→T3, B3→T4, B4→T5, B5→T6, B6→T2. §3.1 STT structure→T4. §3.2 defaults→T4 Step 8 (`STT_CONFIG`). §3.3 priming→T4 (`prime` arg) + T9 (measured). §3.4 `stt-eval`→T9. §4.1 layout→T3. §4.2 German bank→T7 with the human gate. §4.3 copy→T6. §5 selection→T8. §6 engine/observer language lines→T6 (engine) and T5 (observer). §7 testing→every task, live run in T9 Step 10.

**No placeholders.** Every code step carries the code. The one deliberately deferred item — which German model wins — is a *measurement*, not a placeholder: T9 Step 10 names the decision, the trigger and the one-line change.

**Type consistency.** `load_bank(lang, root)` is used with those argument names in T3, T5, T7, T8. `for_language(lang)` in T4, T8, T9. `create(subject_code, consent_at, now, language)` in T5, T8. `create_app(store, engines, transcribers)` — dicts — in T8's helper, T8 Step 4 and T9's live run. `Transcriber.transcribe(wav_path, prime=None)` in T4 and T8's `answer` route (which passes no prime today; priming is measured in T9 before being switched on).
