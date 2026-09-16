---
name: combine
description: Use when ember interview results have arrived from another machine — zips or JSON files sent over WhatsApp, AirDrop, or email that need to go into the cohort graph. Triggers on "combine", "add the new interviews", "ingest the results", "pull in what they sent".
---

# combine

Files the ember result files that interviewers sent from their own Macs into the
study's cohort graph, then opens it.

Each interviewer runs `ember contribute`, which writes one JSON per interview
(scores, observer notes, short quotes — no audio, no transcript). They send those,
usually zipped. This skill takes whatever arrived and folds it into the graph.

## Steps

1. **Find the repo.** Normally `~/SCIO/ember`. If it isn't there, locate the `SCIO`
   folder before doing anything else.

2. **Find what arrived.** Look in `~/Desktop` and `~/Downloads` for `.zip` files, and
   for loose `.json` files matching `*_20*.json` (the `SUBJECT_timestamp.json` shape
   `contribute` emits). Show the user what you found and its modified date, and ask
   which to combine if anything looks ambiguous or old.

3. **Stage each zip in its own directory** under
   `~/Desktop/ember-incoming/<zip name>/`, using `unzip -j -o`. Per-zip directories
   matter: two machines commonly send files with identical names, and a flat unzip
   silently overwrites one with the other.

4. **Check for a re-send BEFORE ingesting.** Subjects in `results/` are stored
   pseudonymized (`S01`…), so `session_id` no longer matches what a sender's file
   carries — ember's own dedup cannot see the duplicate, and ingesting a re-sent zip
   files 16 fresh copies under real names. **Identity is the timestamp**
   (`\d{4}-\d{2}-\d{2}T\d{2}-\d{2}-\d{2}`), not the id. For each incoming file,
   pull its timestamp, find the `results/` file with the same one, and compare the
   payload with `subject_code` and `session_id` removed. Report counts of identical /
   new / changed, and ingest **only** the genuinely new ones. If nothing is new, say
   so and stop — do not ingest, do not commit.

5. **Ingest.** From the repo:
   ```sh
   cd ~/SCIO/ember && unset ANTHROPIC_API_KEY && uv run ember ingest <every staged .json>
   ```
   `ingest` copies them into `results/` and rebuilds `graph/data.js` in one step — do
   not run `export` afterward.

6. **Pseudonymize before committing.** Real names never go to the public repo.
   Assign the next free `S##` chronologically, continuing from the highest already in
   `ember/identities.local.json` (gitignored, the name↔code map). A returning subject
   keeps their existing code — look them up by real name first. Rewrite both
   `subject_code` and `session_id`; build the new id by matching the timestamp with an
   anchored regex, never by splitting on `_` (names contain underscores, and a split
   leaks the surname into the filename). Then grep the staged diff for every real name
   before committing.

7. **Open the graph:** `open graph/index.html`.

8. **Report** how many subjects the rebuild reported, and name the subject codes that
   were newly added versus already present.

## What to expect

- **Re-running is safe.** `export.py` dedups on `session_id`, and a local session in
  `sessions/` always wins over a contributed file. Ingesting the same result twice
  does not double-count it.
- **`skipping <file>: missing ...`** — that file isn't a contribution (often someone
  sent `meta.json` or a whole session folder). One bad file never stops the build.
  Report it; don't try to repair it.
- **A subject who appears in `sessions/` already** will be ignored as a contribution.
  That's correct, not a failure.

## Don't

- Don't ask the interviewer for audio or transcripts. They stay on their machine by
  design, and the study doesn't collect them.
- Don't commit anything in `results/` or `graph/data.js` without the user saying so —
  those carry subject quotes, and the repo is public.
