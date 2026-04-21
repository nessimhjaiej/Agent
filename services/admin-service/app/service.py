from queue import Queue
from threading import Thread
from typing import Any
import re

from app.config import Settings
from app.graph import run_graph
from app.schemas import AdminActivityItem, AdminAgentRunState, AdminChatRequest, AdminChatResponse, AdminPendingAction
from app.session_store import SessionStore
from app.tools import AdminToolbox


MUTATING_TOOLS = {
    "update_repo_config",
    "delete_document_completely",
    "reindex_document",
    "reindex_validated_documents",
    "run_evaluation",
    "compare_evaluation_reports",
}


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
        language = _detect_language(payload.message, session.get("preferred_language"))

        if payload.confirm:
            pending_payload = (
                payload.pending_action.model_dump()
                if payload.pending_action is not None
                else session.get("pending_action")
            )
            if isinstance(pending_payload, dict) and pending_payload.get("tool"):
                return self._execute_confirmed_action(
                    session_id,
                    payload,
                    pending_payload,
                    session,
                    access_token,
                    language,
                    progress_callback,
                )

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
        toolbox = self._toolbox if access_token == getattr(self._toolbox, "_access_token", None) else self._toolbox.with_access_token(access_token)
        response = self._prepare_multi_step_response(
            response=response,
            toolbox=toolbox,
            language=language,
            progress_callback=progress_callback,
        )
        response = _ensure_markdown_response(response, language)
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
                "pending_executed_steps": (
                    response.result.get("executed_steps", [])
                    if response.pending_action is not None and isinstance(response.result, dict)
                    else []
                ),
                "last_response": response.answer,
                "last_route": response.mode,
                "last_topic": response.intent,
                "last_result": response.result,
                "preferred_language": language,
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
        language: str,
        progress_callback=None,
    ) -> AdminChatResponse:
        toolbox = self._toolbox if access_token == getattr(self._toolbox, "_access_token", None) else self._toolbox.with_access_token(access_token)
        pending_tool = str(pending_payload.get("tool") or "")
        stored_steps = [
            {
                "tool": str(step.get("tool") or ""),
                "arguments": step.get("arguments", {}) if isinstance(step.get("arguments"), dict) else {},
            }
            for step in (pending_payload.get("steps", []) if isinstance(pending_payload.get("steps", []), list) else [])
            if isinstance(step, dict) and str(step.get("tool") or "").strip()
        ]
        if pending_tool == "compound_action":
            current_step = None
            remaining_steps = stored_steps
        else:
            current_step = {
                "tool": pending_tool,
                "arguments": pending_payload.get("arguments", {}) if isinstance(pending_payload.get("arguments"), dict) else {},
            }
            remaining_steps = stored_steps

        carried_steps = session.get("pending_executed_steps", [])
        if not isinstance(carried_steps, list):
            carried_steps = []
        executed_steps: list[dict[str, Any]] = [step for step in carried_steps if isinstance(step, dict)]
        current_result: Any = {}
        if current_step is not None:
            current_result = toolbox.execute_pending_action(current_step)
            executed_steps.append({"tool": current_step["tool"], "result": current_result})
            self._emit_execution_activity(progress_callback, current_step["tool"], current_step["arguments"], current_result, language)

        auto_results, next_mutation, tail_steps = self._execute_read_only_until_mutation(
            toolbox=toolbox,
            steps=remaining_steps,
            language=language,
            progress_callback=progress_callback,
        )
        executed_steps.extend(auto_results)

        result_payload: dict[str, Any]
        if current_step is not None and not auto_results and next_mutation is None and not tail_steps:
            result_payload = current_result if isinstance(current_result, dict) else {"raw": current_result}
        else:
            result_payload = {
                "status": "ok",
                "executed_steps": executed_steps,
            }
            if next_mutation is not None:
                result_payload["next_pending_action"] = {
                    "intent": "mutation",
                    "tool": next_mutation["tool"],
                    "arguments": next_mutation["arguments"],
                    "steps": tail_steps,
                }

        summary = _summarize_step_results(executed_steps, language=language)
        if next_mutation is not None:
            confirm_prompt = _build_confirmation_prompt(next_mutation, language=language)
            answer = f"{summary}\n\n{confirm_prompt}".strip()
            pending_next = {
                "intent": "mutation",
                "tool": next_mutation["tool"],
                "arguments": next_mutation["arguments"],
                "steps": tail_steps,
            }
            status = "needs_confirmation"
            requires_confirmation = True
            pending_model = AdminPendingAction(**pending_next)
            executed_flag = True
            stop_reason = "awaiting_next_confirmation"
        else:
            answer = summary
            pending_next = None
            status = "ok"
            requires_confirmation = False
            pending_model = None
            executed_flag = True
            stop_reason = "confirmed_action_executed"

        self._sessions.save(
            session_id,
            {
                **self._memory_snapshot(session),
                "pending_action": pending_next,
                "pending_executed_steps": executed_steps if pending_next is not None else [],
                "last_message": payload.message,
                "last_response": answer,
                "last_result": result_payload,
                "last_route": "mutate",
                "last_topic": str((pending_next or pending_payload).get("tool") or ""),
                "access_token": access_token,
            },
        )
        self._sessions.append_turn(session_id, "user", payload.message)
        self._sessions.append_turn(session_id, "assistant", answer)
        for step in executed_steps:
            self._sessions.invalidate_tool_cache(session_id, _cache_invalidation_tags(str(step.get("tool") or "")))
        raw_response = AdminChatResponse(
            status=status,
            mode="mutate",
            selected_mode=payload.selected_mode,
            session_id=session_id,
            message=payload.message,
            answer=answer,
            intent=str(pending_payload.get("intent") or "confirmed_action"),
            tool=str(pending_payload.get("tool") or ""),
            arguments=pending_payload.get("arguments", {}),
            requires_confirmation=requires_confirmation,
            executed=executed_flag,
            pending_action=pending_model,
            citations=[],
            thinking_summary="A confirmed action was executed and remaining steps were advanced.",
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
            result=result_payload,
            agent_run=AdminAgentRunState(
                status="paused_for_confirmation" if requires_confirmation else "completed",
                iteration_count=1,
                tool_call_count=max(1, len(executed_steps)),
                max_iterations=self._settings.max_iterations,
                max_tool_calls=self._settings.max_tool_calls,
                facts={},
                observations=[],
                decision_history=[],
                proposed_steps=[],
                final_answer=answer,
                stop_reason=stop_reason,
            ),
        )
        return _ensure_markdown_response(raw_response, language)

    def _prepare_multi_step_response(
        self,
        *,
        response: AdminChatResponse,
        toolbox: AdminToolbox,
        language: str,
        progress_callback=None,
    ) -> AdminChatResponse:
        pending = response.pending_action
        if pending is None or pending.tool != "compound_action":
            return response

        planned_steps = [
            {"tool": step.tool, "arguments": step.arguments}
            for step in pending.steps
            if step.tool
        ]
        auto_results, next_mutation, tail_steps = self._execute_read_only_until_mutation(
            toolbox=toolbox,
            steps=planned_steps,
            language=language,
            progress_callback=progress_callback,
        )

        if next_mutation is None:
            final_summary = _summarize_step_results(auto_results, language=language)
            next_agent_run = (
                response.agent_run.model_copy(
                    update={
                        "status": "completed",
                        "pending_confirmation": None,
                        "final_answer": final_summary,
                        "stop_reason": "all_steps_completed",
                    }
                )
                if response.agent_run is not None
                else None
            )
            return response.model_copy(
                update={
                    "status": "ok",
                    "answer": final_summary,
                    "requires_confirmation": False,
                    "pending_action": None,
                    "executed": True,
                    "result": {
                        "route": "mutate",
                        "executed_steps": auto_results,
                        "tool_cache_updates": response.result.get("tool_cache_updates", {}) if isinstance(response.result, dict) else {},
                    },
                    "agent_run": next_agent_run,
                }
            )

        answer_parts: list[str] = []
        if auto_results:
            answer_parts.append(_summarize_step_results(auto_results, language=language))
        answer_parts.append(_build_confirmation_prompt(next_mutation, language=language))
        next_pending = AdminPendingAction(
            intent="mutation",
            tool=next_mutation["tool"],
            arguments=next_mutation["arguments"],
            steps=[{"tool": step["tool"], "arguments": step["arguments"]} for step in tail_steps],
        )
        next_answer = "\n\n".join(part for part in answer_parts if part).strip()
        next_agent_run = (
            response.agent_run.model_copy(
                update={
                    "status": "paused_for_confirmation",
                    "pending_confirmation": next_pending.model_dump(),
                    "final_answer": next_answer,
                    "stop_reason": "awaiting_confirmation_after_read_steps",
                }
            )
            if response.agent_run is not None
            else None
        )
        return response.model_copy(
            update={
                "status": "needs_confirmation",
                "answer": next_answer,
                "requires_confirmation": True,
                "pending_action": next_pending,
                "tool": next_mutation["tool"],
                "arguments": next_mutation["arguments"],
                "executed": bool(auto_results),
                "result": {
                    "route": "mutate",
                    "executed_steps": auto_results,
                    "tool_cache_updates": response.result.get("tool_cache_updates", {}) if isinstance(response.result, dict) else {},
                },
                "agent_run": next_agent_run,
            }
        )

    def _execute_read_only_until_mutation(
        self,
        *,
        toolbox: AdminToolbox,
        steps: list[dict[str, Any]],
        language: str,
        progress_callback=None,
    ) -> tuple[list[dict[str, Any]], dict[str, Any] | None, list[dict[str, Any]]]:
        normalized_steps = [
            {
                "tool": str(step.get("tool") or ""),
                "arguments": step.get("arguments", {}) if isinstance(step.get("arguments"), dict) else {},
            }
            for step in steps
            if isinstance(step, dict) and str(step.get("tool") or "").strip()
        ]
        executed: list[dict[str, Any]] = []
        for index, step in enumerate(normalized_steps):
            tool_name = step["tool"]
            if tool_name in MUTATING_TOOLS:
                return executed, step, normalized_steps[index + 1 :]
            result = toolbox.execute_pending_action(step)
            executed.append({"tool": tool_name, "result": result})
            self._emit_execution_activity(progress_callback, tool_name, step["arguments"], result, language)
        return executed, None, []

    def _emit_execution_activity(self, progress_callback, tool_name: str, arguments: dict, result: Any, language: str) -> None:
        if progress_callback is None:
            return
        detail = _summarize_single_step(tool_name, result, language=language)
        progress_callback(
            {
                "phase": "tool",
                "status": "completed",
                "title": f"Step executed: {tool_name}",
                "detail": detail,
                "tool": tool_name,
                "arguments": arguments,
            }
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
            "pending_executed_steps": session.get("pending_executed_steps", []),
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
                parts.append("**Reranking:** disabled")
            else:
                parts.append(f"**Reranking strategy:** `{ranker}`")
        if rerank_top_n is not None:
            parts.append(f"**Rerank top-N:** `{rerank_top_n}`")
        if top_k_retrieve is not None and top_k_return is not None:
            parts.append(f"**Retrieval window:** pull `{top_k_retrieve}`, return `{top_k_return}`")
        return "; ".join(parts) if parts else "current retrieval settings checked"

    if scope == "preprocessing":
        strategy = config.get("chunk_strategy")
        chunk_size = config.get("chunk_size")
        chunk_overlap = config.get("chunk_overlap")
        parts = []
        if strategy is not None:
            parts.append(f"**Chunking strategy:** `{strategy}`")
        if chunk_size is not None:
            parts.append(f"**Chunk size:** `{chunk_size}`")
        if chunk_overlap is not None:
            parts.append(f"**Chunk overlap:** `{chunk_overlap}`")
        return "; ".join(parts) if parts else "current preprocessing settings checked"

    if scope == "embedding":
        embedding_model = config.get("embedding_model")
        embedding_dimensions = config.get("embedding_dimensions")
        embedding_batch_size = config.get("embedding_batch_size")
        parts = []
        parts.append(f"**Embedding model:** `{embedding_model if embedding_model is not None else 'unset'}`")
        parts.append(f"**Embedding dimensions:** `{embedding_dimensions if embedding_dimensions is not None else 'unset'}`")
        parts.append(f"**Embedding batch size:** `{embedding_batch_size if embedding_batch_size is not None else 'unset'}`")
        return "; ".join(parts)

    if scope == "generation":
        generation_model = config.get("generation_model")
        parts = []
        if generation_model is not None:
            parts.append(f"**Generation model:** `{generation_model}`")
        return "; ".join(parts) if parts else "current generation settings checked"

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
        ranker_value = updated.get("ranker", updated.get("default_ranker_type"))
        if ranker_value is not None:
            if str(ranker_value).strip().lower() in {"none", "", "null"}:
                parts.append("reranking disabled")
            else:
                parts.append(f"reranking strategy set to {ranker_value}")
        if "rerank_top_n" in updated:
            parts.append(f"reranking top-N set to {updated['rerank_top_n']}")
        if "top_k_retrieve" in updated:
            parts.append(f"retrieval top-K set to {updated['top_k_retrieve']}")
        if "top_k_return" in updated:
            parts.append(f"returned top-K set to {updated['top_k_return']}")
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
        summary = _format_update_summary(str(scope), updated)
        if summary:
            return f"Done. {summary[:1].upper()}{summary[1:]}."
        return "Done. The configuration change was applied."
    if tool_name == "get_repo_config" and isinstance(result, dict):
        scope = result.get("scope") or "system"
        config = result.get("config", {})
        return f"Done. {_format_scope_summary(str(scope), config).capitalize()}."
    if tool_name in {"reindex_document", "reindex_validated_documents"}:
        return "Done. Reindex completed."
    if tool_name == "run_evaluation":
        report = result.get("report", {}) if isinstance(result, dict) else {}
        return f"Done. The evaluation completed and saved report {report.get('report_id', '')}.".strip()
    if tool_name == "compare_evaluation_reports":
        return "Done. The evaluation comparison completed."
    return "Confirmed action executed successfully."


def _summarize_single_step(tool_name: str, result: Any, language: str = "en") -> str:
    if tool_name == "update_repo_config" and isinstance(result, dict):
        scope = str(result.get("scope") or "system")
        return _format_update_summary(scope, result.get("updated", {}))
    if tool_name == "get_repo_config" and isinstance(result, dict):
        scope = str(result.get("scope") or "system")
        return _format_scope_summary(scope, result.get("config", {}))
    if tool_name == "get_chunking_methods" and isinstance(result, dict):
        current = result.get("current_strategy")
        if language == "fr":
            return f"options de decoupage verifiees; strategie actuelle: `{current}`"
        if language == "ar":
            return f"تم التحقق من خيارات التقسيم؛ الاستراتيجية الحالية: `{current}`"
        return f"chunking options checked; current strategy is `{current}`"
    if tool_name == "get_ingestion_status" and isinstance(result, dict):
        total = result.get("total_documents", 0)
        embedded = result.get("embedded_documents", 0)
        if language == "fr":
            return f"etat d'ingestion verifie: total=`{total}`, indexes=`{embedded}`"
        if language == "ar":
            return f"تم التحقق من حالة الإدخال: الإجمالي=`{total}`، المفهرس=`{embedded}`"
        return f"ingestion status checked: total=`{total}`, embedded=`{embedded}`"
    if tool_name == "list_loaded_documents" and isinstance(result, dict):
        documents = result.get("documents", [])
        count = len(documents) if isinstance(documents, list) else 0
        if language == "fr":
            return f"documents charges verifies (`{count}` trouves)"
        if language == "ar":
            return f"تم التحقق من المستندات المحملة (تم العثور على `{count}`)"
        return f"loaded documents checked (`{count}` found)"
    if tool_name == "list_evaluation_reports" and isinstance(result, dict):
        reports = result.get("reports", [])
        count = len(reports) if isinstance(reports, list) else 0
        if language == "fr":
            return f"rapports d'evaluation verifies (`{count}` trouves)"
        if language == "ar":
            return f"تم التحقق من تقارير التقييم (تم العثور على `{count}`)"
        return f"evaluation reports checked (`{count}` found)"
    if tool_name in {"reindex_document", "reindex_validated_documents"}:
        return "reindex termine" if language == "fr" else ("اكتملت إعادة الفهرسة" if language == "ar" else "reindex completed")
    if tool_name == "run_evaluation" and isinstance(result, dict):
        report = result.get("report", {}) if isinstance(result.get("report"), dict) else {}
        report_id = report.get("report_id", "report created")
        if language == "fr":
            return f"evaluation terminee: `{report_id}`"
        if language == "ar":
            return f"اكتمل التقييم: `{report_id}`"
        return f"evaluation completed: `{report_id}`"
    if tool_name == "compare_evaluation_reports":
        return "comparaison terminee" if language == "fr" else ("اكتملت المقارنة" if language == "ar" else "evaluation comparison completed")
    if tool_name == "delete_document_completely":
        return "suppression terminee" if language == "fr" else ("اكتمل حذف المستند" if language == "ar" else "document deletion completed")
    return f"{tool_name} completed"


def _summarize_step_results(executed_steps: list[dict[str, Any]], language: str = "en") -> str:
    if not executed_steps:
        if language == "fr":
            return "## Resume\n\nAucune etape n'a encore ete executee."
        if language == "ar":
            return "## الملخص\n\nلم يتم تنفيذ أي خطوة بعد."
        return "## Summary\n\nNo steps were executed yet."

    info_parts: list[str] = []
    update_parts: list[str] = []
    for step in executed_steps:
        if not isinstance(step, dict):
            continue
        tool_name = str(step.get("tool") or "").strip() or "unknown_tool"
        summary = _summarize_single_step(str(step.get("tool") or ""), step.get("result"), language=language)
        if not summary:
            continue
        if tool_name in MUTATING_TOOLS:
            update_parts.append(summary)
        else:
            info_parts.append(summary)

    if not info_parts and not update_parts:
        if language == "fr":
            return "## Resume\n\nLes etapes demandees ont ete executees."
        if language == "ar":
            return "## الملخص\n\nتم تنفيذ الخطوات المطلوبة."
        return "## Summary\n\nThe requested steps were executed."

    sections = ["## Resume" if language == "fr" else ("## الملخص" if language == "ar" else "## Summary")]
    if info_parts:
        sections.append("### Informations collectees" if language == "fr" else ("### المعلومات التي تم جمعها" if language == "ar" else "### Information Gathered"))
        sections.extend(f"- {item}" for item in info_parts)
    if update_parts:
        sections.append("")
        sections.append("### Mises a jour appliquees" if language == "fr" else ("### التحديثات المطبقة" if language == "ar" else "### Updates Applied"))
        sections.extend(f"- {item}" for item in update_parts)
    return "\n".join(sections).strip()


def _describe_pending_step(step: dict[str, Any], language: str = "en") -> str:
    tool_name = str(step.get("tool") or "")
    arguments = step.get("arguments", {}) if isinstance(step.get("arguments"), dict) else {}
    if tool_name == "update_repo_config":
        scope = str(arguments.get("service_name") or "system")
        changes = arguments.get("changes", {})
        if language == "fr":
            return f"mettre a jour les parametres `{scope}` avec {changes}"
        if language == "ar":
            return f"تحديث إعدادات `{scope}` بالقيم {changes}"
        return f"update the {scope} settings with {changes}"
    if tool_name == "delete_document_completely":
        if language == "fr":
            return f"supprimer le document `{arguments.get('document_id', '')}` et nettoyer les vecteurs"
        if language == "ar":
            return f"حذف المستند `{arguments.get('document_id', '')}` وتنظيف المتجهات"
        return f"delete document '{arguments.get('document_id', '')}' and clean vectors"
    if tool_name == "reindex_document":
        if language == "fr":
            return f"reindexer le document `{arguments.get('document_id', '')}`"
        if language == "ar":
            return f"إعادة فهرسة المستند `{arguments.get('document_id', '')}`"
        return f"reindex document '{arguments.get('document_id', '')}'"
    if tool_name == "reindex_validated_documents":
        return "reindexer tous les documents valides" if language == "fr" else ("إعادة فهرسة جميع المستندات المعتمدة" if language == "ar" else "reindex all validated documents")
    if tool_name == "run_evaluation":
        dataset = arguments.get("dataset_path", "evals/sample_eval_dataset.json")
        if language == "fr":
            return f"lancer l'evaluation avec le dataset `{dataset}`"
        if language == "ar":
            return f"تشغيل التقييم باستخدام مجموعة البيانات `{dataset}`"
        return f"run evaluation with dataset '{dataset}'"
    if tool_name == "compare_evaluation_reports":
        baseline = arguments.get("baseline_report_id", "")
        candidate = arguments.get("candidate_report_id", "")
        if language == "fr":
            return f"comparer les rapports d'evaluation `{baseline}` et `{candidate}`"
        if language == "ar":
            return f"مقارنة تقريري التقييم `{baseline}` و`{candidate}`"
        return (
            "compare evaluation reports "
            f"'{baseline}' and '{candidate}'"
        )
    return tool_name.replace("_", " ")


def _build_confirmation_prompt(step: dict[str, Any], language: str = "en") -> str:
    if language == "fr":
        return (
            "## Prochaine Action\n\n"
            "### Confirmation Requise\n"
            f"- {_describe_pending_step(step, language=language)}\n\n"
            "Repondez avec **`confirm`** pour continuer."
        )
    if language == "ar":
        return (
            "## الإجراء التالي\n\n"
            "### يتطلب تأكيدًا\n"
            f"- {_describe_pending_step(step, language=language)}\n\n"
            "أرسل **`confirm`** للمتابعة."
        )
    return (
        "## Next Action\n\n"
        "### Confirmation Required\n"
        f"- {_describe_pending_step(step, language=language)}\n\n"
        "Reply with **`confirm`** to continue."
    )


def _ensure_markdown_response(response: AdminChatResponse, language: str = "en") -> AdminChatResponse:
    answer = str(response.answer or "").strip()
    if not answer:
        return response

    # Keep already-structured Markdown, but ensure confirmation block is present when needed.
    if answer.startswith("#"):
        expected = "## Prochaine Action" if language == "fr" else ("## الإجراء التالي" if language == "ar" else "## Next Action")
        if response.requires_confirmation and expected not in answer and response.pending_action is not None:
            next_block = _build_confirmation_prompt(response.pending_action.model_dump(), language=language)
            return response.model_copy(update={"answer": f"{answer}\n\n{next_block}"})
        return response

    heading = "## Resume" if language == "fr" else ("## الملخص" if language == "ar" else "## Summary")
    if response.mode == "advisory":
        heading = "## Conseil" if language == "fr" else ("## نصيحة" if language == "ar" else "## Advice")
    elif response.mode == "inspect":
        heading = "## Inspection" if language == "fr" else ("## فحص" if language == "ar" else "## Inspection")
    elif response.mode == "mutate":
        heading = "## Resume Des Modifications" if language == "fr" else ("## ملخص التحديث" if language == "ar" else "## Update Summary")

    normalized_body = answer.replace("\r\n", "\n").strip()
    markdown_answer = f"{heading}\n\n{normalized_body}"
    if response.requires_confirmation and response.pending_action is not None:
        markdown_answer = f"{markdown_answer}\n\n{_build_confirmation_prompt(response.pending_action.model_dump(), language=language)}"

    return response.model_copy(update={"answer": markdown_answer})


def _detect_language(message: str, preferred_language: Any = None) -> str:
    msg = str(message or "").strip()
    if re.search(r"[\u0600-\u06FF]", msg):
        return "ar"
    lowered = msg.lower()
    if re.search(r"[àâçéèêëîïôùûü]", lowered) or any(
        token in lowered for token in ["bonjour", "merci", "quelle", "quelles", "changer", "strategie", "parametres"]
    ):
        return "fr"
    if isinstance(preferred_language, str) and preferred_language.strip() in {"en", "fr", "ar"}:
        return preferred_language.strip()
    return "en"
