"""Local speech-to-text. One transcriber per language; the model is loaded once and stays resident.

Backend choice per language lives in STT_CONFIG and is set by measurement — run `ember stt-eval`.
Whisper is the default for both languages because it strips disfluencies natively (spec §3.2).
"""
import difflib
import time
from pathlib import Path
from typing import Protocol

import mlx_whisper
import numpy as np

from .disfluency import clean_disfluencies

MODEL_REPO = "mlx-community/whisper-large-v3-turbo"
PARAKEET_REPO = "mlx-community/parakeet-tdt-0.6b-v3"

# language -> (backend, model repo). German is provisional until real German speech is measured.
STT_CONFIG: dict[str, tuple[str, str]] = {
    "en": ("whisper", MODEL_REPO),
    "de": ("whisper", MODEL_REPO),
}


PROMPT_ECHO_RUN = 6      # whisper occasionally transcribes its own initial_prompt back on thin or silent audio


def _tokens(text: str) -> list[str]:
    return [k for k in (t.strip(".,!?;:—–\"'").lower() for t in text.split()) if k]


def echoes_prompt(text: str, prime: str, run: int = PROMPT_ECHO_RUN) -> bool:
    """True when the transcript repeats a long verbatim stretch of the prompt back at us.

    A real answer reuses a few words of the question ("um zwei Uhr nachmittags arbeite ich");
    it does not reproduce `run` consecutive tokens of it. Short prompts are matched in full.
    """
    a, b = _tokens(text), _tokens(prime)
    if not a or not b:
        return False
    m = difflib.SequenceMatcher(a=a, b=b, autojunk=False).find_longest_match(0, len(a), 0, len(b))
    return m.size >= min(run, len(b))


class Transcriber(Protocol):
    language: str

    def warm(self) -> float: ...
    def transcribe(self, wav_path: Path, prime: str | None = None) -> str: ...


class WhisperTranscriber:
    def __init__(self, language: str = "en", repo: str = MODEL_REPO):
        self.language = language
        self.repo = repo

    def warm(self) -> float:
        """Load the model by transcribing one second of silence; mlx_whisper caches it on its ModelHolder."""
        t0 = time.perf_counter()
        mlx_whisper.transcribe(np.zeros(16000, dtype=np.float32), path_or_hf_repo=self.repo, language=self.language)
        return time.perf_counter() - t0

    def _decode(self, wav_path: Path, prime: str | None) -> str:
        out = mlx_whisper.transcribe(str(wav_path), path_or_hf_repo=self.repo, language=self.language,
                                     initial_prompt=prime)
        return out["text"].strip()

    def transcribe(self, wav_path: Path, prime: str | None = None) -> str:
        """`prime` is the question on screen. It conditions the decoder on the right spelling and
        register — German loses far fewer words that way ('neidisch' rather than 'neulich')."""
        text = self._decode(wav_path, prime)
        if prime and echoes_prompt(text, prime):
            text = self._decode(wav_path, None)      # the prompt came back as the answer; trust the unprimed read
        return text


class ParakeetTranscriber:
    """Faster than whisper but transcribes disfluencies verbatim, so its output is cleaned.
    Not a default backend — kept so `ember stt-eval` can keep comparing it (spec §3.2)."""

    def __init__(self, language: str = "en", repo: str = PARAKEET_REPO):
        self.language = language
        self.repo = repo
        self._model = None

    def _load(self):
        if self._model is None:
            from parakeet_mlx import from_pretrained
            self._model = from_pretrained(self.repo)
        return self._model

    def warm(self) -> float:
        t0 = time.perf_counter()
        self._load()
        return time.perf_counter() - t0

    def transcribe(self, wav_path: Path, prime: str | None = None) -> str:
        # Parakeet auto-detects language and takes no prompt; `prime` is accepted for interface parity.
        return clean_disfluencies(self._load().transcribe(str(wav_path)).text.strip(), self.language)


def for_language(lang: str) -> Transcriber:
    if lang not in STT_CONFIG:
        raise ValueError(f"unknown language {lang!r}")
    backend, repo = STT_CONFIG[lang]
    if backend == "whisper":
        return WhisperTranscriber(lang, repo)
    if backend == "parakeet":
        return ParakeetTranscriber(lang, repo)
    raise ValueError(f"unknown backend {backend!r} for {lang!r}")
