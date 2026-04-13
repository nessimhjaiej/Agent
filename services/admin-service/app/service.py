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

    def chat_events(self, payload: AdminChatRequest):
        session_id = self._sessions.ensure_session_id(payload.session_id)
        yield {
            "type": "status",
            "status": "started",
            "session_id": session_id,
            "message": payload.message,
        }

        response = self.chat(payload.model_copy(update={"session_id": session_id}))

        for item in response.activity:
            yield {
                "type": "activity",
                "session_id": session_id,
                "data": item.model_dump(),
            }

        if response.pending_action is not None:
            yield {
                "type": "confirmation",
                "session_id": session_id,
                "data": response.pending_action.model_dump(),
            }

        yield {
            "type": "response",
            "session_id": session_id,
            "data": response.model_dump(),
        }
        yield {
            "type": "done",
            "session_id": session_id,
        }

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
        self._sessions.save(
            session_id,
            {
                **self._memory_snapshot(session),
                "pending_action": None,
                "last_message": payload.message,
                "last_response": "Confirmed action executed successfully.",
                "last_result": result,
                "last_route": "workflow" if pending_payload.get("intent") == "workflow" else "mutate",
                "last_topic": str(pending_payload.get("tool") or ""),
                "access_token": access_token,
            },
        )
        self._sessions.append_turn(session_id, "user", payload.message)
        self._sessions.append_turn(session_id, "assistant", "Confirmed action executed successfully.")
        self._sessions.invalidate_tool_cache(session_id, _cache_invalidation_tags(str(pending_payload.get("tool") or "")))
        return AdminChatResponse(
            status="ok",
            mode="workflow" if pending_payload.get("intent") == "workflow" else "mutate",
            selected_mode=payload.selected_mode,
            session_id=session_id,
            message=payload.message,
            answer="Confirmed action executed successfully.",
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
                final_answer="Confirmed action executed successfully.",
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
