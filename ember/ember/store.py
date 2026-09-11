"""Per-session folders and a SQLite index (spec §8 storage). transcript.json is the observer's only input."""
import json
import sqlite3
import time
from pathlib import Path

from .session import Session, new_session_id

RUBRIC_VERSION = "1.0.0"


class SessionStore:
    def __init__(self, root: Path):
        self.root = Path(root)
        self.root.mkdir(parents=True, exist_ok=True)
        self.db_path = self.root.parent / "ember.sqlite"
        with self._db() as db:
            db.execute("""CREATE TABLE IF NOT EXISTS sessions(
                session_id TEXT PRIMARY KEY, subject_code TEXT, started_at REAL, closed INTEGER,
                n_turns INTEGER, mirror TEXT, take_home TEXT, updated_at REAL)""")

    def _db(self):
        return sqlite3.connect(self.db_path)

    def dir_for(self, session_id: str) -> Path:
        return self.root / session_id

    def create(self, subject_code: str, consent_at: float, now: float, language: str = "en") -> Session:
        s = Session(session_id=new_session_id(subject_code, now), subject_code=subject_code,
                    started_at=now, consent_at=consent_at, language=language)
        d = self.dir_for(s.session_id)
        (d / "audio").mkdir(parents=True, exist_ok=True)
        (d / "meta.json").write_text(json.dumps({
            "session_id": s.session_id, "subject_code": subject_code, "started_at": now,
            "consent_at": consent_at, "language": language,
            "rubric_version": RUBRIC_VERSION, "operator_notes": ""}, indent=2))
        (d / "engine_log.json").write_text("[]")
        self.save(s)
        return s

    def save(self, session: Session) -> None:
        d = self.dir_for(session.session_id)
        (d / "session.json").write_text(json.dumps(session.to_dict(), indent=2, ensure_ascii=False))
        (d / "transcript.json").write_text(json.dumps({
            "session_id": session.session_id, "subject_code": session.subject_code,
            "started_at": session.started_at, "closed": session.closed, "language": session.language,
            "mirror": session.mirror, "take_home": session.take_home,
            "turns": session.transcript_for_observer()}, indent=2, ensure_ascii=False))
        with self._db() as db:
            db.execute("""INSERT INTO sessions VALUES(?,?,?,?,?,?,?,?)
                ON CONFLICT(session_id) DO UPDATE SET closed=excluded.closed, n_turns=excluded.n_turns,
                mirror=excluded.mirror, take_home=excluded.take_home, updated_at=excluded.updated_at""",
                (session.session_id, session.subject_code, session.started_at, int(session.closed),
                 len(session.turns), session.mirror, session.take_home, time.time()))

    def load(self, session_id: str) -> Session:
        return Session.from_dict(json.loads((self.dir_for(session_id) / "session.json").read_text()))

    def append_engine_log(self, session_id: str, entry: dict) -> None:
        p = self.dir_for(session_id) / "engine_log.json"
        log = json.loads(p.read_text())
        log.append(entry)
        p.write_text(json.dumps(log, indent=2, ensure_ascii=False, default=str))

    def list_sessions(self) -> list[dict]:
        with self._db() as db:
            db.row_factory = sqlite3.Row
            return [dict(r) for r in db.execute("SELECT * FROM sessions ORDER BY started_at DESC")]
