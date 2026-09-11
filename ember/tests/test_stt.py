import subprocess, time
from pathlib import Path
import pytest

from ember.audio import to_wav
from ember.stt import STT_CONFIG, Transcriber, WhisperTranscriber, for_language

AUDIO = Path(__file__).parent / "fixtures" / "audio"


def test_config_covers_both_languages_and_dispatches():
    assert set(STT_CONFIG) == {"en", "de"}
    for lang, (backend, repo) in STT_CONFIG.items():
        assert backend in ("whisper", "parakeet") and repo.startswith("mlx-community/")
    t = for_language("de")
    assert isinstance(t, WhisperTranscriber) and t.language == "de"
    assert for_language("en").language == "en"
    with pytest.raises(ValueError, match="unknown language"):
        for_language("fr")


@pytest.mark.slow
class TestRealAudio:
    @pytest.fixture(scope="class")
    def clip(self) -> Path:
        AUDIO.mkdir(parents=True, exist_ok=True)
        aiff = AUDIO / "clip.aiff"
        if not aiff.exists():
            subprocess.run(["say", "-o", str(aiff),
                            "I rebuilt the whole backend three times. Nobody asked me to. "
                            "My friends thought I was wasting my time, and by any normal measure I probably was."],
                           check=True)
        return aiff

    @pytest.fixture(scope="class")
    def german_clip(self) -> Path:
        AUDIO.mkdir(parents=True, exist_ok=True)
        aiff = AUDIO / "clip_de.aiff"
        if not aiff.exists():
            subprocess.run(["say", "-v", "Anna", "-o", str(aiff),
                            "Ich habe das ganze Backend dreimal neu gebaut. Niemand hat mich darum gebeten. "
                            "Meine Freunde dachten, ich verschwende meine Zeit."], check=True)
        return aiff

    def test_to_wav_produces_16k_mono(self, clip, tmp_path):
        wav = to_wav(clip, tmp_path / "clip.wav")
        info = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "stream=sample_rate,channels",
                               "-of", "csv=p=0", str(wav)], capture_output=True, text=True, check=True).stdout
        assert info.strip() == "16000,1"

    def test_english_transcribe_after_warm(self, clip, tmp_path):
        wav = to_wav(clip, tmp_path / "clip.wav")
        t = for_language("en")
        warm_s = t.warm()
        t0 = time.perf_counter()
        text = t.transcribe(wav)
        dt = time.perf_counter() - t0
        print(f"\nen warm={warm_s:.1f}s transcribe={dt:.2f}s text={text!r}")
        assert "wasting my time" in text.lower() and "nobody asked me" in text.lower()
        assert dt < 6.0

    def test_german_transcribe_and_priming(self, german_clip, tmp_path):
        wav = to_wav(german_clip, tmp_path / "clip_de.wav")
        t = for_language("de")
        t.warm()
        text = t.transcribe(wav)
        primed = t.transcribe(wav, prime="Was hast du dafür schon aufgegeben?")
        print(f"\nde text={text!r}\nde primed={primed!r}")
        assert "backend" in text.lower() and "freunde" in text.lower()
        assert "ich" in primed.lower()                      # priming must not break the transcript
