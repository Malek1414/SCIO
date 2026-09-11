"""Measure STT backends against reference clips (spec §3.4). `ember stt-eval`."""
import re
import subprocess
import time
from dataclasses import dataclass
from pathlib import Path

import yaml

from .stt import MODEL_REPO, PARAKEET_REPO, STT_CONFIG, ParakeetTranscriber, WhisperTranscriber

LARGE_V3_REPO = "mlx-community/whisper-large-v3-mlx"
_WORD = re.compile(r"[\w']+", re.UNICODE)


def _words(s: str) -> list[str]:
    return _WORD.findall(s.lower())


def wer(reference: str, hypothesis: str) -> float:
    """Levenshtein word distance over reference length. 0.0 for an empty reference."""
    r, h = _words(reference), _words(hypothesis)
    if not r:
        return 0.0
    d = list(range(len(h) + 1))
    for i in range(1, len(r) + 1):
        prev, d[0] = d[0], i
        for j in range(1, len(h) + 1):
            cur = d[j]
            d[j] = min(d[j] + 1, d[j - 1] + 1, prev + (r[i - 1] != h[j - 1]))
            prev = cur
    return d[len(h)] / len(r)


@dataclass
class Clip:
    path: Path
    language: str
    reference_text: str


def load_clips(path: Path) -> list[Clip]:
    path = Path(path)
    data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    return [Clip(path=(path.parent / c["path"]).resolve(), language=c["language"], reference_text=c["reference_text"])
            for c in (data.get("clips") or [])]


def _duration(p: Path) -> float:
    out = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", str(p)],
                         capture_output=True, text=True).stdout.strip()
    return float(out) if out else 0.0


def evaluate(clips: list[Clip], backends: list[tuple[str, str, str]]) -> list[dict]:
    """backends: (label, kind, repo). Returns one row per (backend, clip)."""
    rows = []
    for label, kind, repo in backends:
        for clip in clips:
            t = WhisperTranscriber(clip.language, repo) if kind == "whisper" else ParakeetTranscriber(clip.language, repo)
            try:
                t.warm()
                t.transcribe(clip.path)                      # discard the first run
                t0 = time.perf_counter()
                text = t.transcribe(clip.path)
                dt = time.perf_counter() - t0
                dur = _duration(clip.path)
                rows.append({"backend": label, "repo": repo, "language": clip.language, "clip": clip.path.name,
                             "wer": wer(clip.reference_text, text), "seconds": dt,
                             "rtf": (dur / dt) if dt else 0.0, "text": text})
            except Exception as e:
                rows.append({"backend": label, "repo": repo, "language": clip.language, "clip": clip.path.name,
                             "wer": None, "seconds": None, "rtf": None, "text": f"ERROR {e!r}"[:120]})
    return rows


def render(rows: list[dict]) -> str:
    out = [f"{'backend':22s} {'lang':4s} {'clip':18s} {'WER':>7s} {'time':>8s} {'RTF':>6s}"]
    for r in rows:
        w = f"{r['wer'] * 100:6.1f}%" if r["wer"] is not None else "    n/a"
        s = f"{r['seconds']:7.2f}s" if r["seconds"] is not None else "    n/a"
        f = f"{r['rtf']:5.0f}x" if r["rtf"] else "   n/a"
        out.append(f"{r['backend']:22s} {r['language']:4s} {r['clip']:18s} {w} {s} {f}")
    out.append("\ncurrent defaults: " + ", ".join(f"{k}={v[0]}:{v[1].split('/')[-1]}" for k, v in STT_CONFIG.items()))
    return "\n".join(out)


DEFAULT_BACKENDS = [("whisper turbo", "whisper", MODEL_REPO),
                    ("whisper large-v3", "whisper", LARGE_V3_REPO),
                    ("parakeet v3", "parakeet", PARAKEET_REPO)]
