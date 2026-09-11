import importlib


def test_project_imports():
    for mod in ("ember", "claude_agent_sdk", "mlx_whisper", "fastapi", "pydantic", "yaml"):
        importlib.import_module(mod)
