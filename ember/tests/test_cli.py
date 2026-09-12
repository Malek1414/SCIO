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


def test_cli_observe_uses_a_long_timeout(tmp_path, monkeypatch):
    import json
    import ember.llm as llm_mod
    from ember.cli import main
    ALL = ("F1", "F2", "F3", "C1", "C2", "C3", "G1", "G2", "G3")
    captured = {}

    class RecordingLLMClass:
        def __init__(self, **kw):
            captured.update(kw)

        def call_json(self, **kw):
            return {"constructs": {c: {"score": 4, "evidence": [], "note": "n"} for c in ALL}, "declined": [], "flags": []}

    monkeypatch.setattr(llm_mod, "LLM", RecordingLLMClass)
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    d = tmp_path / "S01_x"
    d.mkdir()
    (d / "transcript.json").write_text(json.dumps({"session_id": "S01_x", "subject_code": "S01", "started_at": 0, "closed": True,
                                                   "mirror": None, "take_home": None, "turns": []}))
    assert main(["observe", str(d)]) == 0
    assert captured["timeout_s"] >= 60                     # offline scoring must not use the live engine's 15 s bound
    assert (d / "observer.json").exists()


def test_autoscore_reports_and_swallows_a_bad_session(tmp_path, capsys):
    """A scoring failure must not take the server down with it."""
    from ember.cli import _autoscore

    hook = _autoscore(tmp_path / "sessions", tmp_path / "graph" / "data.js")
    hook("NO_SUCH_SESSION")                                   # must not raise
    assert "autoscore failed for NO_SUCH_SESSION" in capsys.readouterr().out
