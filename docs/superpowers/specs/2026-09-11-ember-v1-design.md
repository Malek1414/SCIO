# ember — v1 design

**Date:** 2026-09-11
**Status:** approved in brainstorming; awaiting spec review
**Owner:** Malek

---

## 1. What ember is

A 5–8 minute, voice-answered, screen-asked psychological interview that gets a person to say something true about themselves that they had not put into words before — and, separately, scores them on nine traits for a cohort graph the operator reads.

Two products from one session, kept apart by a hard wall:

- **For the subject:** a maieutic experience. No verdict is ever delivered. The value is what they hear themselves say, and one question they take home.
- **For the operator:** a diagnostic score per construct, with evidence, on a cohort map.

Primary use is self-discovery (subject is the customer). Secondary use is co-founder / partner vetting (operator uses the graph). Same engine, same session; only the output surface differs.

### 1.1 Why this shape

The brief asked for a "mentalist" — indirect questions that reverse-engineer what drives someone without them noticing what is being measured. The validated science of exactly that mechanism is **Motivational Interviewing** (Miller & Rollnick): self-generated statements predict change; practitioner-supplied insight predicts resistance. People defend against being told who they are. They do not defend against what they just heard themselves say.

So: the mentalist is the **aesthetic** (confidence, indirection, the reveal). MI is the **mechanism** (reflection, change talk, discrepancy). Cold reading's elicitation techniques are borrowed; its illusion techniques are excluded (§4).

### 1.2 v1 constraints (decided)

| Constraint | Value |
|---|---|
| Session length | 5–8 min, hard close at 6:30 elapsed |
| Sessions per subject | One. No longitudinal state in v1. |
| Cohort | ~40 people, young builders / students, in person |
| Modality | Question as **text on screen** → subject **speaks** → local STT → engine → next question. **No TTS.** |
| Language | English only |
| Operator | Malek, in the room, **silent** — runs the laptop, cannot inject or skip |
| Clusters in v1 | Fire (anchor), Compass, Ground. **Engine cluster out** (ceiling, back-against-the-wall effort, interest-vs-competence gap). |
| Close | Mirror (verbatim) + one take-home question |
| Consent | Subjects know it is a psychological interview and that it is recorded and scored |
| Stack | Python 3.12 via `uv` |
| LLM backend | **Claude Agent SDK** (`claude-agent-sdk`) on the operator's Claude subscription, authenticated by the existing Claude Code login. No API key, no API-key code path. |
| Subscription | Max 5x → Opus 5 for engine and observer, Sonnet 5 as `fallback_model`. Sessions spread over 2–3 days to stay clear of 5-hour usage windows. |

---

## 2. Architecture

```
                 ┌──────────────────────────┐
  subject ◄─────►│     MAIEUTIC ENGINE      │  picks the next question
  (screen/voice) │  conversational inference │  on its own logic only
                 └────────────┬─────────────┘
                              │ writes
                              ▼
                       ┌─────────────┐
                       │  TRANSCRIPT │   single source of truth
                       └──────┬──────┘
                              │ reads Q/A ONLY — never candidates, picks, or reasons
                              ▼
                 ┌──────────────────────────┐
                 │   DIAGNOSTIC OBSERVER    │  scores 9 constructs → graph
                 │      trait inference      │  ZERO feedback path
                 └──────────────────────────┘
```

**The wall.** The observer is a pure function of the Q/A transcript. It runs after the session, never during. It never sees the engine's candidate lists, choices, surfaced tags, or reasons. Nothing the observer produces is ever an input to the engine. This is enforced in data (the observer is handed a transcript file that contains only Q/A pairs and timestamps) and in code (separate modules, no shared state).

The engine *does* infer — but conversationally: what thread to pull, what discrepancy to surface, what phrase to reflect. It never asks "what is this person's score on F2."

---

## 3. Construct model

Nine constructs, three clusters. Each is scored 1–7 by the observer with a **signal** rating and 1–3 verbatim evidence quotes.

### FIRE — the itch

| ID | Construct | 1 looks like | 7 looks like |
|---|---|---|---|
| **F1** | Driver specificity | "Make an impact," "be successful." Cannot name a thing. | A specific itch described in sensory or mechanical detail; they can say what it feels like when it's working. |
| **F2** | Trade-off evidence | Only hypothetical sacrifice ("I would give up…"). | Names a real cost already paid — time, money, a relationship, status — and does not perform regret about it. |
| **F3** | Mediocrity tolerance *(inverse-scored)* | Describes settled people with warmth, ease, or envy. | Describes settled people with visible discomfort, restlessness, or something close to fear. |

### COMPASS — what they believe and fear

| ID | Construct | 1 looks like | 7 looks like |
|---|---|---|---|
| **C1** | Values–reality gap *(scored on the gap, not the code)* | Stated values and the pressure decision contradict, and they do not notice. | Stated values and the pressure decision match, or they name the gap themselves without prompting. |
| **C2** | Transcendence frame | Nothing larger than self is oriented to; "biggest thing I'm part of" gets a job or a friend group. | A specific frame that exceeds the self — religious, civilisational, scientific, familial-across-generations — and they can say how it changes a decision. |
| **C3** | Fear specificity | Cannot name a fear, or names a generic outcome ("failing"). | Names a *self* they fear becoming, specifically. |

### GROUND — who they are alone, with others, and after the storm

| ID | Construct | 1 looks like | 7 looks like |
|---|---|---|---|
| **G1** | Solitude stance | Has never considered it; the empty-room question produces filler activity. | Knows what they do at minute forty and why; or names precisely that they don't and that it bothers them. |
| **G2** | Disruption processed *(scored on processing, not severity)* | Names an event with no account of what changed after. | Names what they built, decided, or dropped as a result, in their own causal language. |
| **G3** | Relational orientation | People are audience (validation) or fuel (extraction) and they cannot see it. | People are anchors; or they name the audience/fuel pattern in themselves. |

Full three-point anchors (1 / 4 / 7, with a short exemplar quote each) are authored in implementation as `ember/bank/rubric.yaml`, reviewed by Malek before the pilots. The table above is the definition; the rubric file is the calibration instrument.

**Language note.** C2 is deliberately shaped by Christopher Langan's CTMU argument — that reality's deducible properties match what religions call God — because it makes the construct *structural*: the question is whether the subject has any frame that exceeds themselves, not whether they are religious. The word "God" never appears in a spine question.

**Signal thresholds.**
- `high` — ≥ 3 evidence quotes from ≥ 2 different answers
- `med` — 2 quotes
- `low` — < 2 quotes, or the construct's question was skipped or declined

---

## 4. Indirection technique library

### 4.1 From cold reading — the split

Rowland's *Full Facts Book of Cold Reading* divides cleanly.

**OUT — illusion family.** Barnum statements, Rainbow Ruse, Jacques statement, Good Chance Guess, Fuzzy Fact. These exist to *sound* like you already know. Two failure modes: a subject who catches one stops trusting the screen; and a Barnum statement fed to the observer poisons the score. **The engine never guesses out loud.**

**IN — elicitation family.**
- **Forking** — offer two readings; the correction is the data. *"That sounds like it was either a relief or a loss."*
- **Diverted question** — never explain what a question is for; redirect.

### 4.2 From Motivational Interviewing

- **Reflection over question** — a probe is a statement, not a question. *"You said 'I couldn't stop.'"* Then nothing. They fill the silence.
- **Discrepancy surfacing** — *"Earlier, X. Just now, Y."* Laid side by side, never accusatory.
- **Change-talk detection** — the engine listens for desire / ability / reason / need language and pulls on it.
- **Open only** — no spine question is answerable with yes/no. Enforced by review.

### 4.3 Framings — asking about X while appearing to ask about Y

| Framing | Surface question (example) | Targets |
|---|---|---|
| Third-person projection | *Someone you know who's clearly going to make it — what do they do differently?* | F1, F3 |
| Counterfactual removal | *Money's solved. What are you doing Tuesday?* | F1 |
| Envy locator | *Whose life makes you jealous in a way you'd rather not admit?* | F1 |
| Cost already paid | *Something you gave up that people around you didn't get.* | F2 |
| Settled-person read | *Someone you know who settled. How is it, being around them?* | F3 |
| Pressure decision | *Last time you had to choose fast and it cost something.* | C1 |
| Scale-of-things | *What's the biggest thing you're a small part of?* | C2 |
| Fear-of-self | *What kind of person are you afraid of turning into?* | C3 |
| Empty room | *Phone's dead, nobody's coming for six hours. Minute forty — what's happening?* | G1 |
| Aftermath, not event | *Something knocked you sideways. What did you build after?* | G2 |
| People-as | *When you're at your best, what are the people closest to you doing?* | G3 |

Idiom for the pool: second person, casual, no business jargon, assumes ambition is on the table. Questions are written for a 22-year-old who builds things.

### 4.4 On The Mentalist (TV)

Not a technique source. Patrick Jane's on-screen reads are dramatised cold reading where the writers already know the answer. Used only as a **tone reference for the close** — how a mirror lands when delivered flat, confident, without hedging. No clips are needed; episode summaries from the fan wiki go in the corpus for tone only.

---

## 5. Session arc and engine logic

### 5.1 Arc

Escalation is the mechanism (Aron et al. 1997: closeness between strangers came from escalating disclosure across three sets, not from depth at the start). Seven spine slots climb in threat.

```
threat
  ▲
7 │                                  ● Q4 Fire·deep
6 │                     ● Q3                  ● Q5 Compass   ● Q6 Ground
5 │           ● Q2                                                ● Q7 flex
4 │
3 │ ● Q1 Fire·opener
  └──────────────────────────────────────────────────────────────► time
    0:00                                                 ~6:30 → CLOSE
```

| Slot | Cluster | Selection |
|---|---|---|
| Q1 | Fire | Fixed opener. Same for everyone. No LLM call. |
| Q2–Q4 | Fire | 3–4 hand-written candidates per slot. Engine picks by surfaced tags. Q4 is the deep one. |
| Q5 | Compass | 4–5 candidates covering C1–C3. Pre-filtered by what Fire surfaced. |
| Q6 | Ground | 4–5 candidates covering G1–G3. Pre-filtered by what Fire surfaced. |
| Q7 | flex | An unused Compass/Ground candidate. Only if elapsed < 5:45 after Q6. |
| Probes | — | Max 2 per session, only while elapsed < 4:00, only after an answer of ≥ 15 words. |
| Close | — | Always. Mirror + take-home. |

Bank size: 1 opener + ~10 Fire + ~5 Compass + ~5 Ground ≈ **21 spine questions**, each with a gentler rephrase. Authored in implementation as `ember/bank/questions.yaml`, every line reviewed by Malek before the pilots.

### 5.2 Candidate schema

```yaml
- id: F2-c
  slot: 3                    # 1–7
  cluster: fire              # fire | compass | ground
  targets: [F2]              # construct ids
  threat: 5                  # 1–7; within Fire (slots 2–4) must be ≥ previous Fire pick
  framing: cost-already-paid
  prerequisites: []          # tags that must be in session.surfaced_tags; empty = always eligible.
                             # Slot-2 candidates must have none: tags are emitted with the slot-2 pick, so nothing is known yet.
  default: false             # exactly one default per slot; used on API failure
  text: "…"
  rephrase: "…"              # shown after 25 s silence
```

### 5.3 Surfaced tags

A controlled vocabulary the engine emits with every turn, accumulated in session state, used *only* for deterministic prerequisite filtering: `named-project`, `family`, `money`, `health`, `loss`, `faith`, `relationship`, `solitude`, `quit`, `moved`, `failure`, `competition`. Tags are engine-internal. The observer never sees them.

### 5.4 Engine turn contract

**Input:** transcript so far (Q/A + timestamps), slot number, elapsed seconds, the slot's candidate list *after* prerequisite filtering, probe budget remaining, probe window open (bool).

**Output — one JSON object, schema-enforced:**

```json
{
  "action": "pick" | "probe" | "close",
  "candidate_id": "F2-c",
  "probe_text": "You said 'I couldn't stop.'",
  "surfaced_tags": ["named-project", "quit"],
  "reason": "one line, logged, never shown"
}
```

Validation before the screen updates: `candidate_id` must be in the offered list; `probe_text` must contain a **verbatim 3–6-consecutive-word substring** of the last answer (case-insensitive, punctuation-stripped) and be ≤ 12 words total; `action: probe` rejected if budget is 0 or window is closed. A validation failure falls back to the slot's default candidate — no retry, no second LLM call.

### 5.5 Deterministic guards (no LLM involved)

| Guard | Rule |
|---|---|
| Opener | Q1 is fixed; no engine call. |
| Prerequisites | Hard filter before the LLM sees candidates. |
| Threat monotonic (Fire only) | Within slots 2–4, a candidate with `threat` below the previous Fire pick is filtered out. Compass and Ground candidates are not constrained by the Fire pick. |
| Probe gate | Only if last answer ≥ 15 words **and** elapsed < 4:00 **and** budget > 0. |
| Fire guard | Elapsed > **4:30** and slot ≤ 4 → skip remaining Fire, go to Q5. Guarantees Compass and Ground ~1 min each. |
| Q7 gate | Only if elapsed < 5:45 after Q6 completes. |
| Hard close | Elapsed ≥ **6:30** → close after the current answer, whatever the slot. |

### 5.6 Close contract

Separate call, its own schema:

```json
{ "mirror": "verbatim quote, ≥ 5 words, from any answer",
  "take_home": "one question, ≤ 20 words, must reference the mirror" }
```

Validation: mirror must be a verbatim substring of the transcript (same matching rule as probes). Failure → the engine selects the longest single sentence from any Fire-slot answer as the mirror, and uses a slot-independent fallback take-home from the bank. The screen holds the close until the operator ends the session.

### 5.7 Why the LLM chooses spine questions but writes probes and the close

Every question carrying a construct target was reviewed by a human before it shipped. The LLM's freedom is confined to reflecting the subject's own words back — which is exactly the thing that cannot be pre-written.

---

## 6. Observer

**Input:** `transcript.json` — Q/A pairs with timestamps. Nothing else.
**When:** after the session ends. `ember observe <session_dir>`. Re-runnable; every run records `rubric_version`.
**Model:** Claude Opus 5, adaptive thinking, effort `high`, structured output.

**Output — `observer.json`:**

```json
{
  "subject_id": "S17",
  "session_id": "2026-09-20T14-05-11",
  "scored_at": "…",
  "rubric_version": "1.0.0",
  "constructs": {
    "F1": { "score": 6, "signal": "high",
            "evidence": ["I've rebuilt it three times and I'm not done", "…"],
            "note": "one line" },
    "…": {}
  },
  "declined": ["G2"],
  "flags": ["read G2 by hand — subject paused 30 s then changed topic"]
}
```

**Rules the observer must obey:**
- Score against the three anchors in `rubric.yaml`, never against a general impression.
- Every score ≥ 2 quotes or `signal: low`. No exceptions.
- A declined or skipped construct is `signal: low` **and** listed in `declined`.
- Evidence quotes must be verbatim substrings of the transcript (validated).
- `flags` is for anything the operator should read manually. It is not a score.

**Calibration (v1 validation):** Malek, Claude, and the observer each score the five pilot transcripts by hand. Disagreements of ≥ 2 points on any construct tighten that construct's anchors. Repeat until the observer is within 1 point of the human median on ≥ 80 % of construct scores across the five.

---

## 7. Graph

One static HTML page, local, reading `graph/data.json` exported from SQLite.

**Cohort view.** Scatter of all subjects. X and Y selectable from the nine constructs; default **F1 × F2** — *do they know what they want* × *have they paid for it*. Dot size = signal (mean over the two plotted constructs; thin evidence is visibly small). Colour = a third construct, default C2. Hover shows subject id; click opens the subject view.

**Subject view.** Nine-spoke radar (1–7). Below: evidence quotes per construct, `declined` and `flags`, then the mirror and take-home from their close. This is where a person is actually read.

The graph is **operator-facing only**. A subject sees it only if they ask after the session.

---

## 8. Pipeline

```
browser (localhost)                   python backend (FastAPI)
┌────────────────────┐   WAV   ┌─────────────────────────────────────┐
│  question text     │────────▶│ /answer                             │
│  [hold SPACE       │         │  ├─ mlx_whisper · in-process,       │
│   to speak]        │         │  │   model held in memory           │
│  "…" while waiting │◀────────│  ├─ engine.next(transcript)         │
│                    │ next Q  │  │   Opus 5 · structured output     │
└────────────────────┘         │  │   effort low · cached bank       │
                               │  └─ session store · folder + SQLite │
                               └─────────────────────────────────────┘
                                             │ after session
                                             ▼
                               ember observe <session_dir>
                               Opus 5 · structured output · effort high
                                             │
                                             ▼
                               graph/  static HTML over data.json
```

**Screen.** One page. Large type, one question. Hold space (or click-and-hold) to record; release to submit. A quiet "…" while waiting. Subject sees no transcript and no timer. Operator's view (second browser tab) shows elapsed time, slot, and the engine's last action.

**STT.** `mlx_whisper`, model `mlx-community/whisper-large-v3-turbo`, loaded once at server start and held in memory. Measured 2026-09-11: 41 s of speech → 5.2 s via the CLI including model load per call; in-process expected ~2–3 s. Confirm in implementation and record the number.

**Engine.** Claude Opus 5 via the **Claude Agent SDK** (`claude-agent-sdk`), authenticated by the operator's existing Claude Code login — no API key. Each call is a one-shot `query()` with `system_prompt` (plain string, replaces the Claude Code preset), `model="opus"`, `fallback_model="sonnet"`, `thinking={"type": "adaptive"}`, `output_format={"type": "json_schema", …}` against the §5.4 schema, `tools=[]`, `max_turns=2`, and **mandatory isolation**: `setting_sources=[]`, `mcp_servers={}`, `strict_mcp_config=True`, so the child process loads none of the operator's skills, memory, or MCP tools (measured 2026-09-11: without isolation a trivial call consumed ~80K tokens; with it, 956). Effort `low` for the per-turn pick, `high` for the close. The system prompt (bank + rules) is a stable prefix and is served from Anthropic's prompt cache across calls (1-hour TTL, observed across separate processes). The parsed result is `ResultMessage.structured_output`; `ResultMessage.usage` is logged per turn. The ember process **refuses to start if `ANTHROPIC_API_KEY` is set** (Claude Code would silently bill the API instead of the subscription) and strips inherited `CLAUDE*` environment variables so it behaves identically whether launched from a plain terminal or from inside a Claude Code session.

**Observer.** Same backend and isolation, Opus 5, effort `high`, `output_format` against §6. `ember observe <session_dir>`. Re-runnable.

**Storage.** One folder per session under `sessions/` (git-ignored):

```
sessions/S17_2026-09-20T14-05-11/
  meta.json          subject code, consent timestamp, rubric version, operator notes
  audio/q1.wav …     raw recordings, one per answer
  transcript.json    Q/A + timestamps — the ONLY file the observer reads
  engine_log.json    candidates offered, pick, reason, tags, validation results, timings
  observer.json      written by ember observe
```

`ember.sqlite` indexes sessions for the graph; `ember export` writes `graph/data.json`.

**Latency per turn.** STT ~2–3 s + engine **2.6–2.9 s measured** (≈1.1 s process spawn + ≈1.6 s model) → **~5–6 s** from release to next question. v1 accepts this behind the "…" indicator. v1.1 options: chunked STT during speech; a persistent `ClaudeSDKClient` to remove the spawn.

**Cost.** Draws on the operator's Max 5x subscription, not an API bill. API-equivalent as reported by the SDK: $0.016 for a first call, $0.007 cached. With a ~5K-token bank, **≈ $0.10 API-equivalent per session** — negligible against subscription limits. Spread the 40 sessions over two or three days.

**Layout.**

```
ember/
  ember/
    bank/questions.yaml    spine questions + rephrases
    bank/rubric.yaml       three anchors per construct
    bank/opener.yaml       Q1 + fallback take-home
    engine.py              turn contract, guards, validation
    observer.py            pure function transcript → observer.json
    stt.py                 mlx_whisper wrapper, model held in memory
    store.py               session folders + SQLite index
    server.py              FastAPI: /session, /answer, /close, operator view
    static/                subject screen + operator screen
  graph/                   static HTML + export script
  sessions/                git-ignored
  tests/
  docs/superpowers/specs/
```

---

## 9. Error handling

| Situation | Behaviour |
|---|---|
| STT returns empty or < 5 words | Screen: "Didn't catch that — once more?" Same slot, not counted. Max 2 retries, then skip; observer will set `signal: low`. |
| Silent > 25 s after question shown | Pre-written gentler rephrase appears. Same slot. |
| Subject declines to answer | Engine moves on. Observer records `declined`. Declining is data. |
| Probe quotes a mis-transcription | Probes quote 3–6 words max and are framed "you said," never "you claimed." A correction is logged as the answer. |
| API error / timeout | 15 s timeout per attempt, one retry, then the slot's `default` candidate — deterministic, no LLM. Session continues; turn flagged in `engine_log`. |
| Model refusal or Opus unavailable | `fallback_model="sonnet"` retries on Sonnet inside the same call. If that also fails → slot default candidate. Logged. |
| Engine output fails validation | Slot default candidate. No second call. Logged. |
| Time guards | Fire guard 4:30 · probe window closes 4:00 · Q7 gate 5:45 · hard close 6:30. |
| Browser / laptop crash | Session folder written per turn. Reopen the subject page as `/?sid=<session id>` — it resumes at the pending question. |

---

## 10. Testing

**Unit — deterministic, no API.** Prerequisite filtering, threat monotonicity, probe gate, Fire guard, Q7 gate, hard close, min-words rule, verbatim-substring matcher, fallback-to-default, observer schema validation, session-store round-trip, resume-after-crash.

**Engine behaviour — recorded API.** ~10 hand-written transcripts: vague answerer, decliner, 90-second talker, five-word answerer, subject who contradicts themselves, subject who mentions family in Q1. Assert: pick is in the offered list, probes contain a verbatim substring, tags are from the vocabulary, close passes validation. Responses recorded so the suite reruns without cost.

**Craft — humans.** Five pilot sessions before the 40. Two measures:
1. Immediately after: *"Did you say anything you hadn't put into words before?"* — yes/no.
2. 24 h later, by message: *"Still thinking about the last question?"* — yes/no.

Target: ≥ 3/5 on both before the 40 begin. The five transcripts also drive observer calibration (§6).

---

## 11. Consent and data

Three lines on screen before Q1; tap to accept; timestamp stored in `meta.json`:

1. This is a ~7-minute psychological interview. It's recorded and transcribed.
2. Transcript text goes to Anthropic, through Malek's Claude subscription, to pick questions and score. Audio stays on this laptop.
3. Your session goes into a graph Malek reads. Ask him and he'll delete it.

No names collected. Subject code `S01`–`S40` assigned by the operator. The SQLite index carries no names by default.

---

## 12. Out of scope for v1

TTS · Arabic / German · longitudinal sessions & callbacks · Engine cluster · subject-facing report · remote sessions · operator injection or skip · chunked STT · subject-facing transcript · speaker diarisation.

Nothing in the architecture blocks any of them. Longitudinal is the most valuable next step: it turns "do they only lock in under pressure" from self-report into a said-vs-did measurement.

---

## 13. Build order

1. **Author** `rubric.yaml`, `questions.yaml`, `opener.yaml` — no code. Malek reviews every line.
2. **Store + engine** with unit tests and the recorded-API suite.
3. **STT + screen** — the live loop, measured latency.
4. **Observer** + calibration harness.
5. **Graph** + export.
6. **Five pilots** → calibrate → fix craft.
7. **The 40.**

---

## 14. Decisions log

| # | Decision | Choice |
|---|---|---|
| 1 | Who is in the chair | Self-discovery primary, co-founder vetting secondary |
| 2 | Diagnostic vs maieutic | Maieutic, with a fully decoupled diagnostic observer |
| 3 | Observer → engine feedback | None. Hard wall. |
| 4 | Session format | Single, 5–8 min, ~40 subjects |
| 5 | Clusters | Fire (anchor), Compass, Ground. Engine cluster out. |
| 6 | Modality | Text question on screen, voice answer, STT. No TTS. |
| 7 | Language | English only |
| 8 | Pool | Young builders / students |
| 9 | Close | Mirror + take-home question |
| 10 | Setting | In person, operator silent |
| 11 | Engine architecture | Hybrid: hand-crafted spine + LLM probes (max 2) |
| 12 | Graph | Cohort scatter → per-subject radar; operator-facing |
| 13 | Stack | Python |
| 14 | Project name | ember |
| 15 | The Mentalist clips | Not needed; tone reference only |
| 16 | LLM backend | Claude Agent SDK on the operator's subscription; no API-key path |
| 17 | Subscription plan | Max 5x → Opus 5, Sonnet fallback, sessions spread over 2–3 days |

---

## Appendix A — Research inputs

**Christopher Langan / CTMU.** Claimed IQ 190–210. Argues reality is a self-configuring, self-processing language whose deducible properties match the God of major religions; touches simulation hypothesis. Used here only to shape C2 as a structural construct. Sources: [LADbible — Langan on God](https://www.ladbible.com/news/science/worlds-smartest-man-answers-if-god-exists-855495-20241217) · [All That's Interesting](https://allthatsinteresting.com/christopher-langan).

**Motivational Interviewing.** Miller & Rollnick. Very brief sessions (< 20 min) show real effects on initial change; sustained behaviour change needs more sessions — which is fine, ember's goal is the moment of articulation, not treatment. Reflection > question; self-generated change talk predicts change. Sources: [MI research reviews 2017 (PDF)](https://www.motivationalinterviewing.org/sites/default/files/mi_research_reviews_2017.pdf) · [BJPsych Advances — MI: living up to its promise?](https://www.cambridge.org/core/journals/bjpsych-advances/article/motivational-interviewing-living-up-to-its-promise/301E29C38EC9D433802E164440E09A23) · [NCBI — Motivational counseling and brief intervention](https://www.ncbi.nlm.nih.gov/books/NBK571067/).

**Aron et al. 1997 — "The Experimental Generation of Interpersonal Closeness."** 36 questions in three escalating sets over 45 min produced closeness between strangers exceeding many long friendships. The escalation principle is the basis of the seven-slot arc. Sources: [paper (PSPB)](https://journals.sagepub.com/doi/10.1177/0146167297234003) · [Greater Good — the 36 questions](https://ggia.berkeley.edu/practice/36_questions_for_increasing_closeness).

**Ian Rowland — *The Full Facts Book of Cold Reading*.** Source of the elicitation/illusion split in §4. [Goodreads](https://www.goodreads.com/book/show/3327264-the-full-facts-book-of-cold-reading).

**The Mentalist (TV).** Tone reference for the close only. [Patrick Jane — fan wiki](https://thementalist.fandom.com/wiki/Patrick_Jane).

**Video.**
- [Arthur Aron Q&A on the 36 questions](https://www.youtube.com/watch?v=8mGXD2eL1sw) · [the experiment demonstrated](https://www.youtube.com/watch?v=fwDhfkctcos)
- [Derren Brown — what cold reading is](https://www.youtube.com/watch?v=ENS8_3XdRFw) · [on Barnum statements](https://www.youtube.com/watch?v=ffB6Kymbhz4)
- [MI — evoking change talk, demonstration](https://www.youtube.com/watch?v=jXtslk8MmuA) · [reflective listening demo](https://www.youtube.com/watch?v=SZ-IH-V7oJ4)

## Appendix B — STT measurement, 2026-09-11

`mlx_whisper` · `whisper-large-v3-turbo` · Apple Silicon · 40.9 s synthetic speech (macOS `say`), 16 kHz mono WAV.
CLI including model load: **6.95 s cold, 5.15 s warm.** One substitution error in ~140 words. In-process with the model resident is expected to be substantially faster; to be measured in build step 3.
In-process, model resident: **1.14s** for the ~12 s test clip (build step 3, 2026-09-11).

## Appendix C — Agent SDK measurement, 2026-09-11

`claude-agent-sdk 0.2.152` · Opus 5 · effort `low` · adaptive thinking · JSON-schema output · `tools=[]` · one-shot `query()`.

| Configuration | Latency | Prompt tokens | Output tokens | API-equivalent |
|---|---|---|---|---|
| No isolation, launched inside a Claude Code session | 8.3 s cold / 3.5 s warm | ~80K (operator's skills + MCP tools loaded) | ~210 | $0.46 |
| `setting_sources=[]`, `mcp_servers={}`, `strict_mcp_config=True`, `CLAUDE*` env stripped | **2.62 s / 2.85 s** | **956** (cache write, then cache read) | 205–228 | **$0.016 / $0.007** |

Auth resolved from the existing Claude Code login with no configuration. Second call hit the 1-hour prompt cache across a separate process.
