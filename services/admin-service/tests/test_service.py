from pathlib import Path
import sys

SERVICE_ROOT = Path(__file__).resolve().parents[1]
if str(SERVICE_ROOT) not in sys.path:
    sys.path.insert(0, str(SERVICE_ROOT))

from app.config import Settings  # noqa: E402
from app.schemas import AdminActivityItem, AdminAgentRunState, AdminChatRequest, AdminChatResponse  # noqa: E402
import app.service as service_module  # noqa: E402
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


def test_service_emits_info_event_for_confirmed_mutation(monkeypatch, tmp_path: Path) -> None:  # noqa: ANN001
    service = AdminService(_settings(tmp_path))
    first = service.chat(AdminChatRequest(message="please reindex documents"))

    monkeypatch.setattr(
        service._toolbox,
        "execute_pending_action",
        lambda pending_action: {"status": "ok", "index_result": {"document_id": "doc-1"}},
    )

    emitted: list[dict] = []

    def _capture_emit(settings, **kwargs):  # noqa: ANN001
        emitted.append(kwargs)

    monkeypatch.setattr(service_module, "emit_security_event", _capture_emit)

    second = service.chat(
        AdminChatRequest(
            message="confirm",
            session_id=first.session_id,
            confirm=True,
            actor_user_id="admin-1",
            actor_email="admin@example.com",
            actor_role="admin",
        )
    )

    assert second.executed is True
    assert len(emitted) == 1
    assert emitted[0]["event_type"] == "ADMIN_MUTATION_CONFIRMED"
    assert emitted[0]["severity"] == "info"
    assert emitted[0]["metadata"]["email"] == "admin@example.com"
    assert emitted[0]["metadata"]["tool"] == "reindex_validated_documents"
    assert emitted[0]["metadata"]["session_id"] == first.session_id


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

    def _exec(pending_action: dict) -> dict:
        tool = pending_action.get("tool")
        if tool == "update_repo_config":
            return {
                "scope": "preprocessing",
                "updated": {"chunk_overlap": 115},
            }
        if tool == "get_repo_config":
            return {
                "scope": "retrieval",
                "config": {
                    "ranker": "cross_encoder",
                    "rerank_top_n": 8,
                    "top_k_retrieve": 24,
                    "top_k_return": 6,
                },
            }
        return {"status": "ok"}

    monkeypatch.setattr(service._toolbox, "execute_pending_action", _exec)

    second = service.chat(AdminChatRequest(message="confirm", session_id=session_id, confirm=True))

    assert second.executed is True
    assert second.result["executed_steps"][0]["tool"] == "update_repo_config"
    assert second.result["executed_steps"][1]["tool"] == "get_repo_config"
    assert "chunk overlap set to 115" in second.answer
    assert "current reranking strategy is cross_encoder" in second.answer


def test_service_runs_read_only_steps_before_first_mutation_confirmation(monkeypatch, tmp_path: Path) -> None:  # noqa: ANN001
    import app.service as service_module  # noqa: PLC0415

    service = AdminService(_settings(tmp_path))

    def _fake_run_graph(payload, settings, session_context=None, progress_callback=None):  # noqa: ANN001
        return AdminChatResponse(
            status="needs_confirmation",
            mode="mutate",
            selected_mode=payload.selected_mode,
            session_id=payload.session_id,
            message=payload.message,
            answer="initial",
            intent="mutation",
            tool="compound_action",
            arguments={},
            requires_confirmation=True,
            executed=False,
            pending_action={
                "intent": "mutation",
                "tool": "compound_action",
                "arguments": {},
                "steps": [
                    {"tool": "get_repo_config", "arguments": {"service_name": "embedding"}},
                    {"tool": "update_repo_config", "arguments": {"service_name": "retrieval", "changes": {"ranker": "none"}}},
                ],
            },
            citations=[],
            thinking_summary="test",
            activity=[],
            result={"route": "mutate", "tool_result": None, "tool_cache_updates": {}},
            agent_run=AdminAgentRunState(status="paused_for_confirmation"),
        )

    monkeypatch.setattr(service_module, "run_graph", _fake_run_graph)
    monkeypatch.setattr(
        service._toolbox,
        "execute_pending_action",
        lambda pending_action: {
            "scope": "embedding",
            "config": {"embedding_model": "text-embedding-3-small"},
        }
        if pending_action.get("tool") == "get_repo_config"
        else {"status": "ok"},
    )

    response = service.chat(
        AdminChatRequest(message="tell embeddings config then change reranking strategy to none"),
    )

    assert response.status == "needs_confirmation"
    assert response.pending_action is not None
    assert response.pending_action.tool == "update_repo_config"
    assert response.pending_action.arguments["changes"]["ranker"] == "none"
    assert response.answer.startswith("## Next Action")
    assert "embedding model is text-embedding-3-small" not in response.answer


def test_service_keeps_reranking_advantages_and_confirmation_for_compound_request(monkeypatch, tmp_path: Path) -> None:  # noqa: ANN001
    import app.service as service_module  # noqa: PLC0415

    service = AdminService(_settings(tmp_path))

    def _fake_run_graph(payload, settings, session_context=None, progress_callback=None):  # noqa: ANN001
        return AdminChatResponse(
            status="needs_confirmation",
            mode="mutate",
            selected_mode=payload.selected_mode,
            session_id=payload.session_id,
            message=payload.message,
            answer="initial",
            intent="mutation",
            tool="compound_action",
            arguments={},
            requires_confirmation=True,
            executed=False,
            pending_action={
                "intent": "mutation",
                "tool": "compound_action",
                "arguments": {},
                "steps": [
                    {"tool": "get_reranking_methods", "arguments": {}},
                    {"tool": "update_repo_config", "arguments": {"service_name": "preprocessing", "changes": {"chunk_strategy": "semantic"}}},
                ],
            },
            citations=[],
            thinking_summary="test",
            activity=[],
            result={"route": "mutate", "tool_result": None, "tool_cache_updates": {}},
            agent_run=AdminAgentRunState(status="paused_for_confirmation"),
        )

    monkeypatch.setattr(service_module, "run_graph", _fake_run_graph)
    monkeypatch.setattr(
        service._toolbox,
        "execute_pending_action",
        lambda pending_action: {
            "status": "ok",
            "scope": "retrieval",
            "current_default_ranker_type": "llm_batch",
            "methods": [
                {"name": "cross_encoder", "exists": True, "implemented": True},
                {"name": "llm_batch", "exists": True, "implemented": True},
                {"name": "none", "exists": True, "implemented": True},
            ],
        }
        if pending_action.get("tool") == "get_reranking_methods"
        else {"status": "ok"},
    )

    response = service.chat(
        AdminChatRequest(
            message="i want the advantages of all available reranking strategies and update chunking strategy to sementic",
        ),
    )

    assert response.status == "needs_confirmation"
    assert response.pending_action is not None
    assert response.pending_action.tool == "update_repo_config"
    assert response.pending_action.arguments["service_name"] == "preprocessing"
    assert response.pending_action.arguments["changes"]["chunk_strategy"] == "semantic"
    assert len(response.result["executed_steps"]) == 1
    assert response.result["executed_steps"][0]["tool"] == "get_reranking_methods"
    assert response.answer.startswith("## Next Action")
    assert "Advantages of Available Reranking Strategies" not in response.answer
    assert "Information Gathered" not in response.answer
    assert "update the preprocessing settings" in response.answer


def test_service_rejects_pending_action_and_clears_session(tmp_path: Path) -> None:
    service = AdminService(_settings(tmp_path))
    session_id = service._sessions.ensure_session_id(None)
    service._sessions.save(
        session_id,
        {
            "pending_action": {
                "intent": "mutation",
                "tool": "update_repo_config",
                "arguments": {"service_name": "preprocessing", "changes": {"chunk_strategy": "late"}},
                "steps": [],
            }
        },
    )

    response = service.chat(
        AdminChatRequest(message="reject", session_id=session_id, reject=True)
    )

    assert response.status == "ok"
    assert response.requires_confirmation is False
    assert response.pending_action is None
    assert "Action Canceled" in response.answer
    stored = service._sessions.load(session_id)
    assert stored["pending_action"] is None
    assert stored["pending_executed_steps"] == []


def test_service_reject_summarizes_completed_and_rejected_steps(tmp_path: Path) -> None:
    service = AdminService(_settings(tmp_path))
    session_id = service._sessions.ensure_session_id(None)
    service._sessions.save(
        session_id,
        {
            "last_message": "i want the advantages of all available chunking strategies and update chunking strategy to semantic",
            "pending_action": {
                "intent": "mutation",
                "tool": "update_repo_config",
                "arguments": {"service_name": "retrieval", "changes": {"ranker": "none"}},
                "steps": [],
            },
            "pending_executed_steps": [
                {
                    "tool": "update_repo_config",
                    "result": {
                        "status": "ok",
                        "scope": "preprocessing",
                        "updated": {"chunk_strategy": "semantic"},
                    },
                },
                {
                    "tool": "get_chunking_methods",
                    "result": {
                        "status": "ok",
                        "scope": "preprocessing",
                        "current_strategy": "semantic",
                        "current_chunk_size": 750,
                        "current_chunk_overlap": 120,
                        "methods": [
                            {"name": "late", "exists": True, "implemented": True},
                            {"name": "overlap", "exists": True, "implemented": True},
                            {"name": "semantic", "exists": True, "implemented": True},
                        ],
                    },
                },
            ],
        },
    )

    response = service.chat(
        AdminChatRequest(message="reject", session_id=session_id, reject=True)
    )

    assert response.status == "ok"
    assert "chunking strategy set to semantic" in response.answer
    assert "Rejected Action" in response.answer
    assert "update the retrieval settings with {'ranker': 'none'}" in response.answer


def test_service_reject_advances_to_next_mutation_in_chain(tmp_path: Path) -> None:
    service = AdminService(_settings(tmp_path))
    session_id = service._sessions.ensure_session_id(None)
    service._sessions.save(
        session_id,
        {
            "pending_action": {
                "intent": "mutation",
                "tool": "update_repo_config",
                "arguments": {"service_name": "retrieval", "changes": {"ranker": "none"}},
                "steps": [
                    {
                        "tool": "update_repo_config",
                        "arguments": {"service_name": "preprocessing", "changes": {"chunk_strategy": "late"}},
                    }
                ],
            }
        },
    )

    response = service.chat(
        AdminChatRequest(message="reject", session_id=session_id, reject=True)
    )

    assert response.status == "needs_confirmation"
    assert response.requires_confirmation is True
    assert response.pending_action is not None
    assert response.pending_action.tool == "update_repo_config"
    assert response.pending_action.arguments["service_name"] == "preprocessing"
    assert response.pending_action.arguments["changes"]["chunk_strategy"] == "late"
    assert response.answer.startswith("## Next Action")


def test_service_confirm_completes_all_requested_tasks_from_ledger(monkeypatch, tmp_path: Path) -> None:  # noqa: ANN001
    service = AdminService(_settings(tmp_path))
    session_id = service._sessions.ensure_session_id(None)
    service._sessions.save(
        session_id,
        {
            "last_message": "i want the advantages of all available reranking strategies and update chunking strategy to semantic",
            "pending_action": {
                "intent": "mutation",
                "tool": "update_repo_config",
                "arguments": {"service_name": "preprocessing", "changes": {"chunk_strategy": "semantic"}},
                "steps": [],
                "task_index": 1,
                "workflow_tasks": [
                    {
                        "task_id": "task_1",
                        "kind": "advice",
                        "clause": "advantages of all available reranking strategies",
                        "status": "completed",
                        "steps": [{"tool": "get_reranking_methods", "arguments": {}}],
                        "outcome": {
                            "executed_steps": [
                                {
                                    "tool": "get_reranking_methods",
                                    "result": {
                                        "status": "ok",
                                        "scope": "retrieval",
                                        "current_default_ranker_type": "llm_batch",
                                        "methods": [
                                            {"name": "cross_encoder", "exists": True, "implemented": True},
                                            {"name": "llm_batch", "exists": True, "implemented": True},
                                            {"name": "none", "exists": True, "implemented": True},
                                        ],
                                    },
                                }
                            ]
                        },
                    },
                    {
                        "task_id": "task_2",
                        "kind": "mutation",
                        "clause": "update chunking strategy to semantic",
                        "status": "pending",
                        "steps": [{"tool": "update_repo_config", "arguments": {"service_name": "preprocessing", "changes": {"chunk_strategy": "semantic"}}}],
                        "outcome": {},
                    },
                ],
            },
            "workflow_tasks": [
                {
                    "task_id": "task_1",
                    "kind": "advice",
                    "clause": "advantages of all available reranking strategies",
                    "status": "completed",
                    "steps": [{"tool": "get_reranking_methods", "arguments": {}}],
                    "outcome": {
                        "executed_steps": [
                            {
                                "tool": "get_reranking_methods",
                                "result": {
                                    "status": "ok",
                                    "scope": "retrieval",
                                    "current_default_ranker_type": "llm_batch",
                                    "methods": [
                                        {"name": "cross_encoder", "exists": True, "implemented": True},
                                        {"name": "llm_batch", "exists": True, "implemented": True},
                                        {"name": "none", "exists": True, "implemented": True},
                                    ],
                                },
                            }
                        ]
                    },
                },
                {
                    "task_id": "task_2",
                    "kind": "mutation",
                    "clause": "update chunking strategy to semantic",
                    "status": "pending",
                    "steps": [{"tool": "update_repo_config", "arguments": {"service_name": "preprocessing", "changes": {"chunk_strategy": "semantic"}}}],
                    "outcome": {},
                },
            ],
            "active_task_index": 1,
        },
    )

    monkeypatch.setattr(
        service._toolbox,
        "execute_pending_action",
        lambda pending_action: {
            "status": "ok",
            "scope": "preprocessing",
            "updated": {"chunk_strategy": "semantic"},
        },
    )

    response = service.chat(AdminChatRequest(message="confirm", session_id=session_id, confirm=True))

    assert response.status == "ok"
    assert "cross_encoder" in response.answer
    assert "llm_batch" in response.answer
    assert "chunking strategy set to semantic" in response.answer


def test_service_reject_keeps_completed_info_tasks_in_final_summary(tmp_path: Path) -> None:
    service = AdminService(_settings(tmp_path))
    session_id = service._sessions.ensure_session_id(None)
    workflow_tasks = [
        {
            "task_id": "task_1",
            "kind": "advice",
            "clause": "advantages of all available reranking strategies",
            "status": "completed",
            "steps": [{"tool": "get_reranking_methods", "arguments": {}}],
            "outcome": {
                "executed_steps": [
                    {
                        "tool": "get_reranking_methods",
                        "result": {
                            "status": "ok",
                            "scope": "retrieval",
                            "current_default_ranker_type": "llm_batch",
                            "methods": [
                                {"name": "cross_encoder", "exists": True, "implemented": True},
                                {"name": "llm_batch", "exists": True, "implemented": True},
                                {"name": "none", "exists": True, "implemented": True},
                            ],
                        },
                    }
                ]
            },
        },
        {
            "task_id": "task_2",
            "kind": "mutation",
            "clause": "update chunking strategy to semantic",
            "status": "pending",
            "steps": [{"tool": "update_repo_config", "arguments": {"service_name": "preprocessing", "changes": {"chunk_strategy": "semantic"}}}],
            "outcome": {},
        },
    ]
    service._sessions.save(
        session_id,
        {
            "last_message": "i want the advantages of all available reranking strategies and update chunking strategy to semantic",
            "pending_action": {
                "intent": "mutation",
                "tool": "update_repo_config",
                "arguments": {"service_name": "preprocessing", "changes": {"chunk_strategy": "semantic"}},
                "steps": [],
                "task_index": 1,
                "workflow_tasks": workflow_tasks,
            },
            "workflow_tasks": workflow_tasks,
            "active_task_index": 1,
        },
    )

    response = service.chat(AdminChatRequest(message="reject", session_id=session_id, reject=True))

    assert response.status == "ok"
    assert "cross_encoder" in response.answer
    assert "llm_batch" in response.answer
    assert "Rejected Action" in response.answer
    assert "semantic" in response.answer


def test_service_confirm_keeps_prior_read_step_summary(monkeypatch, tmp_path: Path) -> None:  # noqa: ANN001
    service = AdminService(_settings(tmp_path))
    session_id = service._sessions.ensure_session_id(None)
    service._sessions.save(
        session_id,
        {
            "pending_action": {
                "intent": "mutation",
                "tool": "update_repo_config",
                "arguments": {"service_name": "retrieval", "changes": {"ranker": "none"}},
                "steps": [],
            },
            "pending_executed_steps": [
                {
                    "tool": "get_repo_config",
                    "result": {
                        "scope": "embedding",
                        "config": {
                            "embedding_model": None,
                            "embedding_dimensions": None,
                            "embedding_batch_size": None,
                        },
                    },
                }
            ],
        },
    )

    monkeypatch.setattr(
        service._toolbox,
        "execute_pending_action",
        lambda pending_action: {
            "scope": "retrieval",
            "updated": {"default_ranker_type": "none"},
        },
    )

    response = service.chat(AdminChatRequest(message="confirm", session_id=session_id, confirm=True))
    assert response.status == "ok"
    assert "embedding model is unset" in response.answer
    assert "reranking disabled" in response.answer


def test_service_confirm_prefers_latest_read_state_in_summary(monkeypatch, tmp_path: Path) -> None:  # noqa: ANN001
    service = AdminService(_settings(tmp_path))
    session_id = service._sessions.ensure_session_id(None)
    service._sessions.save(
        session_id,
        {
            "last_message": "i want the advantages of all available chunking strategies and update chunking strategy to semantic",
            "pending_action": {
                "intent": "mutation",
                "tool": "update_repo_config",
                "arguments": {"service_name": "preprocessing", "changes": {"chunk_strategy": "semantic"}},
                "steps": [{"tool": "get_chunking_methods", "arguments": {}}],
            },
            "pending_executed_steps": [
                {
                    "tool": "get_chunking_methods",
                    "result": {
                        "status": "ok",
                        "scope": "preprocessing",
                        "current_strategy": "late",
                        "current_chunk_size": 750,
                        "current_chunk_overlap": 120,
                        "methods": [
                            {"name": "late", "exists": True, "implemented": True},
                            {"name": "overlap", "exists": True, "implemented": True},
                            {"name": "semantic", "exists": True, "implemented": True},
                        ],
                    },
                }
            ],
        },
    )

    def _exec(pending_action: dict) -> dict:
        tool = pending_action.get("tool")
        if tool == "update_repo_config":
            return {
                "status": "ok",
                "scope": "preprocessing",
                "updated": {"chunk_strategy": "semantic"},
            }
        if tool == "get_chunking_methods":
            return {
                "status": "ok",
                "scope": "preprocessing",
                "current_strategy": "semantic",
                "current_chunk_size": 750,
                "current_chunk_overlap": 120,
                "methods": [
                    {"name": "late", "exists": True, "implemented": True},
                    {"name": "overlap", "exists": True, "implemented": True},
                    {"name": "semantic", "exists": True, "implemented": True},
                ],
            }
        return {"status": "ok"}

    monkeypatch.setattr(service._toolbox, "execute_pending_action", _exec)

    response = service.chat(AdminChatRequest(message="confirm", session_id=session_id, confirm=True))

    assert response.status == "ok"
    assert response.answer.count("available chunking strategies") == 1
    assert "current strategy: `semantic`" in response.answer
    assert "current strategy: `late`" not in response.answer


def test_service_completed_mutation_summary_falls_back_without_openai_key(monkeypatch, tmp_path: Path) -> None:  # noqa: ANN001
    service = AdminService(_settings(tmp_path))
    session_id = service._sessions.ensure_session_id(None)
    service._sessions.save(
        session_id,
        {
            "pending_action": {
                "intent": "mutation",
                "tool": "update_repo_config",
                "arguments": {"service_name": "preprocessing", "changes": {"chunk_strategy": "semantic"}},
                "steps": [],
            }
        },
    )

    monkeypatch.setattr(
        service._toolbox,
        "execute_pending_action",
        lambda pending_action: {
            "status": "ok",
            "scope": "preprocessing",
            "updated": {"chunk_strategy": "semantic"},
        },
    )

    response = service.chat(AdminChatRequest(message="confirm", session_id=session_id, confirm=True))

    assert response.status == "ok"
    assert "chunking strategy set to semantic" in response.answer


def test_service_completed_mutation_summary_uses_llm_when_available(monkeypatch, tmp_path: Path) -> None:  # noqa: ANN001
    import app.service as service_module  # noqa: PLC0415

    settings = Settings(
        openai_key="test-key",
        session_store_path=str(tmp_path / "sessions.json"),
        max_iterations=8,
        max_tool_calls=8,
    )
    service = AdminService(settings)
    session_id = service._sessions.ensure_session_id(None)
    service._sessions.save(
        session_id,
        {
            "pending_action": {
                "intent": "mutation",
                "tool": "update_repo_config",
                "arguments": {"service_name": "preprocessing", "changes": {"chunk_strategy": "semantic"}},
                "steps": [],
            }
        },
    )

    class _FakeModel:
        def invoke(self, messages):  # noqa: ANN001
            class _Response:
                content = "## Summary\n\nLLM final summary."

            return _Response()

    monkeypatch.setattr(service_module, "_make_summary_model", lambda settings: _FakeModel())
    monkeypatch.setattr(
        service._toolbox,
        "execute_pending_action",
        lambda pending_action: {
            "status": "ok",
            "scope": "preprocessing",
            "updated": {"chunk_strategy": "semantic"},
        },
    )

    response = service.chat(AdminChatRequest(message="confirm", session_id=session_id, confirm=True))

    assert response.status == "ok"
    assert response.answer == "## Summary\n\nLLM final summary."


def test_service_confirm_keeps_prior_read_step_summary_across_persisted_streams(monkeypatch, tmp_path: Path) -> None:  # noqa: ANN001
    service = AdminService(_settings(tmp_path))
    session_id = service._sessions.ensure_session_id(None)
    service._sessions.save(
        session_id,
        {
            "pending_action": {
                "intent": "mutation",
                "tool": "update_repo_config",
                "arguments": {"service_name": "retrieval", "changes": {"ranker": "cross_encoder"}},
                "steps": [],
            },
            "pending_executed_steps": [
                {
                    "tool": "get_repo_config",
                    "result": {
                        "scope": "embedding",
                        "config": {
                            "embedding_model": None,
                            "embedding_dimensions": None,
                            "embedding_batch_size": None,
                        },
                    },
                }
            ],
        },
    )
    # Simulate a fresh request load (next stream): data must survive compaction in session store.
    reloaded = service._sessions.load(session_id)
    assert isinstance(reloaded.get("pending_executed_steps"), list)
    assert len(reloaded["pending_executed_steps"]) == 1

    monkeypatch.setattr(
        service._toolbox,
        "execute_pending_action",
        lambda pending_action: {
            "scope": "retrieval",
            "updated": {"default_ranker_type": "cross_encoder"},
        },
    )

    response = service.chat(AdminChatRequest(message="confirm", session_id=session_id, confirm=True))
    assert response.status == "ok"
    assert "embedding model is unset" in response.answer
    assert "reranking strategy set to cross_encoder" in response.answer


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


def test_service_plans_follow_up_reranker_disable_from_pending_context(tmp_path: Path) -> None:
    service = AdminService(_settings(tmp_path))
    session_id = service._sessions.ensure_session_id(None)
    service._sessions.save(
        session_id,
        {
            "last_route": "mutate",
            "last_topic": "reranking_strategy",
            "pending_action": {
                "intent": "mutation",
                "tool": "update_repo_config",
                "arguments": {"service_name": "retrieval", "changes": {"ranker": "cross_encoder"}},
                "steps": [],
            },
        },
    )

    response = service.chat(AdminChatRequest(message="switch it to none", session_id=session_id))

    assert response.status == "needs_confirmation"
    assert response.mode == "mutate"
    assert response.pending_action is not None
    assert response.pending_action.tool == "update_repo_config"
    assert response.pending_action.arguments["service_name"] == "retrieval"
    assert response.pending_action.arguments["changes"]["ranker"] == "none"


def test_service_capability_follow_up_ignores_prior_mutation_context(tmp_path: Path) -> None:
    service = AdminService(_settings(tmp_path))
    session_id = service._sessions.ensure_session_id(None)
    service._sessions.save(
        session_id,
        {
            "last_route": "mutate",
            "last_topic": "documents",
            "pending_action": {
                "intent": "mutation",
                "tool": "delete_document_completely",
                "arguments": {"document_id": "doc-1"},
                "steps": [],
            },
        },
    )

    response = service.chat(AdminChatRequest(message="i said what can you do?", session_id=session_id))

    assert response.status == "ok"
    assert response.mode == "advisory"
    assert response.requires_confirmation is False
    assert response.pending_action is None
    assert "Read-Only Inspections" in response.answer
    stored = service._sessions.load(session_id)
    assert stored["pending_action"] is None
    assert stored["last_topic"] == "capabilities"


def test_service_plans_follow_up_reranker_disable_from_cached_methods(tmp_path: Path) -> None:
    service = AdminService(_settings(tmp_path))
    session_id = service._sessions.ensure_session_id(None)
    service._sessions.save(
        session_id,
        {
            "last_route": "inspect",
            "last_topic": "reranking_strategy",
            "last_result": {
                "route": "inspect",
                "tool_result": {
                    "status": "ok",
                    "scope": "retrieval",
                    "current_default_ranker_type": "cross_encoder",
                    "methods": [
                        {"name": "cross_encoder", "exists": True, "implemented": True},
                        {"name": "llm_batch", "exists": True, "implemented": True},
                        {"name": "none", "exists": True, "implemented": True},
                    ],
                },
            },
        },
    )

    response = service.chat(AdminChatRequest(message="switch it to none", session_id=session_id))

    assert response.status == "needs_confirmation"
    assert response.mode == "mutate"
    assert response.pending_action is not None
    assert response.pending_action.tool == "update_repo_config"
    assert response.pending_action.arguments["service_name"] == "retrieval"
    assert response.pending_action.arguments["changes"]["ranker"] == "none"


def test_service_uses_semantic_plan_for_french_reranker_follow_up(monkeypatch, tmp_path: Path) -> None:  # noqa: ANN001
    import app.graph as graph_module  # noqa: PLC0415

    service = AdminService(_settings(tmp_path))
    session_id = service._sessions.ensure_session_id(None)
    service._sessions.save(
        session_id,
        {
            "last_route": "inspect",
            "last_topic": "reranking_strategy",
            "last_result": {
                "route": "inspect",
                "tool_result": {
                    "status": "ok",
                    "scope": "retrieval",
                    "current_default_ranker_type": "cross_encoder",
                    "methods": [
                        {"name": "cross_encoder", "exists": True, "implemented": True},
                        {"name": "llm_batch", "exists": True, "implemented": True},
                        {"name": "none", "exists": True, "implemented": True},
                    ],
                },
            },
        },
    )

    monkeypatch.setattr(
        graph_module,
        "_semantic_action_planner",
        lambda message, settings, session_context=None: graph_module.SemanticActionPlan(
            action_type="update_config",
            service_name="retrieval",
            changes={"ranker": "llm_batch"},
        ),
    )

    response = service.chat(AdminChatRequest(message="remplacer la avec llm batch", session_id=session_id))

    assert response.status == "needs_confirmation"
    assert response.mode == "mutate"
    assert response.pending_action is not None
    assert response.pending_action.tool == "update_repo_config"
    assert response.pending_action.arguments["service_name"] == "retrieval"
    assert response.pending_action.arguments["changes"]["ranker"] == "llm_batch"


def test_service_plans_remplacer_la_avec_llm_batch(tmp_path: Path) -> None:
    service = AdminService(_settings(tmp_path))
    session_id = service._sessions.ensure_session_id(None)
    service._sessions.save(
        session_id,
        {
            "last_route": "inspect",
            "last_topic": "reranking_strategy",
            "last_result": {
                "route": "inspect",
                "tool_result": {
                    "status": "ok",
                    "scope": "retrieval",
                    "current_default_ranker_type": "cross_encoder",
                    "methods": [
                        {"name": "cross_encoder", "exists": True, "implemented": True},
                        {"name": "llm_batch", "exists": True, "implemented": True},
                        {"name": "none", "exists": True, "implemented": True},
                    ],
                },
            },
        },
    )

    response = service.chat(AdminChatRequest(message="remplacer la avec llm batch", session_id=session_id))

    assert response.status == "needs_confirmation"
    assert response.mode == "mutate"
    assert response.pending_action is not None
    assert response.pending_action.tool == "update_repo_config"
    assert response.pending_action.arguments["service_name"] == "retrieval"
    assert response.pending_action.arguments["changes"]["ranker"] == "llm_batch"


def test_service_plans_remplacer_reranking_strategy_with_llm_batch(tmp_path: Path) -> None:
    service = AdminService(_settings(tmp_path))
    response = service.chat(AdminChatRequest(message="remplacer la strategie de reranking par llm batch"))

    assert response.status == "needs_confirmation"
    assert response.mode == "mutate"
    assert response.pending_action is not None
    assert response.pending_action.tool == "update_repo_config"
    assert response.pending_action.arguments["service_name"] == "retrieval"
    assert response.pending_action.arguments["changes"]["ranker"] == "llm_batch"


def test_service_plans_value_only_follow_up_without_trigger_keyword(tmp_path: Path) -> None:
    service = AdminService(_settings(tmp_path))
    session_id = service._sessions.ensure_session_id(None)
    service._sessions.save(
        session_id,
        {
            "last_route": "inspect",
            "last_topic": "reranking_strategy",
            "last_result": {
                "route": "inspect",
                "tool_result": {
                    "status": "ok",
                    "scope": "retrieval",
                    "current_default_ranker_type": "cross_encoder",
                    "methods": [
                        {"name": "cross_encoder", "exists": True, "implemented": True},
                        {"name": "llm_batch", "exists": True, "implemented": True},
                        {"name": "none", "exists": True, "implemented": True},
                    ],
                },
            },
        },
    )

    response = service.chat(AdminChatRequest(message="llm batch", session_id=session_id))

    assert response.status == "needs_confirmation"
    assert response.mode == "mutate"
    assert response.pending_action is not None
    assert response.pending_action.tool == "update_repo_config"
    assert response.pending_action.arguments["service_name"] == "retrieval"
    assert response.pending_action.arguments["changes"]["ranker"] == "llm_batch"


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
            "pending_executed_steps": [{"tool": "get_repo_config", "result": {"scope": "embedding"}} for _ in range(20)],
            "noise": "drop-me",
        },
    )
    stored = service._sessions.load(session_id)
    assert len(stored["history"]) == 6
    assert len(stored["tool_cache"]) == 8
    assert len(stored["pending_executed_steps"]) == 10
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
