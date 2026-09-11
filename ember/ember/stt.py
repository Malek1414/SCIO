"""Local speech-to-text. The model is loaded once and stays resident (spec §8 STT)."""
import time
from pathlib import Path

import mlx_whisper
import numpy as np

MODEL_REPO = "mlx-community/whisper-large-v3-turbo"


class Transcriber:
    def __init__(self, repo: str = MODEL_REPO):
        self.repo = repo

    def warm(self) -> float:
        """Load the model by transcribing one second of silence. mlx_whisper caches it on its ModelHolder."""
        t0 = time.perf_counter()
        mlx_whisper.transcribe(np.zeros(16000, dtype=np.float32), path_or_hf_repo=self.repo, language="en")
        return time.perf_counter() - t0

    def transcribe(self, wav_path: Path) -> str:
        out = mlx_whisper.transcribe(str(wav_path), path_or_hf_repo=self.repo, language="en")
        return out["text"].strip()
