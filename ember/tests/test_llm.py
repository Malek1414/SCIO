import os
from types import SimpleNamespace
import pytest

from ember.llm import LLM, LLMError, guard_environment

SCHEMA = {"type": "object", "properties": {"x": {"type": "integer"}}, "required": ["x"], "additionalProperties": False}


def _fake_query(structured=None, result=None, is_error=False, subtype="success"):
    async def q(*, prompt, options):
        q.seen = {"prompt": prompt, "options": options}
        yield SimpleNamespace(structured_output=structured, result=result, is_error=is_error, subtype=subtype,
                              total_cost_usd=0.01, duration_ms=1500, usage={"input_tokens": 2})
    return q


def test_call_json_returns_structured_output_and_meta():
    q = _fake_query(structured={"x": 3})
    llm = LLM(query_fn=q)
    assert llm.call_json(system="S", user="U", schema=SCHEMA, effort="low") == {"x": 3}
    assert llm.last_meta["total_cost_usd"] == 0.01
    assert q.seen["prompt"] == "U"


def test_options_carry_isolation_and_model_settings():
    llm = LLM(query_fn=_fake_query(structured={"x": 1}))
    o = llm.options(system="S", schema=SCHEMA, effort="high")
    assert o.system_prompt == "S" and o.model == "opus" and o.fallback_model == "sonnet"
    assert o.effort == "high" and o.thinking == {"type": "adaptive"}
    assert o.output_format == {"type": "json_schema", "schema": SCHEMA}
    assert o.tools == [] and o.max_turns == 2
    assert o.setting_sources == [] and o.mcp_servers == {} and o.strict_mcp_config is True


def test_falls_back_to_parsing_result_string():
    llm = LLM(query_fn=_fake_query(structured=None, result='{"x": 9}'))
    assert llm.call_json(system="S", user="U", schema=SCHEMA, effort="low") == {"x": 9}


def test_error_result_raises_llm_error():
    llm = LLM(query_fn=_fake_query(structured=None, result=None, is_error=True, subtype="agent_error"))
    with pytest.raises(LLMError):
        llm.call_json(system="S", user="U", schema=SCHEMA, effort="low")


def test_transport_exception_wrapped():
    async def boom(*, prompt, options):
        raise RuntimeError("socket closed")
        yield  # pragma: no cover
    with pytest.raises(LLMError, match="socket closed"):
        LLM(query_fn=boom).call_json(system="S", user="U", schema=SCHEMA, effort="low")


def test_retries_once_then_succeeds():
    calls = {"n": 0}

    async def flaky(*, prompt, options):
        calls["n"] += 1
        if calls["n"] == 1:
            raise RuntimeError("first attempt fails")
        yield SimpleNamespace(structured_output={"x": 5}, result=None, is_error=False, subtype="success",
                              total_cost_usd=0, duration_ms=1, usage={})
    assert LLM(query_fn=flaky).call_json(system="S", user="U", schema=SCHEMA, effort="low") == {"x": 5}
    assert calls["n"] == 2


def test_timeout_per_attempt_then_llm_error():
    import asyncio

    async def slow(*, prompt, options):
        await asyncio.sleep(0.2)
        yield SimpleNamespace(structured_output={"x": 1}, result=None, is_error=False, subtype="success")
    with pytest.raises(LLMError, match="timed out"):
        LLM(query_fn=slow, timeout_s=0.05).call_json(system="S", user="U", schema=SCHEMA, effort="low")


def test_guard_environment(monkeypatch):
    monkeypatch.setenv("CLAUDECODE", "1")
    monkeypatch.setenv("CLAUDE_CODE_SESSION_ID", "abc")
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    guard_environment()
    assert "CLAUDECODE" not in os.environ and "CLAUDE_CODE_SESSION_ID" not in os.environ
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-x")
    with pytest.raises(SystemExit, match="ANTHROPIC_API_KEY"):
        guard_environment()
