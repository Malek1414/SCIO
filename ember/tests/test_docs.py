from pathlib import Path
import yaml

ROOT = Path(__file__).parent.parent


def test_pilot_protocol_covers_the_spec_measures():
    doc = (ROOT / "docs" / "pilot-protocol.md").read_text(encoding="utf-8")
    for needle in ("Did you say anything you hadn't put into words before?", "Still thinking about the last question?",
                   "3/5", "ember observe", "ember calibrate", "80", "human_scores.yaml", "pilot_log.yaml", "rubric_version"):
        assert needle in doc, needle


def test_pilot_log_template_parses():
    data = yaml.safe_load((ROOT / "calibration" / "pilot_log.yaml").read_text(encoding="utf-8"))
    assert data == {"pilots": {}}
