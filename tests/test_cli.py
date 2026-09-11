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
