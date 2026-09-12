# Running an ember interview on your own machine

You run the interview locally, on your own hardware and your own Claude subscription.
The recording never leaves your laptop. When you're done you send one small JSON
file — the scores — to whoever runs the study.

## What you need

- **An Apple Silicon Mac** (M1 or later). The speech model is built on MLX, which is
  Apple-only. Intel Macs, Windows and Linux can't run this yet.
- **Claude Code**, signed in on a paid plan. The interview drives it through the Agent
  SDK, so your interviews run on your subscription, not anyone else's.
- **ffmpeg** — `brew install ffmpeg`
- **uv** — `curl -LsSf https://astral.sh/uv/install.sh | sh`

You do **not** need access to the study's own repository, and you won't be given any. You
run interviews; you send back one file per interview. You never see anyone else's answers,
and nobody sees yours except whoever runs the study.

## Setup

```sh
git clone https://github.com/Malek1414/SCIO.git
cd SCIO/ember
uv sync
```

Make sure `ANTHROPIC_API_KEY` is **not** set. ember refuses to start if it is — that
variable would bill an API account instead of using your subscription.

```sh
echo $ANTHROPIC_API_KEY      # must print nothing
```

## Run an interview

```sh
uv run ember serve
```

That prints two links. Open the first one and give it microphone permission.

- `http://127.0.0.1:8765/` — the subject screen
- `http://127.0.0.1:8765/?lang=de` — same thing in German
- `http://127.0.0.1:8765/operator` — the operator view, for whoever is running the session

The subject holds **space** to answer and releases when they're done. Seven questions,
roughly seven minutes, though nothing is on a timer — a question is never skipped and
never times out, so take as long as the answer takes.

When the interview closes it scores itself in the background (about 30 seconds) and
writes `graph/data.js`. Open `graph/index.html` in a browser to see the result.

## Send the result back

```sh
uv run ember contribute sessions/<SUBJECT>_<timestamp>
```

That writes one file into `outbox/`. Send that file to whoever runs the study, however you
normally send things. That's the whole handover — there's no git, no pull request, no
account to set up.

It prints exactly what's in the file before you send it, e.g.

```
wrote outbox/KAI_2026-09-12T10-00-00.json  (KAI · de · 9 scores · 6 quoted answers)
```

**What's in it:** the nine construct scores, the observer's notes and flags, the closing
mirror and take-home question, and short verbatim quotes from the subject's answers as
the evidence behind each score.

**What is not:** the audio, and the full transcript. Both stay in `sessions/` on your
machine. `sessions/` and `outbox/` are both gitignored, so nothing leaves by accident.

Read the file before you send it if you like — it's plain JSON, and the quotes in it are
the part your subject agreed to share.

## Before you interview anyone

The consent screen tells the subject that their scores and quoted answers may go to the
study's private repository. Let them actually read it. If they want their session gone
afterwards, delete the `sessions/<id>/` directory on your machine. If you already sent the
file, say so — it can be pulled before it ever reaches the dashboard.

## When something breaks

| Symptom | Fix |
|---|---|
| `ember runs on your Claude subscription` on startup | `unset ANTHROPIC_API_KEY` |
| `address already in use` | an ember is already running — `pkill -f "ember serve"` |
| `no observer.json` from `contribute` | the session wasn't scored: `uv run ember observe sessions/<id>` |
| Microphone does nothing | the browser needs mic permission for `127.0.0.1`, and the page must be the one ember served |
| The server dies mid-interview | macOS can kill it under memory pressure. Restart it, then reopen `http://127.0.0.1:8765/?sid=<session id>` to resume at the pending question — nothing is lost, every answer is written to disk as it happens. |
