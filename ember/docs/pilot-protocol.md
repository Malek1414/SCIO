# ember — pilot protocol

Five pilot sessions before the cohort of ~40 (spec §10, §6). Everything below is run by the operator.

## Before the first pilot
1. Bank reviewed: every line of `ember/bank/questions.yaml`, `opener.yaml`, `rubric.yaml` read and approved.
2. `uv run pytest -q` green.
3. Room: quiet, subject alone with the laptop and a decent mic; operator seated behind, silent.
4. Chrome. Start the server from a plain terminal: `uv run ember serve` — wait for `loading whisper… N s`.
5. Open http://127.0.0.1:8765/ on the subject's screen and http://127.0.0.1:8765/operator on the operator's.

## Each session
1. Assign a subject code (`S01`…`S40`). No names anywhere.
2. Subject reads the three consent lines, enters the code, starts, allows the mic.
3. Operator is silent. Watch the operator page; do not intervene. Notes go in `sessions/<id>/meta.json` → `operator_notes` afterwards.
4. The session closes itself at ~6:30. The mirror and take-home stay on screen; let the subject sit with it. Say nothing about the questions.
5. Immediately after, ask exactly: **"Did you say anything you hadn't put into words before?"** Record yes/no in `calibration/pilot_log.yaml`.

## 24 hours later
Message the subject: **"Still thinking about the last question?"** Record yes/no in `calibration/pilot_log.yaml`.

## After the five pilots
1. Score each transcript by hand **before** running the observer: read `sessions/<id>/transcript.json` against `ember/bank/rubric.yaml`, one 1–7 per construct, into `calibration/human_scores.yaml` (one map per rater — operator, and a second rater if available).
2. `uv run ember observe sessions/<id>` for each pilot.
3. `uv run ember calibrate` — target **80 %** of construct scores within 1 point of the human median.
4. Every ≥ 2-point disagreement names a construct: tighten that construct's anchors in `rubric.yaml` (sharper description, a better exemplar), bump `RUBRIC_VERSION` in `ember/store.py`, re-run `ember observe` on the five, re-run `calibrate`. Repeat until it passes.
5. `uv run ember export` and open `graph/index.html` — read the five as people, not as scores. If the take-homes felt earned in the room but the radar shape looks wrong, the rubric is the problem, not the session.

## Go / no-go for the 40
- ≥ **3/5** "yes" on the immediate question **and** ≥ **3/5** "yes" on the 24-hour question, **and**
- `ember calibrate` passes at the current `rubric_version`.
If either fails: revise the bank or the rubric, run two more pilots, re-evaluate. Do not scale a loop that does not produce the effect.

## The 40
- Max 5x plan: keep to **≤ 15 sessions per day**, spread over three days, so the 5-hour usage windows never bite mid-session.
- Same room, same mic, same operator posture.
- `ember observe` each session the same day; `ember export` at the end of each day.
- Deletion on request: `rm -rf sessions/<id>` and delete the row from `ember.sqlite` (`sqlite3 ember.sqlite "delete from sessions where session_id='<id>'"`); re-run `ember export`.

## What is never committed
`sessions/`, `ember.sqlite`, `graph/data.js`. The hand-score and pilot-log YAMLs carry subject codes only.
