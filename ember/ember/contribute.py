"""Package a scored interview for the study's dashboard, and take one in at the other end (§7).

Audio never leaves the machine that recorded it. What travels is one JSON file in the exact
per-subject shape `export.collect` emits, so the receiving side needs no translation.

Interviewers do not get access to the study repository — they send the file, and whoever runs
the study ingests it. That is the whole reason `contribute` writes a file by default and only
opens a pull request when asked: an interviewer who cannot read the repository cannot read
anybody else's answers either.
"""
import json
import re
import shutil
import subprocess
from pathlib import Path

BRANCH_PREFIX = "contribution/"
SAFE_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.-]{0,127}$")


class ContributeError(RuntimeError):
    pass


def build_result(session_dir: Path) -> dict:
    """Read a scored session into the shape the cohort page consumes."""
    session_dir = Path(session_dir)
    obs_path = session_dir / "observer.json"
    if not obs_path.exists():
        raise ContributeError(f"{session_dir.name} has no observer.json — score it first with "
                              f"`ember observe {session_dir}`")
    r = json.loads(obs_path.read_text(encoding="utf-8"))
    tr_path = session_dir / "transcript.json"
    tr = json.loads(tr_path.read_text(encoding="utf-8")) if tr_path.exists() else {}
    return {"subject_code": r["subject_id"], "session_id": r["session_id"], "scored_at": r["scored_at"],
            "rubric_version": r["rubric_version"], "scores": r["constructs"],
            "language": tr.get("language", r.get("language", "en")),
            "declined": r.get("declined", []), "flags": r.get("flags", []),
            "mirror": tr.get("mirror"), "take_home": tr.get("take_home")}


def write_result(result: dict, results_root: Path) -> Path:
    results_root = Path(results_root)
    results_root.mkdir(parents=True, exist_ok=True)
    out = results_root / f"{result['session_id']}.json"
    out.write_text(json.dumps(result, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    return out


def _git(*args: str, cwd: Path) -> str:
    done = subprocess.run(["git", *args], cwd=cwd, capture_output=True, text=True)
    if done.returncode != 0:
        raise ContributeError(f"git {' '.join(args)} failed: {done.stderr.strip() or done.stdout.strip()}")
    return done.stdout.strip()


def open_pull_request(result_file: Path, session_id: str, *, repo_root: Path) -> str:
    """Branch, commit the one result file, push, and open the PR. Returns the PR url."""
    branch = BRANCH_PREFIX + session_id
    _git("checkout", "-b", branch, cwd=repo_root)
    _git("add", "--", str(Path(result_file).resolve()), cwd=repo_root)
    _git("commit", "-m", f"Contribute scored interview {session_id}", cwd=repo_root)
    _git("push", "-u", "origin", branch, cwd=repo_root)
    done = subprocess.run(
        ["gh", "pr", "create", "--fill", "--title", f"Contribute scored interview {session_id}",
         "--body", "Scored result only — audio and the full transcript stayed on the interviewer's machine.\n\n"
                   "Merge, then `ember export` to put it on the cohort page."],
        cwd=repo_root, capture_output=True, text=True)
    if done.returncode != 0:
        raise ContributeError(f"gh pr create failed: {done.stderr.strip() or done.stdout.strip()}")
    return done.stdout.strip().splitlines()[-1] if done.stdout.strip() else ""


def repo_root_for(path: Path) -> Path:
    return Path(_git("rev-parse", "--show-toplevel", cwd=Path(path).resolve()))


def ingest(incoming: Path, results_root: Path) -> Path:
    """Take a result file sent by an interviewer and file it under results/.

    The file came from another machine, so nothing in it is trusted: the destination name is
    built from the validated session_id in the payload, never from the name on disk.
    """
    incoming = Path(incoming)
    if not incoming.is_file():
        raise ContributeError(f"{incoming} is not a file")
    try:
        d = json.loads(incoming.read_text(encoding="utf-8"))
    except json.JSONDecodeError as e:
        raise ContributeError(f"{incoming.name} is not valid JSON: {e}") from e
    if not isinstance(d, dict):
        raise ContributeError(f"{incoming.name} is not a result object")

    from .export import REQUIRED
    missing = [k for k in REQUIRED if k not in d]
    if missing:
        raise ContributeError(f"{incoming.name} is missing {', '.join(missing)} — is it an ember result?")
    sid = str(d["session_id"])
    if not SAFE_ID.match(sid):
        raise ContributeError(f"{incoming.name} has an unusable session_id {sid!r}")

    results_root = Path(results_root)
    results_root.mkdir(parents=True, exist_ok=True)
    out = results_root / f"{sid}.json"                  # name from the payload, not from the sender
    shutil.copyfile(incoming, out)
    return out
