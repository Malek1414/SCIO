"""Audio conversion via the ffmpeg CLI."""
import subprocess
from pathlib import Path


def to_wav(src: Path, dst: Path) -> Path:
    dst.parent.mkdir(parents=True, exist_ok=True)
    subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-i", str(src), "-ar", "16000", "-ac", "1", str(dst)],
                   check=True)
    return dst
