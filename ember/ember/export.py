"""Fold every observer.json into graph/data.js for the static cohort page (spec §7).

Two sources feed the page: `sessions/` — interviews run on this machine, audio and all — and
`results/` — scored results contributed by someone else's laptop and merged by pull request.
A contributed file is already in the per-subject shape this module emits, so it is appended
as-is; a local session of the same id always wins.
"""
import json
import time
from datetime import datetime, timezone
from pathlib import Path

from .bank import Bank
from .constructs import CONSTRUCTS, CLUSTER_OF
from .observer import load_results
from .store import RUBRIC_VERSION


REQUIRED = ("subject_code", "session_id", "scored_at", "rubric_version", "scores")


def _contributed(results_root: Path, seen: set[str]) -> list[dict]:
    """Load merged contributions. Malformed files are reported and skipped, never fatal —
    one bad contribution must not stop the cohort page from building."""
    out = []
    for f in sorted(Path(results_root).glob("*.json")):
        try:
            d = json.loads(f.read_text(encoding="utf-8"))
        except json.JSONDecodeError as e:
            print(f"skipping {f.name}: not valid JSON ({e})")
            continue
        missing = [k for k in REQUIRED if k not in d]
        if missing:
            print(f"skipping {f.name}: missing {', '.join(missing)}")
            continue
        if d["session_id"] in seen:                  # a local session always wins over a contribution
            continue
        d.setdefault("language", "en")
        d.setdefault("declined", [])
        d.setdefault("flags", [])
        d.setdefault("mirror", None)
        d.setdefault("take_home", None)
        d["contributed"] = True
        out.append(d)
        seen.add(d["session_id"])
    return out


def collect(sessions_root: Path, bank: Bank, *, now: float | None = None,
            results_root: Path | None = None) -> dict:
    root = Path(sessions_root)
    subjects = []
    for sid, r in load_results(root).items():
        tr_path = root / sid / "transcript.json"
        tr = json.loads(tr_path.read_text(encoding="utf-8")) if tr_path.exists() else {}
        subjects.append({"subject_code": r["subject_id"], "session_id": sid, "scored_at": r["scored_at"],
                         "rubric_version": r["rubric_version"], "scores": r["constructs"],
                         "language": tr.get("language", r.get("language", "en")),
                         "declined": r.get("declined", []), "flags": r.get("flags", []),
                         "mirror": tr.get("mirror"), "take_home": tr.get("take_home")})
    if results_root is not None and Path(results_root).is_dir():
        subjects += _contributed(Path(results_root), {s["session_id"] for s in subjects})
    subjects.sort(key=lambda s: (s["subject_code"], s["session_id"]))   # repeat runs stay adjacent and ordered
    ts = datetime.fromtimestamp(now if now is not None else time.time(), tz=timezone.utc).isoformat()
    return {"generated_at": ts, "rubric_version": RUBRIC_VERSION,
            "constructs": [{"id": c, "cluster": CLUSTER_OF[c], "name": bank.rubric[c].name, "inverse": bank.rubric[c].inverse}
                           for c in CONSTRUCTS],
            "subjects": subjects}


def write_data_js(data: dict, out: Path) -> Path:
    out = Path(out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text("window.EMBER_DATA = " + json.dumps(data, ensure_ascii=False, indent=1) + ";\n", encoding="utf-8")
    return out
