"""The only module that talks to the Claude Agent SDK (spec §8 Engine)."""
import asyncio
import json
import os

from claude_agent_sdk import query as sdk_query, ClaudeAgentOptions

MODEL = "opus"
FALLBACK_MODEL = "sonnet"


class LLMError(RuntimeError):
    pass


def guard_environment() -> None:
    """Refuse to bill the API by accident; strip nested Claude Code session vars."""
    if os.environ.get("ANTHROPIC_API_KEY") is not None:
        raise SystemExit("ember runs on your Claude subscription. Unset ANTHROPIC_API_KEY before starting.")
    for k in [k for k in os.environ if k.startswith("CLAUDE")]:
        os.environ.pop(k)


class LLM:
    def __init__(self, *, model: str = MODEL, fallback_model: str = FALLBACK_MODEL, timeout_s: float = 15.0, query_fn=None):
        self.model = model
        self.fallback_model = fallback_model
        self.timeout_s = timeout_s
        self._query = query_fn or sdk_query
        self.last_meta: dict = {}

    def options(self, *, system: str, schema: dict, effort: str) -> ClaudeAgentOptions:
        return ClaudeAgentOptions(
            system_prompt=system,
            model=self.model,
            fallback_model=self.fallback_model,
            effort=effort,
            thinking={"type": "adaptive"},
            output_format={"type": "json_schema", "schema": schema},
            tools=[],
            max_turns=2,
            setting_sources=[],        # no ~/.claude or ./.claude settings, skills, memory
            mcp_servers={},
            strict_mcp_config=True,    # no MCP servers from any config file
        )

    def call_json(self, *, system: str, user: str, schema: dict, effort: str) -> dict:
        """Synchronous. Runs its own event loop; from inside a running loop use asyncio.to_thread.
        Bounded: timeout_s per attempt, one retry, then LLMError (spec §9)."""
        last: LLMError | None = None
        for _attempt in range(2):
            try:
                return asyncio.run(asyncio.wait_for(self._call(system, user, schema, effort), timeout=self.timeout_s))
            except LLMError as e:
                last = e
            except TimeoutError:
                last = LLMError(f"timed out after {self.timeout_s}s")
            except Exception as e:  # transport, SDK, JSON
                last = LLMError(str(e))
                last.__cause__ = e
        raise last

    async def _call(self, system: str, user: str, schema: dict, effort: str) -> dict:
        result = None
        async for m in self._query(prompt=user, options=self.options(system=system, schema=schema, effort=effort)):
            if hasattr(m, "structured_output"):
                result = m
        if result is None:
            raise LLMError("no ResultMessage received")
        self.last_meta = {
            "total_cost_usd": getattr(result, "total_cost_usd", None),
            "duration_ms": getattr(result, "duration_ms", None),
            "usage": getattr(result, "usage", None),
        }
        if getattr(result, "is_error", False) or getattr(result, "subtype", "success") != "success":
            raise LLMError(f"result subtype={getattr(result, 'subtype', '?')}")
        out = result.structured_output
        if out is None:
            out = json.loads(result.result or "")
        if not isinstance(out, dict):
            raise LLMError("structured output is not an object")
        return out
