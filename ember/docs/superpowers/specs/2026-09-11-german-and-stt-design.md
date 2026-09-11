# ember v2 — German support and STT — design

**Date:** 2026-09-11
**Status:** approved in brainstorming; awaiting spec review
**Owner:** Malek
**Builds on:** `2026-09-11-ember-v1-design.md` (v1 shipped on `main`, PRs #1 and #2)

---

## 1. What this adds

1. A **full German session** — German bank, German UI copy, German STT, German probes and close — selectable before the session starts.
2. A **pluggable STT layer** so the model per language is a config value backed by measurement, not a hard-coded string.
3. Fixes for **six bugs**, five of which block German outright.

Out of scope: Arabic; mid-session language switching; a German rubric (the rubric stays English and scores German transcripts directly); translating existing English sessions.

---

## 2. Bugs fixed here

| # | File | Defect | Fix |
|---|---|---|---|
| **B1** | `text.py:4` | `_WORD = re.compile(r"[a-z0-9']+")` is ASCII-only. `"hätte es schön"` → `['h','tte','es','sch','n']` — 5 tokens for 3 words. Corrupts `word_count`, the probe gate (≥15 words), the probe cap (≤12), the 3–6-word quote bound, the take-home cap (≤20) and `longest_sentence`. A valid three-word German probe quote is rejected as six words. | `re.compile(r"[\w']+", re.UNICODE)`. Regression test asserting `word_count("Ich möchte größer träumen") == 4`. |
| **B2** | `bank.py:12` | `YES_NO_STARTS` is English-only, so a German yes/no question passes validation. | Per-language prefix tuples; the validator picks by the bank's language. German set: `hast/hat/hattest/bist/ist/war/warst/kannst/kann/könntest/willst/wirst/würdest/würdest du/möchtest/hältst/glaubst/denkst/fühlst/gibt es/bereust`. |
| **B3** | `stt.py:18,22` | `language="en"` hard-coded in `warm()` and `transcribe()`. | Language is constructor state on the transcriber; the server holds one per language. |
| **B4** | `session.py`, `store.py` | No `language` field anywhere — nothing records which language a session ran in, and the observer cannot be told. | `Session.language: str = "en"`; written to `meta.json`, `session.json`, `transcript.json`; surfaced in `observer.json` and `graph/data.js`. |
| **B5** | `subject.html`, `server.py:77` | UI copy hard-coded English (consent, hold-space hint, retry message, closing line). | A `COPY` dict keyed by language, served to the page; the retry message comes from the same source. |
| **B6** | `observer.py:139` | `skipped = (not cov[cid]) or (cid in declined_raw)` re-derives what `declined` already contains. A third future reason to decline would desync them, letting a construct be listed as `declined` while carrying `signal: high` — breaking the §6 invariant the tests assert. | `skipped = cid in declined`. Test asserting every id in `declined` has `signal == "low"`. |

Cleanup findings B7–B12 (duplicated UTC-timestamp expression, the observer re-implementing the engine's transcript rendering, the nine-construct tuple copied across five test files, the `observer.json`/transcript fixture shapes hand-built three and five times, `test_observer_recorded.py` hard-coding `120.0`) are **not in this spec** — they are a separate cleanup pass, so a feature branch stays reviewable. The multi-agent review that produced them completed only one of eight angles before hitting a session rate limit; **the bug scan is incomplete and is to be re-run**, and anything it finds is triaged then, not folded in here.

---

## 3. STT layer

### 3.1 Structure

```python
class Transcriber(Protocol):
    language: str
    def warm(self) -> float: ...
    def transcribe(self, wav_path: Path) -> str: ...

class WhisperTranscriber:   # mlx-whisper; language passed through; primes with initial_prompt
class ParakeetTranscriber:  # parakeet-mlx; auto-detects language; output passed through clean_disfluencies()

STT_CONFIG: dict[str, tuple[str, str]] = {
    "en": ("whisper", "mlx-community/whisper-large-v3-turbo"),
    "de": ("whisper", "mlx-community/whisper-large-v3-turbo"),
}
def for_language(lang: str) -> Transcriber
```

### 3.2 Why whisper is the default for both

Measured 2026-09-11 — synthetic macOS TTS, ~20 s clips (a floor, not real speech):

| engine | de WER | de time | en WER | en time |
|---|---|---|---|---|
| whisper turbo | 0.0 % | 1.76 s | 1.7 % | 1.60 s |
| whisper large-v3 | 0.0 % | 5.78 s | 1.7 % | 8.01 s |
| Parakeet TDT v3 | 0.0 % | 0.64 s | 3.4 % | 0.54 s |

On the **seven real S00 recordings** (human speech, English): whisper 13.6 s total vs Parakeet 7.2 s — Parakeet is **1.9× faster**, and every divergence between them was a disfluency. Parakeet transcribes `"uh a person who's alone… I don't I don't I'm not afraid"`; whisper writes the same answer without the fillers.

**Decision: transcripts are clean.** Whisper produces clean text natively and contextually; making Parakeet clean requires a hand-maintained filler list per language doing worse what whisper does for free. Parakeet's speed edge is real but buys ~1 s on a ~5 s turn gap — not worth the regression in transcript quality. Parakeet stays implemented behind the protocol so `ember stt-eval` keeps comparing it, and `clean_disfluencies()` exists for that path; it becomes a default only if an eval on real German speech shows whisper failing.

**German model is provisional.** turbo scored 0 % on synthetic German, but synthetic German is easy and turbo is a pruned decoder known to degrade more outside English. No real German speech exists to test against yet. German therefore ships on turbo, and **the first German pilot's recordings become the eval set that settles it** — if WER is poor, `STT_CONFIG["de"]` moves to `whisper-large-v3-mlx` (one config line, ~4 s slower per turn) or to Parakeet.

### 3.3 The accuracy improvement

Whisper accepts an `initial_prompt` that primes its decoder. ember has an obvious primer available and unused: **the question just asked**. Priming with it biases transcription toward the vocabulary the answer is likely to contain — names, domain words, the question's own nouns. `WhisperTranscriber.transcribe(wav, prime: str | None = None)`; the server passes `session.pending.question`. `ember stt-eval` reports WER with and without priming so the default is measured, not assumed.

### 3.4 `ember stt-eval`

`ember stt-eval [--clips calibration/stt_clips.yaml] [--lang de]` — transcribes reference clips with every configured backend and prints WER, latency and real-time factor. Clips are `{path, language, reference_text}` entries; generated synthetic clips for bootstrapping, real session audio once hand-corrected. Output table goes into this spec's appendix on each run.

---

## 4. German content

### 4.1 Layout

```
ember/bank/
  en/{opener,questions,rubric}.yaml     ← moved from bank/*.yaml, unchanged content
  de/{opener,questions}.yaml            ← new
  rubric.yaml                            ← shared, English, operator-facing
```

`load_bank(lang="en")` reads `bank/<lang>/`. The rubric is loaded once from `bank/rubric.yaml` regardless of language — it is scored by the observer and read by the operator, both of whom work in English.

### 4.2 The German bank is crafted, not translated

Same ids, same slots, same `targets`, same `prerequisites`, same threat ladder — so branching, guards, coverage and the observer are unchanged. Different idiom. A literal translation of "Money's solved… what are you doing at two in the afternoon?" is not the German question; the German question has to land the same way for a German speaker.

**Register: `du` throughout** — matches the English bank's casual second person and the cohort of young builders. A `Sie` bank reads like an HR interview and kills the escalation the arc depends on.

The bank ships as a draft I write and **Malek reviews line by line before any session runs**, the same hard gate the English bank had (v1 spec §5.1).

### 4.3 UI copy

```python
COPY = {"en": {...}, "de": {...}}   # consent lines ×3, code label, start button,
                                     # hold-space hint, recording hint, waiting, retry, closing line
```
Served by `GET /api/copy/{lang}`; the page renders from it. The German consent lines say the same three things as the English ones, in German.

---

## 5. Language selection

**Per session, fixed at start.** It selects bank, transcriber and copy — all three are bound into the session's prompt cache and question ids, so mid-session switching is incoherent and is not offered.

- **Subject page:** a slim top bar — `ember` on the left, `EN | DE` on the right — visible only on the consent screen. Flipping it re-fetches copy and re-renders in place. The bar is removed once the session starts.
- **Operator override:** `GET /?lang=de` preselects, and the operator page shows the running session's language.
- **Persistence:** `POST /api/session` takes `{subject_code, language}`; stored on `Session.language` and in `meta.json`, `session.json`, `transcript.json`; carried into `observer.json` and `graph/data.js`, and shown on the subject view.

## 6. Engine and observer

Both receive one line naming the language. Engine: *"The subject speaks German. Write probes and the close in German, using du."* Observer: *"The transcript is in German. Score against the English rubric; quote evidence verbatim in German."* Scores, anchors, notes and flags stay English — the operator reads them.

Every existing validator keeps working once B1 lands: verbatim matching, the 3–6-word quote bound and the word caps are all Unicode-correct after the tokeniser fix.

## 7. Testing

- **Unit:** B1 regression on umlauts and ß; German yes/no validator; `for_language` dispatch; `clean_disfluencies`; copy completeness (every key present in both languages); language round-trips through session, store and export; B6 invariant (every `declined` id has `signal: "low"`).
- **Bank:** the German bank loads and satisfies every structural rule the English one does — 21 candidates, one default per slot, slot-2 prerequisites empty, threat monotonicity satisfiable, no yes/no questions.
- **Recorded API:** one German engine turn and one German observer scoring, against synthetic German transcripts, recorded and replayed offline — asserting probes are German and quote verbatim.
- **STT:** `stt-eval` runs on committed synthetic clips in CI-free form; the numbers land in the spec appendix.
- **Live:** one German end-to-end session by the operator before the German bank is trusted.

## 8. Decisions log

| # | Decision | Choice |
|---|---|---|
| 1 | Depth of German | Full session: bank, UI, STT, probes, close |
| 2 | Register | `du` |
| 3 | Rubric language | English, shared |
| 4 | STT architecture | Pluggable backends, per-language config, `ember stt-eval` |
| 5 | Disfluencies | Stripped — clean transcripts |
| 6 | Default engine | whisper turbo both languages; German provisional pending real speech |
| 7 | Parakeet | Implemented, eval-only, not a default |
| 8 | Accuracy lever | `initial_prompt` primed with the question just asked, measured |
| 9 | Toggle placement | Subject-page top bar **and** `?lang=` / operator override |
| 10 | Switching mid-session | Not supported |
| 11 | Bug scope | B1–B6 here; B7–B12 a separate cleanup pass; full scan to be re-run |

## Appendix A — STT measurements, 2026-09-11

Synthetic macOS TTS, `say` voices (`Anna` for German), 16 kHz mono, ~20 s clips. WER against the known reference text.

| engine | lang | WER | time | RTF |
|---|---|---|---|---|
| whisper-large-v3-turbo | de | 0.0 % | 1.76 s | 14× |
| whisper-large-v3-turbo | en | 1.7 % | 1.60 s | 11× |
| whisper-large-v3 | de | 0.0 % | 5.78 s | 4× |
| whisper-large-v3 | en | 1.7 % | 8.01 s | 2× |
| parakeet-tdt-0.6b-v3 | de | 0.0 % | 0.64 s | 37× |
| parakeet-tdt-0.6b-v3 | en | 3.4 % | 0.54 s | 33× |

Real human speech — the seven S00 recordings, English, 16–47 s each:

| | whisper turbo | Parakeet v3 |
|---|---|---|
| total transcription | 13.6 s | 7.2 s (1.9× faster) |
| agreement (token ratio) | — | 70–94 %, every divergence a disfluency |

No real German speech has been tested. The first German pilot supplies it.

### Re-run 2026-09-12 — `ember stt-eval`, bootstrap clips, all backends

| backend | lang | WER | time | RTF |
|---|---|---|---|---|
| whisper turbo | de | 0.0 % | 1.25 s | 11× |
| whisper turbo | en | 3.2 % | 1.15 s | 9× |
| whisper large-v3 | de | 0.0 % | 2.67 s | 5× |
| whisper large-v3 | en | 12.9 % | 2.55 s | 4× |
| parakeet v3 | de | **0.0 %** | **0.40 s** | 34× |
| parakeet v3 | en | **0.0 %** | **0.31 s** | 32× |

**Read these numbers with the transcripts, not alone.**

- **large-v3's 12.9 % English is a formatting artifact.** It writes "2 years", "3 times" where the reference
  says "two", "three". Word-level WER counts those as errors; a listener would not.
- **turbo's 3.2 % is a real hallucination.** It transcribed "Nobody asked me to" as *"Nobody asked me to **book**"* —
  and produced the identical "book" insertion on a separate recording of the same sentence earlier the same day.
  Reproducible, not noise.
- **Parakeet was exact on both clips.** Combined with its 1.9× speed advantage on the real S00 recordings, the only
  thing keeping it out of the defaults is the disfluency decision (§3.2) — and `clean_disfluencies()` now exists
  and is tested. **This is an open question for the first German pilot to settle**, not a closed one.
- Synthetic clips remain a floor. Nothing here separates the models on German, where all three scored 0 %.

### Priming (§3.3) — no effect measured yet

`initial_prompt` was wired and exercised on the German clip; the primed and unprimed transcripts were identical
because the clip already transcribed perfectly. The lever is in place and unmeasured. It needs a clip the model
gets *wrong* — real speech with a proper noun or a domain word — which the first German pilot supplies.
The server does not pass a prime today; switching it on is one argument at the `transcriber.transcribe` call site.
