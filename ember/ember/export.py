"""Fold every observer.json into graph/data.js for the static cohort page (spec §7)."""
import json
import time
from datetime import datetime, timezone
from pathlib import Path

from .bank import Bank
from .constructs import CONSTRUCTS, CLUSTER_OF
from .observer import load_results
from .store import RUBRIC_VERSION


def collect(sessions_root: Path, bank: Bank, *, now: float | None = None) -> dict:
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
    subjects.sort(key=lambda s: s["subject_code"])
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
