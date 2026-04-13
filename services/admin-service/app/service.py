from queue import Queue
from threading import Thread

from app.config import Settings
from app.graph import run_graph
from app.schemas import AdminActivityItem, AdminAgentRunState, AdminChatRequest, AdminChatResponse, AdminPendingAction
from app.session_store import SessionStore
from app.tools import AdminToolbox


class AdminService:
    def __init__(self, settings: Settings | None = None) -> None:
        self._settings = settings or Settings.from_env()
        self._sessions = SessionStore(self._settings.session_store_path)
        self._toolbox = AdminToolbox(self._settings)

    def chat(self, payload: AdminChatRequest) -> AdminChatResponse:
        return self.chat_with_progress(payload)

    def chat_events(self, payload: AdminChatRequest):
        session_id = self._sessions.ensure_session_id(payload.session_id)
        yield {
            "type": "status",
            "status": "started",
            "session_id": session_id,
            "message": payload.message,
        }

        event_queue: Queue[dict] = Queue()

        def _worker() -> None:
            try:
                response = self.chat_with_progress(
                    payload.model_copy(update={"session_id": session_id}),
                    lambda activity_item: event_queue.put(
                        {
                            "type": "activity",
                            "session_id": session_id,
                            "data": activity_item,
                        }
                    ),
                )
                if response.pending_action is not None:
                    event_queue.put(
                        {
                            "type": "confirmation",
                            "session_id": session_id,
                            "data": response.pending_action.model_dump(),
                        }
                    )
                event_queue.put(
                    {
                        "type": "response",
                        "session_id": session_id,
                        "data": response.model_dump(),
                    }
                )
            except Exception as exc:
                event_queue.put(
                    {
                        "type": "error",
                        "session_id": session_id,
                        "message": str(exc),
                    }
                )
            finally:
                event_queue.put({"type": "done", "session_id": session_id})

        worker = Thread(target=_worker, daemon=True)
        worker.start()

        while True:
            event = event_queue.get()
            yield event
            if event.get("type") == "done":
                break

    def chat_with_progress(self, payload: AdminChatRequest, progress_callback=None) -> AdminChatResponse:
        session_id = self._sessions.ensure_session_id(payload.session_id)
        session = self._sessions.load(session_id)
        access_token = payload.access_token or session.get("access_token")

        if payload.confirm:
            pending_payload = (
                payload.pending_action.model_dump()
                if payload.pending_action is not None
                else session.get("pending_action")
            )
            if isinstance(pending_payload, dict) and pending_payload.get("tool"):
                return self._execute_confirmed_action(session_id, payload, pending_payload, session, access_token)

        response = run_graph(
            payload.model_copy(
                update={
                    "session_id": session_id,
                    "access_token": access_token,
                    "chat_history": payload.chat_history or self._recent_history(session),
                }
            ),
            self._settings,
            session_context=self._memory_snapshot(session),
            progress_callback=progress_callback,
        )
        self._sessions.append_turn(session_id, "user", payload.message)
        self._sessions.append_turn(session_id, "assistant", response.answer)
        cache_updates = response.result.get("tool_cache_updates", {}) if isinstance(response.result, dict) else {}
        if isinstance(cache_updates, dict) and cache_updates:
            self._sessions.upsert_tool_cache(session_id, cache_updates)
        self._sessions.save(
            session_id,
            {
                **self._sessions.load(session_id),
                "last_message": payload.message,
                "pending_action": response.pending_action.model_dump() if response.pending_action else None,
                "last_response": response.answer,
                "last_route": response.mode,
                "last_topic": response.intent,
                "last_result": response.result,
                "access_token": access_token,
            },
        )
        return response

    def _execute_confirmed_action(
        self,
        session_id: str,
        payload: AdminChatRequest,
        pending_payload: dict,
        session: dict,
        access_token: str | None,
    ) -> AdminChatResponse:
        toolbox = self._toolbox if access_token == getattr(self._toolbox, "_access_token", None) else self._toolbox.with_access_token(access_token)
        result = toolbox.execute_pending_action(pending_payload)
        answer = _summarize_confirmed_result(pending_payload, result)
        self._sessions.save(
            session_id,
            {
                **self._memory_snapshot(session),
                "pending_action": None,
                "last_message": payload.message,
                "last_response": answer,
                "last_result": result,
                "last_route": "workflow" if pending_payload.get("intent") == "workflow" else "mutate",
                "last_topic": str(pending_payload.get("tool") or ""),
                "access_token": access_token,
            },
        )
        self._sessions.append_turn(session_id, "user", payload.message)
        self._sessions.append_turn(session_id, "assistant", answer)
        self._sessions.invalidate_tool_cache(session_id, _cache_invalidation_tags(str(pending_payload.get("tool") or "")))
        return AdminChatResponse(
            status="ok",
            mode="workflow" if pending_payload.get("intent") == "workflow" else "mutate",
            selected_mode=payload.selected_mode,
            session_id=session_id,
            message=payload.message,
            answer=answer,
            intent=str(pending_payload.get("intent") or "confirmed_action"),
            tool=str(pending_payload.get("tool") or ""),
            arguments=pending_payload.get("arguments", {}),
            requires_confirmation=False,
            executed=True,
            pending_action=None,
            citations=[],
            thinking_summary="A previously proposed action was confirmed and executed.",
            activity=[
                AdminActivityItem(
                    phase="confirmation",
                    status="completed",
                    title="Action confirmed",
                    detail="The pending action was approved and executed.",
                    tool=str(pending_payload.get("tool") or ""),
                    arguments=pending_payload.get("arguments", {}),
                )
            ],
            result=result,
            agent_run=AdminAgentRunState(
                status="completed",
                iteration_count=1,
                tool_call_count=1,
                max_iterations=self._settings.max_iterations,
                max_tool_calls=self._settings.max_tool_calls,
                facts={},
                observations=[],
                decision_history=[],
                proposed_steps=[],
                final_answer=answer,
                stop_reason="confirmed_action_executed",
            ),
        )

    def _recent_history(self, session: dict) -> list[dict]:
        history = session.get("history", [])
        return history[-6:] if isinstance(history, list) else []

    def _memory_snapshot(self, session: dict) -> dict:
        if not isinstance(session, dict):
            return {}
        return {
            "history": self._recent_history(session),
            "tool_cache": session.get("tool_cache", {}) if isinstance(session.get("tool_cache"), dict) else {},
            "pending_action": session.get("pending_action"),
            "last_message": session.get("last_message"),
            "last_response": session.get("last_response"),
            "last_route": session.get("last_route"),
            "last_topic": session.get("last_topic"),
            "last_result": session.get("last_result") if isinstance(session.get("last_result"), dict) else {},
            "access_token": session.get("access_token"),
            "cache_invalidated_at": session.get("cache_invalidated_at"),
        }


def _cache_invalidation_tags(tool_name: str) -> list[str]:
    if tool_name == "update_repo_config":
        return ["config"]
    if tool_name in {"reindex_document", "reindex_validated_documents", "delete_document_completely"}:
        return ["documents", "ingestion"]
    if tool_name in {"run_evaluation", "compare_evaluation_reports"}:
        return ["evaluation_reports"]
    return []


def _format_scope_summary(scope: str, config: dict) -> str:
    if not isinstance(config, dict):
        return f"current {scope} settings checked"

    if scope == "retrieval":
        ranker = config.get("ranker")
        rerank_top_n = config.get("rerank_top_n")
        top_k_retrieve = config.get("top_k_retrieve")
        top_k_return = config.get("top_k_return")
        parts = []
        if ranker is not None:
            if str(ranker).strip().lower() in {"none", "", "null"}:
                parts.append("reranking is currently disabled")
            else:
                parts.append(f"the current reranking strategy is {ranker}")
        if rerank_top_n is not None:
            parts.append(f"reranking reviews the top {rerank_top_n} retrieved chunks")
        if top_k_retrieve is not None and top_k_return is not None:
            parts.append(f"retrieval pulls {top_k_retrieve} candidates and returns {top_k_return}")
        return "; ".join(parts) if parts else "current retrieval settings checked"

    if scope == "preprocessing":
        strategy = config.get("chunk_strategy")
        chunk_size = config.get("chunk_size")
        chunk_overlap = config.get("chunk_overlap")
        parts = []
        if strategy is not None:
            parts.append(f"the current chunking strategy is {strategy}")
        if chunk_size is not None:
            parts.append(f"chunk size is {chunk_size}")
        if chunk_overlap is not None:
            parts.append(f"chunk overlap is {chunk_overlap}")
        return "; ".join(parts) if parts else "current preprocessing settings checked"

    return f"current {scope} settings checked: {config}"


def _format_update_summary(scope: str, updated: dict) -> str:
    if not isinstance(updated, dict) or not updated:
        return f"updated {scope} settings"

    if scope == "preprocessing":
        parts = []
        if "chunk_strategy" in updated:
            parts.append(f"chunking strategy set to {updated['chunk_strategy']}")
        if "chunk_size" in updated:
            parts.append(f"chunk size set to {updated['chunk_size']}")
        if "chunk_overlap" in updated:
            parts.append(f"chunk overlap set to {updated['chunk_overlap']}")
        return "; ".join(parts) if parts else f"updated {scope} settings"

    if scope == "retrieval":
        parts = []
        if "ranker" in updated:
            if str(updated["ranker"]).strip().lower() in {"none", "", "null"}:
                parts.append("reranking disabled")
            else:
                parts.append(f"reranking strategy set to {updated['ranker']}")
        if "rerank_top_n" in updated:
            parts.append(f"reranking top-N set to {updated['rerank_top_n']}")
        if "top_k_retrieve" in updated:
            parts.append(f"retrieval top-K set to {updated['top_k_retrieve']}")
        return "; ".join(parts) if parts else f"updated {scope} settings"

    rendered = ", ".join(f"{key}={value}" for key, value in updated.items())
    return f"updated {scope} settings: {rendered}"


def _summarize_confirmed_result(pending_payload: dict, result: dict) -> str:
    tool_name = str(pending_payload.get("tool") or "")
    if tool_name == "compound_action":
        parts = []
        for item in result.get("results", []) if isinstance(result, dict) else []:
            if not isinstance(item, dict):
                continue
            step_tool = str(item.get("tool") or "")
            step_result = item.get("result", {})
            if step_tool == "update_repo_config" and isinstance(step_result, dict):
                scope = step_result.get("scope") or "system"
                updated = step_result.get("updated", {})
                parts.append(_format_update_summary(str(scope), updated))
            elif step_tool == "get_repo_config" and isinstance(step_result, dict):
                scope = step_result.get("scope") or "system"
                config = step_result.get("config", {})
                parts.append(_format_scope_summary(str(scope), config))
            elif step_tool == "get_chunking_methods" and isinstance(step_result, dict):
                parts.append(
                    f"chunking options checked; current strategy is {step_result.get('current_strategy')}"
                )
            elif step_tool == "run_evaluation" and isinstance(step_result, dict):
                report = step_result.get("report", {})
                parts.append(f"evaluation completed: {report.get('report_id', 'report created')}")
            elif step_tool == "compare_evaluation_reports" and isinstance(step_result, dict):
                parts.append("evaluation comparison completed")
            elif step_tool in {"reindex_document", "reindex_validated_documents"} and isinstance(step_result, dict):
                parts.append("reindex completed")
            else:
                parts.append(f"{step_tool} completed")
        if parts:
            return "Done: " + "; ".join(parts) + "."
        return "Done. The planned actions were executed."

    if tool_name == "update_repo_config" and isinstance(result, dict):
        scope = result.get("scope") or "system"
        updated = result.get("updated", {})
        return f"Done. I {_format_update_summary(str(scope), updated)}."
    if tool_name == "get_repo_config" and isinstance(result, dict):
        scope = result.get("scope") or "system"
        config = result.get("config", {})
        return f"Done. {_format_scope_summary(str(scope), config).capitalize()}."
    if tool_name in {"reindex_document", "reindex_validated_documents"}:
        return "Done. The reindex workflow completed."
    if tool_name == "run_evaluation":
        report = result.get("report", {}) if isinstance(result, dict) else {}
        return f"Done. The evaluation completed and saved report {report.get('report_id', '')}.".strip()
    if tool_name == "compare_evaluation_reports":
        return "Done. The evaluation comparison completed."
    return "Confirmed action executed successfully."
