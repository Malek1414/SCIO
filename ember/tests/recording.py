import hashlib, json, os
from pathlib import Path
import pytest

REC_DIR = Path(__file__).parent / "fixtures" / "recorded"


class RecordingLLM:
    def __init__(self, inner=None, dir: Path = REC_DIR):
        self.inner = inner
        self.dir = dir
        self.dir.mkdir(parents=True, exist_ok=True)
        self.last_meta: dict = {}

    @staticmethod
    def _key(system, user, schema, effort) -> str:
        blob = json.dumps([system, user, schema, effort], sort_keys=True).encode()
        return hashlib.sha256(blob).hexdigest()[:24]

    def call_json(self, *, system: str, user: str, schema: dict, effort: str) -> dict:
        f = self.dir / f"{self._key(system, user, schema, effort)}.json"
        if f.exists():
            return json.loads(f.read_text())
        if os.environ.get("EMBER_RECORD") != "1" or self.inner is None:
            pytest.skip(f"no recording {f.name}; run with EMBER_RECORD=1")
        out = self.inner.call_json(system=system, user=user, schema=schema, effort=effort)
        self.last_meta = self.inner.last_meta
        f.write_text(json.dumps(out, indent=2, ensure_ascii=False))
        return out
