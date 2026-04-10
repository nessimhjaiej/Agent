import asyncio
from pathlib import Path

from app.agent.graph import AdminAgentGraph
from app.agent.memory import SessionMemoryStore
from app.audit.history import AuditLogger
from app.config import Settings
from app.mcp.client import MCPClient
from app.schemas import AdminChatRequest, AdminUser


def _request(session_id: str, message: str, chat_history: list[dict[str, str]] | None = None) -> AdminChatRequest:
    return AdminChatRequest(
        message=message,
        session_id=session_id,
        user=AdminUser(id="admin-1", email="admin@example.com", role="admin"),
        chat_history=chat_history or [],
    )


def test_session_memory_uses_sliding_window(tmp_path: Path) -> None:
    async def scenario() -> None:
        settings = Settings(
            state_log_path=str(tmp_path / "session_state.json"),
            audit_log_path=str(tmp_path / "audit_history.jsonl"),
            session_history_max_turns=4,
            session_history_max_chars=10_000,
        )
        memory = SessionMemoryStore(settings)
        graph = AdminAgentGraph(
            settings=settings,
            memory=memory,
            audit=AuditLogger(settings),
            mcp_client=MCPClient(settings),
        )

        await graph.invoke(_request("session-window", "first question"))
        await graph.invoke(_request("session-window", "second question"))
        await graph.invoke(_request("session-window", "third question"))

        saved = await memory.load_state("session-window")
        assert saved is not None
        assert [turn["role"] for turn in saved.chat_history] == ["user", "assistant", "user", "assistant"]
        assert saved.chat_history[0]["content"] == "second question"
        assert saved.chat_history[-2]["content"] == "third question"
        assert saved.chat_history[-1]["role"] == "assistant"

    asyncio.run(scenario())


def test_session_memory_prefers_recent_turns_under_char_budget(tmp_path: Path) -> None:
    async def scenario() -> None:
        settings = Settings(
            state_log_path=str(tmp_path / "session_state_chars.json"),
            audit_log_path=str(tmp_path / "audit_history_chars.jsonl"),
            session_history_max_turns=10,
            session_history_max_chars=80,
        )
        memory = SessionMemoryStore(settings)
        graph = AdminAgentGraph(
            settings=settings,
            memory=memory,
            audit=AuditLogger(settings),
            mcp_client=MCPClient(settings),
        )

        await graph.invoke(_request("session-chars", "old"))
        await graph.invoke(_request("session-chars", "this is a much newer message that should consume most of the budget"))

        saved = await memory.load_state("session-chars")
        assert saved is not None
        assert len(saved.chat_history) >= 2
        assert saved.chat_history[-2]["content"] == "this is a much newer message that should consume most of the budget"
        assert saved.chat_history[0]["content"] != "old"

    asyncio.run(scenario())


def test_session_memory_merges_incoming_history_without_duplication(tmp_path: Path) -> None:
    async def scenario() -> None:
        settings = Settings(
            state_log_path=str(tmp_path / "session_state_merge.json"),
            audit_log_path=str(tmp_path / "audit_history_merge.jsonl"),
            session_history_max_turns=8,
            session_history_max_chars=10_000,
        )
        memory = SessionMemoryStore(settings)
        graph = AdminAgentGraph(
            settings=settings,
            memory=memory,
            audit=AuditLogger(settings),
            mcp_client=MCPClient(settings),
        )

        await graph.invoke(_request("session-merge", "first"))
        first_state = await memory.load_state("session-merge")
        assert first_state is not None

        incoming = [
            {"role": turn["role"], "content": turn["content"]}
            for turn in first_state.chat_history
        ]
        await graph.invoke(_request("session-merge", "second", chat_history=incoming))

        saved = await memory.load_state("session-merge")
        assert saved is not None
        assert [turn["content"] for turn in saved.chat_history].count("first") == 1
        assert [turn["content"] for turn in saved.chat_history].count("second") == 1

    asyncio.run(scenario())
