import asyncio
from pathlib import Path

import app.agent.runtime as runtime_module
from app.agent.runtime import AdminAgentRuntime, AgentDecision, AgentPlannedTool
from app.config import Settings
from app.mcp.client import MCPClient


def _settings(tmp_path: Path) -> Settings:
    return Settings(
        state_log_path=str(tmp_path / "session_state.json"),
        audit_log_path=str(tmp_path / "audit_history.jsonl"),
        config_override_env_file=str(tmp_path / ".env.local"),
    )


def test_runtime_fallback_selects_mutation_tool_without_llm(tmp_path: Path) -> None:
    async def scenario() -> None:
        settings = _settings(tmp_path)
        runtime = AdminAgentRuntime(settings, MCPClient(settings))
        decision = await runtime.decide(message="restart retrieval", chat_history=[])
        assert decision.tool_calls[0].tool_name == "restart_service"
        assert decision.intent == "mutation"

    asyncio.run(scenario())


def test_runtime_fallback_returns_direct_answer_for_non_tool_request(tmp_path: Path) -> None:
    async def scenario() -> None:
        settings = _settings(tmp_path)
        runtime = AdminAgentRuntime(settings, MCPClient(settings))
        decision = await runtime.decide(message="how is the admin service built", chat_history=[])
        assert decision.tool_calls == []
        assert decision.intent == "qa"
        assert decision.answer

    asyncio.run(scenario())


def test_runtime_fallback_builds_bounded_multi_step_plan(tmp_path: Path) -> None:
    async def scenario() -> None:
        settings = _settings(tmp_path)
        runtime = AdminAgentRuntime(settings, MCPClient(settings))
        decision = await runtime.decide(
            message="show config chunking and then restart retrieval",
            chat_history=[],
        )
        assert [call.tool_name for call in decision.tool_calls] == ["get_chunking_config", "restart_service"]
        assert decision.intent == "mutation"

    asyncio.run(scenario())


def test_runtime_fallback_synthesizes_tool_response_without_llm(tmp_path: Path) -> None:
    async def scenario() -> None:
        settings = _settings(tmp_path)
        runtime = AdminAgentRuntime(settings, MCPClient(settings))
        answer = await runtime.synthesize_tool_response(
            message="show config chunking",
            tool_name="get_chunking_config",
            tool_result={
                "status": "ok",
                "service_name": "preprocessing-service",
                "config": {
                    "chunk_strategy": "late",
                    "chunk_size": 800,
                    "chunk_overlap": 120,
                },
            },
            is_mutation=False,
        )
        assert "chunking strategy" in answer
        assert "late" in answer

    asyncio.run(scenario())


def test_runtime_normalizes_plan_to_put_mutation_last(tmp_path: Path) -> None:
    settings = _settings(tmp_path)
    runtime = AdminAgentRuntime(settings, MCPClient(settings))
    tools = asyncio.run(MCPClient(settings).discover_tools())
    normalized = runtime._normalize_decision(  # type: ignore[attr-defined]
        AgentDecision(
            intent="mutation",
            tool_calls=[
                AgentPlannedTool(tool_name="restart_service", arguments={"service_name": "retrieval-service"}),
                AgentPlannedTool(tool_name="show_config", arguments={"section": "chunking"}),
            ],
        ),
        tools,
    )
    assert normalized is not None
    assert [call.tool_name for call in normalized.tool_calls] == ["show_config", "restart_service"]


def test_runtime_normalizes_plan_to_single_mutation(tmp_path: Path) -> None:
    settings = _settings(tmp_path)
    runtime = AdminAgentRuntime(settings, MCPClient(settings))
    tools = asyncio.run(MCPClient(settings).discover_tools())
    normalized = runtime._normalize_decision(  # type: ignore[attr-defined]
        AgentDecision(
            intent="mutation",
            tool_calls=[
                AgentPlannedTool(tool_name="run_evaluation", arguments={"suite": "smoke"}),
                AgentPlannedTool(tool_name="restart_service", arguments={"service_name": "retrieval-service"}),
            ],
        ),
        tools,
    )
    assert normalized is not None
    assert [call.tool_name for call in normalized.tool_calls] == ["run_evaluation"]


def test_runtime_decide_falls_back_when_llm_call_fails(tmp_path: Path, monkeypatch) -> None:
    class _BrokenChain:
        async def ainvoke(self, *_args, **_kwargs):
            raise RuntimeError("model unavailable")

    class _BrokenModel:
        def with_structured_output(self, _schema):
            return self

    class _BrokenPrompt:
        def __or__(self, _other):
            return _BrokenChain()

    async def scenario() -> None:
        settings = _settings(tmp_path).model_copy(update={"openai_key": "test-key"})
        runtime = AdminAgentRuntime(settings, MCPClient(settings))
        monkeypatch.setattr(runtime, "_should_use_llm", lambda: True)
        monkeypatch.setattr(runtime_module.ChatPromptTemplate, "from_messages", lambda *_args, **_kwargs: _BrokenPrompt())
        monkeypatch.setattr(runtime_module, "ChatOpenAI", lambda **_kwargs: _BrokenModel())
        decision = await runtime.decide(message="restart retrieval", chat_history=[])
        assert decision.tool_calls[0].tool_name == "restart_service"
        assert decision.rationale == "The model-driven decision layer failed, so the deterministic fallback selector was used."

    asyncio.run(scenario())


def test_runtime_decide_uses_fallback_when_llm_returns_no_tool_for_actionable_request(tmp_path: Path, monkeypatch) -> None:
    class _DecisionChain:
        async def ainvoke(self, *_args, **_kwargs):
            return AgentDecision(intent="qa", tool_calls=[], answer="No action needed")

    class _ModelWithStructuredOutput:
        def with_structured_output(self, _schema):
            return self

    class _Prompt:
        def __or__(self, _other):
            return _DecisionChain()

    async def scenario() -> None:
        settings = _settings(tmp_path).model_copy(update={"openai_key": "test-key"})
        runtime = AdminAgentRuntime(settings, MCPClient(settings))
        monkeypatch.setattr(runtime, "_should_use_llm", lambda: True)
        monkeypatch.setattr(runtime_module.ChatPromptTemplate, "from_messages", lambda *_args, **_kwargs: _Prompt())
        monkeypatch.setattr(runtime_module, "ChatOpenAI", lambda **_kwargs: _ModelWithStructuredOutput())
        decision = await runtime.decide(message="what's the current reranking strategy", chat_history=[])
        assert decision.tool_calls[0].tool_name == "get_reranking_config"
        assert decision.rationale == "The model returned no actionable tool, so the deterministic fallback selector was used."

    asyncio.run(scenario())


def test_runtime_synthesize_tool_response_falls_back_when_llm_call_fails(tmp_path: Path, monkeypatch) -> None:
    class _BrokenChain:
        async def ainvoke(self, *_args, **_kwargs):
            raise RuntimeError("model unavailable")

    class _BrokenModel:
        pass

    class _BrokenPrompt:
        def __or__(self, _other):
            return _BrokenChain()

    async def scenario() -> None:
        settings = _settings(tmp_path).model_copy(update={"openai_key": "test-key"})
        runtime = AdminAgentRuntime(settings, MCPClient(settings))
        monkeypatch.setattr(runtime, "_should_use_llm", lambda: True)
        monkeypatch.setattr(runtime_module.ChatPromptTemplate, "from_messages", lambda *_args, **_kwargs: _BrokenPrompt())
        monkeypatch.setattr(runtime_module, "ChatOpenAI", lambda **_kwargs: _BrokenModel())
        answer = await runtime.synthesize_tool_response(
            message="show config chunking",
            tool_name="get_chunking_config",
            tool_result={
                "status": "ok",
                "service_name": "preprocessing-service",
                "config": {
                    "chunk_strategy": "late",
                    "chunk_size": 800,
                    "chunk_overlap": 120,
                },
            },
            is_mutation=False,
        )
        assert answer == "The current chunking strategy in preprocessing-service is 'late' with chunk size 800 and overlap 120."

    asyncio.run(scenario())


def test_runtime_synthesize_plan_response_falls_back_when_llm_call_fails(tmp_path: Path, monkeypatch) -> None:
    class _BrokenChain:
        async def ainvoke(self, *_args, **_kwargs):
            raise RuntimeError("model unavailable")

    class _BrokenModel:
        pass

    class _BrokenPrompt:
        def __or__(self, _other):
            return _BrokenChain()

    async def scenario() -> None:
        settings = _settings(tmp_path).model_copy(update={"openai_key": "test-key"})
        runtime = AdminAgentRuntime(settings, MCPClient(settings))
        monkeypatch.setattr(runtime, "_should_use_llm", lambda: True)
        monkeypatch.setattr(runtime_module.ChatPromptTemplate, "from_messages", lambda *_args, **_kwargs: _BrokenPrompt())
        monkeypatch.setattr(runtime_module, "ChatOpenAI", lambda **_kwargs: _BrokenModel())
        answer = await runtime.synthesize_plan_response(
            message="show config and then restart retrieval",
            completed_tools=[
                {"tool_name": "get_chunking_config", "result": {"status": "ok"}},
                {"tool_name": "restart_service", "result": {"status": "restarted"}},
            ],
        )
        assert answer == "Completed 2 tool steps through the MCP adapter: get_chunking_config, restart_service."

    asyncio.run(scenario())
