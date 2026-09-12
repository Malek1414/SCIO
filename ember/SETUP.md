# Running an ember interview on your own machine

You run the interview locally, on your own hardware and your own Claude subscription.
The recording never leaves your laptop. When you're done you send back one small JSON
file — the scores — as a pull request.

## What you need

- **An Apple Silicon Mac** (M1 or later). The speech model is built on MLX, which is
  Apple-only. Intel Macs, Windows and Linux can't run this yet.
- **Claude Code**, signed in on a paid plan. The interview drives it through the Agent
  SDK, so your interviews run on your subscription, not anyone else's.
- **ffmpeg** — `brew install ffmpeg`
- **uv** — `curl -LsSf https://astral.sh/uv/install.sh | sh`
- **gh**, signed in — `brew install gh && gh auth login`
- Access to the study repository (it's private — ask for an invite).

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

That writes `results/<session id>.json`, branches, commits, pushes and opens the pull
request. Add `--no-pr` if you'd rather do the git part yourself — it prints the commands.

**What's in that file:** the nine construct scores, the observer's notes and flags, the
closing mirror and take-home question, and short verbatim quotes from the subject's
answers as evidence for each score.

**What is not:** the audio, and the full transcript. Those stay in `sessions/` on your
machine, which is gitignored and never uploaded.

## Before you interview anyone

The consent screen tells the subject that their scores and quoted answers may go to the
study's private repository. Let them actually read it. If they want their session gone
afterwards, delete the `sessions/<id>/` directory and say so on the pull request — or
close the PR if it hasn't been merged.

## When something breaks

| Symptom | Fix |
|---|---|
| `ember runs on your Claude subscription` on startup | `unset ANTHROPIC_API_KEY` |
| `address already in use` | an ember is already running — `pkill -f "ember serve"` |
| `no observer.json` from `contribute` | the session wasn't scored: `uv run ember observe sessions/<id>` |
| Microphone does nothing | the browser needs mic permission for `127.0.0.1`, and the page must be the one ember served |
| `gh pr create failed` | `gh auth login`, and check you have access to the repo |
