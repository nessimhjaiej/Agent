import asyncio
from pathlib import Path

import pytest

from app.config import Settings
from app.mcp.client import MCPClient, MCPToolNotFoundError
from app.tools.wrappers import build_tool_wrappers


def _settings(tmp_path: Path) -> Settings:
    return Settings(
        state_log_path=str(tmp_path / "session_state.json"),
        audit_log_path=str(tmp_path / "audit_history.jsonl"),
        config_override_env_file=str(tmp_path / ".env.local"),
    )


def test_mcp_adapter_discovers_expected_tools(tmp_path: Path) -> None:
    async def scenario() -> None:
        client = MCPClient(_settings(tmp_path))
        tools = await client.discover_tools()
        names = {tool.name for tool in tools}
        assert names == {
            "get_vector_stats",
            "show_config",
            "get_chunking_config",
            "update_chunking_config",
            "get_retrieval_config",
            "update_retrieval_config",
            "get_reranking_config",
            "update_reranking_config",
            "reindex_embeddings",
            "delete_document",
            "run_evaluation",
            "restart_service",
        }
        restart = next(tool for tool in tools if tool.name == "restart_service")
        assert restart.requires_confirmation is True
        assert restart.mutation is True

    asyncio.run(scenario())


def test_mcp_adapter_executes_stubbed_tool(tmp_path: Path) -> None:
    async def scenario() -> None:
        client = MCPClient(_settings(tmp_path))
        result = await client.execute_tool("show_config", {"service_name": "generation-service"})
        assert result.tool_name == "show_config"
        assert result.service == "platform-config"
        assert result.result["status"] == "ok"
        assert result.result["service_name"] == "generation-service"
        assert "generation_model" in result.result["config"]

    asyncio.run(scenario())


def test_mcp_adapter_selects_show_config_for_natural_language_chunking_question(tmp_path: Path) -> None:
    async def scenario() -> None:
        client = MCPClient(_settings(tmp_path))
        selection = await client.select_tool_for_message("what's the current chunking strategy")
        assert selection is not None
        assert selection.tool_name == "get_chunking_config"
        assert selection.arguments == {}

    asyncio.run(scenario())


def test_mcp_adapter_selects_reranking_config_for_natural_language_question(tmp_path: Path) -> None:
    async def scenario() -> None:
        client = MCPClient(_settings(tmp_path))
        selection = await client.select_tool_for_message("what's the current reranking strategy")
        assert selection is not None
        assert selection.tool_name == "get_reranking_config"

    asyncio.run(scenario())


def test_mcp_adapter_updates_chunking_config_in_env_override(tmp_path: Path) -> None:
    async def scenario() -> None:
        settings = _settings(tmp_path)
        client = MCPClient(settings)
        result = await client.execute_tool(
            "update_chunking_config",
            {"chunk_strategy": "late", "chunk_size": 900, "chunk_overlap": 150},
        )
        assert result.result["status"] == "updated"
        env_text = settings.config_override_env_path.read_text(encoding="utf-8")
        assert "PREPROCESSING_CHUNK_SIZE=900" in env_text
        assert "PREPROCESSING_CHUNK_OVERLAP=150" in env_text

    asyncio.run(scenario())


def test_mcp_adapter_updates_retrieval_and_reranking_config_in_env_override(tmp_path: Path) -> None:
    async def scenario() -> None:
        settings = _settings(tmp_path)
        client = MCPClient(settings)
        retrieval_result = await client.execute_tool(
            "update_retrieval_config",
            {"fusion_type": "rrf", "top_k_retrieve": 8, "top_k_return": 4, "rrf_k": 80},
        )
        rerank_result = await client.execute_tool(
            "update_reranking_config",
            {"ranker_type": "cross_encoder", "rerank_top_n": 12},
        )
        assert retrieval_result.result["status"] == "updated"
        assert rerank_result.result["status"] == "updated"
        env_text = settings.config_override_env_path.read_text(encoding="utf-8")
        assert "RETRIEVAL_DEFAULT_FUSION=rrf" in env_text
        assert "RETRIEVAL_DEFAULT_RANKER=cross_encoder" in env_text

    asyncio.run(scenario())


def test_mcp_adapter_reads_retrieval_and_reranking_configs(tmp_path: Path) -> None:
    async def scenario() -> None:
        client = MCPClient(_settings(tmp_path))
        retrieval_result = await client.execute_tool("get_retrieval_config", {})
        reranking_result = await client.execute_tool("get_reranking_config", {})
        assert retrieval_result.result["status"] == "ok"
        assert "fusion_type" in retrieval_result.result["config"]
        assert reranking_result.result["status"] == "ok"
        assert "ranker_type" in reranking_result.result["config"]

    asyncio.run(scenario())


def test_mcp_adapter_rejects_unknown_tool(tmp_path: Path) -> None:
    async def scenario() -> None:
        client = MCPClient(_settings(tmp_path))
        with pytest.raises(MCPToolNotFoundError):
            await client.execute_tool("missing_tool", {})

    asyncio.run(scenario())


def test_mcp_wrappers_delegate_to_mcp_client(tmp_path: Path) -> None:
    async def scenario() -> None:
        client = MCPClient(_settings(tmp_path))
        wrappers = await build_tool_wrappers(client)
        delete_wrapper = next(wrapper for wrapper in wrappers if wrapper.name == "delete_document")
        result = await delete_wrapper.ainvoke({"document_id": "doc-1"})
        assert result.tool_name == "delete_document"
        assert result.result["status"] == "accepted"
        assert result.result["document_id"] == "doc-1"

    asyncio.run(scenario())
