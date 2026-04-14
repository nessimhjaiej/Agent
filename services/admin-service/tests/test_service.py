from pathlib import Path
import sys

SERVICE_ROOT = Path(__file__).resolve().parents[1]
if str(SERVICE_ROOT) not in sys.path:
    sys.path.insert(0, str(SERVICE_ROOT))

from app.config import Settings  # noqa: E402
from app.schemas import AdminActivityItem, AdminAgentRunState, AdminChatRequest, AdminChatResponse  # noqa: E402
from app.service import AdminService  # noqa: E402


def _settings(tmp_path: Path) -> Settings:
    return Settings(
        openai_key="",
        session_store_path=str(tmp_path / "sessions.json"),
        max_iterations=8,
        max_tool_calls=8,
    )


def test_service_persists_pending_action(monkeypatch, tmp_path: Path) -> None:  # noqa: ANN001
    import app.service as service_module  # noqa: PLC0415

    service = AdminService(_settings(tmp_path))
    response = service.chat(AdminChatRequest(message="please reindex documents"))

    assert response.status == "needs_confirmation"
    assert response.session_id is not None
    stored = service_module.SessionStore(str(tmp_path / "sessions.json")).load(response.session_id)
    assert stored["pending_action"]["tool"] == "reindex_validated_documents"


def test_service_executes_confirmed_action(monkeypatch, tmp_path: Path) -> None:  # noqa: ANN001
    service = AdminService(_settings(tmp_path))
    first = service.chat(AdminChatRequest(message="please reindex documents"))

    monkeypatch.setattr(
        service._toolbox,
        "execute_pending_action",
        lambda pending_action: {"status": "ok", "index_result": {"document_id": "doc-1"}},
    )

    second = service.chat(
        AdminChatRequest(
            message="confirm",
            session_id=first.session_id,
            confirm=True,
        )
    )

    assert second.executed is True
    assert second.requires_confirmation is False
    assert second.result["index_result"]["document_id"] == "doc-1"


def test_service_executes_compound_confirmed_action(monkeypatch, tmp_path: Path) -> None:  # noqa: ANN001
    service = AdminService(_settings(tmp_path))
    session_id = service._sessions.ensure_session_id(None)
    service._sessions.save(
        session_id,
        {
            "pending_action": {
                "intent": "mutation",
                "tool": "compound_action",
                "arguments": {},
                "steps": [
                    {"tool": "update_repo_config", "arguments": {"service_name": "preprocessing", "changes": {"chunk_overlap": 115}}},
                    {"tool": "get_repo_config", "arguments": {"service_name": "retrieval"}},
                ],
            }
        },
    )

    monkeypatch.setattr(
        service._toolbox,
        "execute_pending_action",
        lambda pending_action: {
            "status": "ok",
            "results": [
                {
                    "tool": "update_repo_config",
                    "result": {
                        "scope": "preprocessing",
                        "updated": {"chunk_overlap": 115},
                    },
                },
                {
                    "tool": "get_repo_config",
                    "result": {
                        "scope": "retrieval",
                        "config": {
                            "ranker": "cross_encoder",
                            "rerank_top_n": 8,
                            "top_k_retrieve": 24,
                            "top_k_return": 6,
                        },
                    },
                },
            ],
        },
    )

    second = service.chat(AdminChatRequest(message="confirm", session_id=session_id, confirm=True))

    assert second.executed is True
    assert second.result["results"][0]["tool"] == "update_repo_config"
    assert second.result["results"][1]["tool"] == "get_repo_config"
    assert "chunk overlap set to 115" in second.answer
    assert "current reranking strategy is cross_encoder" in second.answer


def test_service_persists_run_evaluation_arguments(tmp_path: Path) -> None:
    service = AdminService(_settings(tmp_path))
    response = service.chat(AdminChatRequest(message="run evaluation"))
    assert response.pending_action is not None
    assert response.pending_action.tool == "run_evaluation"
    assert response.pending_action.arguments["dataset_path"] == "evals/sample_eval_dataset.json"


def test_service_plans_chunking_config_change(tmp_path: Path) -> None:
    service = AdminService(_settings(tmp_path))
    response = service.chat(AdminChatRequest(message="change chunk size to 900"))
    assert response.status == "needs_confirmation"
    assert response.pending_action is not None
    assert response.pending_action.tool == "update_repo_config"
    assert response.pending_action.arguments["service_name"] == "preprocessing"
    assert response.pending_action.arguments["changes"]["chunk_size"] == 900
    assert ".env" not in response.answer


def test_service_plans_chunk_strategy_change(tmp_path: Path) -> None:
    service = AdminService(_settings(tmp_path))
    response = service.chat(AdminChatRequest(message="set chunk_strategy to semantic"))

    assert response.status == "needs_confirmation"
    assert response.pending_action is not None
    assert response.pending_action.tool == "update_repo_config"
    assert response.pending_action.arguments["service_name"] == "preprocessing"
    assert response.pending_action.arguments["changes"]["chunk_strategy"] == "semantic"


def test_service_plans_chunk_overlap_change(tmp_path: Path) -> None:
    service = AdminService(_settings(tmp_path))
    response = service.chat(AdminChatRequest(message="update chunk_overlap to 64"))

    assert response.status == "needs_confirmation"
    assert response.pending_action is not None
    assert response.pending_action.tool == "update_repo_config"
    assert response.pending_action.arguments["service_name"] == "preprocessing"
    assert response.pending_action.arguments["changes"]["chunk_overlap"] == 64


def test_service_plans_hyphenated_cross_encoder_reranker_change(tmp_path: Path) -> None:
    service = AdminService(_settings(tmp_path))
    response = service.chat(AdminChatRequest(message="change the reranking strategy to cross-encoder"))

    assert response.status == "needs_confirmation"
    assert response.mode == "mutate"
    assert response.pending_action is not None
    assert response.pending_action.tool == "update_repo_config"
    assert response.pending_action.arguments["service_name"] == "retrieval"
    assert response.pending_action.arguments["changes"]["ranker"] == "cross_encoder"


def test_service_invalidates_cache_after_confirmed_change(monkeypatch, tmp_path: Path) -> None:  # noqa: ANN001
    import app.service as service_module  # noqa: PLC0415

    service = AdminService(_settings(tmp_path))
    session_id = service._sessions.ensure_session_id(None)
    service._sessions.save(
        session_id,
        {
            "pending_action": {
                "intent": "mutation",
                "tool": "update_repo_config",
                "arguments": {"service_name": "preprocessing", "changes": {"chunk_size": 900}},
                "steps": [],
            },
            "tool_cache": {
                "cache-key": {
                    "tool": "get_repo_config",
                    "args": {"service_name": "preprocessing"},
                    "result": {"scope": "preprocessing", "config": {"chunk_size": 750}},
                    "created_at": 1.0,
                    "ttl_seconds": 600,
                    "tags": ["config"],
                }
            },
        },
    )

    monkeypatch.setattr(
        service._toolbox,
        "execute_pending_action",
        lambda pending_action: {"status": "ok", "updated": {"chunk_size": 900}},
    )

    response = service.chat(AdminChatRequest(message="confirm", session_id=session_id, confirm=True))
    assert response.executed is True
    stored = service_module.SessionStore(str(tmp_path / "sessions.json")).load(session_id)
    assert stored.get("tool_cache", {}) == {}


def test_session_store_keeps_compact_memory(tmp_path: Path) -> None:
    service = AdminService(_settings(tmp_path))
    session_id = service._sessions.ensure_session_id(None)
    service._sessions.save(
        session_id,
        {
            "history": [{"role": "user", "content": f"msg-{index}"} for index in range(20)],
            "tool_cache": {
                f"k-{index}": {
                    "created_at": float(index),
                    "result": {"documents": list(range(20)), "reports": list(range(20))},
                }
                for index in range(20)
            },
            "last_result": {"route": "inspect", "tool_result": {"documents": list(range(20)), "reports": list(range(20))}},
            "noise": "drop-me",
        },
    )
    stored = service._sessions.load(session_id)
    assert len(stored["history"]) == 6
    assert len(stored["tool_cache"]) == 8
    assert "noise" not in stored


def test_service_accepts_stored_dict_history_on_follow_up(tmp_path: Path) -> None:
    service = AdminService(_settings(tmp_path))
    first = service.chat(AdminChatRequest(message="what are the available chunking methods"))
    second = service.chat(AdminChatRequest(message="and what is the current chunk size?", session_id=first.session_id))

    assert second.status == "ok"
    assert second.session_id == first.session_id
    assert second.answer


def test_chat_events_streams_activity_before_final_response(tmp_path: Path) -> None:
    service = AdminService(_settings(tmp_path))
    events = list(service.chat_events(AdminChatRequest(message="what are the available chunking methods")))

    activity_indexes = [index for index, event in enumerate(events) if event.get("type") == "activity"]
    response_indexes = [index for index, event in enumerate(events) if event.get("type") == "response"]

    assert activity_indexes
    assert response_indexes
    assert min(activity_indexes) < min(response_indexes)
