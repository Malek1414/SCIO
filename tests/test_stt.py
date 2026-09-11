import subprocess, time
from pathlib import Path
import pytest

from ember.audio import to_wav
from ember.stt import Transcriber

pytestmark = pytest.mark.slow
AUDIO = Path(__file__).parent / "fixtures" / "audio"


@pytest.fixture(scope="module")
def clip() -> Path:
    AUDIO.mkdir(parents=True, exist_ok=True)
    aiff = AUDIO / "clip.aiff"
    if not aiff.exists():
        subprocess.run(["say", "-o", str(aiff),
                        "I rebuilt the whole backend three times. Nobody asked me to. "
                        "My friends thought I was wasting my time, and by any normal measure I probably was."],
                       check=True)
    return aiff


def test_to_wav_produces_16k_mono(clip, tmp_path):
    wav = to_wav(clip, tmp_path / "clip.wav")
    info = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "stream=sample_rate,channels",
                           "-of", "csv=p=0", str(wav)], capture_output=True, text=True, check=True).stdout
    assert info.strip() == "16000,1"


def test_transcribe_after_warm(clip, tmp_path):
    wav = to_wav(clip, tmp_path / "clip.wav")
    t = Transcriber()
    warm_s = t.warm()
    t0 = time.perf_counter()
    text = t.transcribe(wav)
    dt = time.perf_counter() - t0
    print(f"\nwarm={warm_s:.1f}s  transcribe={dt:.2f}s  text={text!r}")
    assert "backend" in text.lower() and "wasting my time" in text.lower()   # whisper writes numbers as digits
    assert dt < 6.0
