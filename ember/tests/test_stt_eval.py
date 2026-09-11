from pathlib import Path
import yaml

from ember.stt_eval import wer, load_clips, render


def test_wer_is_edit_distance_over_reference_length():
    assert wer("the cat sat on the mat", "the cat sat on the mat") == 0.0
    assert wer("the cat sat", "the cat") == 1 / 3
    assert wer("the cat sat", "the dog sat") == 1 / 3
    assert wer("hätte es schön", "hatte es schon") == 2 / 3        # umlauts are errors, not matches
    assert wer("", "anything") == 0.0                              # empty reference cannot be scored


def test_load_clips_round_trip(tmp_path: Path):
    (tmp_path / "a.wav").write_bytes(b"RIFF")
    y = tmp_path / "clips.yaml"
    y.write_text(yaml.safe_dump({"clips": [{"path": "a.wav", "language": "de", "reference_text": "Hallo Welt"}]}))
    clips = load_clips(y)
    assert len(clips) == 1 and clips[0].language == "de" and clips[0].path == tmp_path / "a.wav"


def test_render_table_has_a_row_per_backend_and_clip():
    rows = [{"backend": "whisper", "repo": "mlx-community/whisper-large-v3-turbo", "language": "de",
             "clip": "a.wav", "wer": 0.05, "seconds": 1.2, "rtf": 12.0}]
    out = render(rows)
    assert "whisper" in out and "5.0%" in out and "1.20s" in out and "de" in out
