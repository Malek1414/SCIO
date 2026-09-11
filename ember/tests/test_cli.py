import subprocess, sys


def test_cli_help_lists_serve():
    out = subprocess.run([sys.executable, "-m", "ember.cli", "--help"], capture_output=True, text=True)
    assert out.returncode == 0 and "serve" in out.stdout


def test_cli_refuses_api_key(monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-test")
    from ember.cli import main
    import pytest
    with pytest.raises(SystemExit, match="ANTHROPIC_API_KEY"):
        main(["serve", "--no-warm", "--port", "0"])


def test_cli_help_lists_plan_b_commands():
    out = subprocess.run([sys.executable, "-m", "ember.cli", "--help"], capture_output=True, text=True)
    assert all(cmd in out.stdout for cmd in ("observe", "export", "calibrate"))


def test_cli_export_and_calibrate_on_fixtures(tmp_path, monkeypatch):
    import json, yaml
    from ember.cli import main
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    ALL = ("F1", "F2", "F3", "C1", "C2", "C3", "G1", "G2", "G3")
    d = tmp_path / "sessions" / "S01_x"
    d.mkdir(parents=True)
    (d / "observer.json").write_text(json.dumps({"subject_id": "S01", "session_id": "S01_x", "scored_at": "t", "rubric_version": "1.0.0",
        "constructs": {c: {"score": 4, "signal": "med", "evidence": [], "note": ""} for c in ALL}, "declined": [], "flags": []}))
    out = tmp_path / "graph" / "data.js"
    assert main(["export", "--sessions", str(tmp_path / "sessions"), "--out", str(out)]) == 0
    assert out.read_text().startswith("window.EMBER_DATA")
    scores = tmp_path / "human.yaml"
    scores.write_text(yaml.safe_dump({"sessions": {"S01_x": {"malek": {c: 4 for c in ALL}}}}))
    assert main(["calibrate", "--scores", str(scores), "--sessions", str(tmp_path / "sessions")]) == 0
    scores.write_text(yaml.safe_dump({"sessions": {"S01_x": {"malek": {c: 7 for c in ALL}}}}))
    assert main(["calibrate", "--scores", str(scores), "--sessions", str(tmp_path / "sessions")]) == 1
