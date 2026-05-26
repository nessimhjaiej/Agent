from queue import Queue
from threading import Thread
from typing import Any
import re
from uuid import uuid4

from langchain_core.messages import HumanMessage, SystemMessage
from langchain_openai import ChatOpenAI

from app.config import Settings
from app.graph import run_graph
from app.security_events import emit_security_event
from app.schemas import (
    AdminActivityItem,
    AdminAgentRunState,
    AdminChatRequest,
    AdminChatResponse,
    AdminPendingAction,
    AdminWorkflowTask,
)
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

    def chat_with_progress(
        self, payload: AdminChatRequest, progress_callback=None
    ) -> AdminChatResponse:
        session_id = self._sessions.ensure_session_id(payload.session_id)
        session = self._sessions.load(session_id)
        access_token = payload.access_token or session.get("access_token")
        language = _detect_language(payload.message, session.get("preferred_language"))

        if payload.reject:
            pending_payload = (
                payload.pending_action.model_dump()
                if payload.pending_action is not None
                else session.get("pending_action")
            )
            return self._reject_pending_action(
                session_id,
                payload,
                pending_payload if isinstance(pending_payload, dict) else None,
                session,
                access_token,
                language,
                progress_callback,
            )

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
                    "chat_history": payload.chat_history
                    or self._recent_history(session),
                }
            ),
            self._settings,
            session_context=self._memory_snapshot(session),
            progress_callback=progress_callback,
        )
        toolbox = (
            self._toolbox
            if access_token == getattr(self._toolbox, "_access_token", None)
            else self._toolbox.with_access_token(access_token)
        )
        response = self._prepare_multi_step_response(
            response=response,
            toolbox=toolbox,
            language=language,
            progress_callback=progress_callback,
        )
        response = _ensure_markdown_response(response, language)
        self._sessions.append_turn(session_id, "user", payload.message)
        self._sessions.append_turn(session_id, "assistant", response.answer)
        cache_updates = (
            response.result.get("tool_cache_updates", {})
            if isinstance(response.result, dict)
            else {}
        )
        if isinstance(cache_updates, dict) and cache_updates:
            self._sessions.upsert_tool_cache(session_id, cache_updates)
        self._sessions.save(
            session_id,
            {
                **self._sessions.load(session_id),
                "last_message": payload.message,
                "pending_action": response.pending_action.model_dump()
                if response.pending_action
                else None,
                "pending_executed_steps": (
                    response.result.get("executed_steps", [])
                    if response.pending_action is not None
                    and isinstance(response.result, dict)
                    else []
                ),
                "workflow_tasks": (
                    response.result.get("workflow_tasks", [])
                    if response.pending_action is not None
                    and isinstance(response.result, dict)
                    else []
                ),
                "active_task_index": (
                    int(response.result.get("active_task_index", 0))
                    if response.pending_action is not None
                    and isinstance(response.result, dict)
                    else 0
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
        toolbox = (
            self._toolbox
            if access_token == getattr(self._toolbox, "_access_token", None)
            else self._toolbox.with_access_token(access_token)
        )
        workflow_tasks = self._normalize_workflow_tasks(
            session.get("workflow_tasks"),
            pending_payload=pending_payload,
        )
        task_index = pending_payload.get("task_index")
        if not isinstance(task_index, int):
            task_index = int(session.get("active_task_index", 0) or 0)
        current_step = {
            "tool": str(pending_payload.get("tool") or ""),
            "arguments": pending_payload.get("arguments", {})
            if isinstance(pending_payload.get("arguments"), dict)
            else {},
        }
        current_result = toolbox.execute_pending_action(current_step)
        self._emit_confirmed_mutation_event(
            payload=payload,
            session_id=session_id,
            pending_payload=pending_payload,
        )
        self._emit_execution_activity(
            progress_callback,
            current_step["tool"],
            current_step["arguments"],
            current_result,
            language,
        )
        workflow_tasks, current_steps = self._complete_mutation_task(
            workflow_tasks=workflow_tasks,
            task_index=task_index,
            result=current_result,
            language=language,
        )
        advanced_tasks, auto_results, next_pending, next_index = (
            self._advance_workflow_tasks(
                toolbox=toolbox,
                workflow_tasks=workflow_tasks,
                start_index=task_index + 1,
                language=language,
                progress_callback=progress_callback,
            )
        )
        executed_steps = self._workflow_executed_steps(advanced_tasks)
        if not executed_steps:
            executed_steps = current_steps + auto_results
        result_payload: dict[str, Any] = {
            "status": "ok",
            "executed_steps": executed_steps,
            "workflow_tasks": advanced_tasks,
            "active_task_index": next_index,
        }
        if next_pending is not None:
            result_payload["next_pending_action"] = next_pending

        if next_pending is not None:
            answer = _build_confirmation_prompt(next_pending, language=language)
            pending_next = next_pending
            status = "needs_confirmation"
            requires_confirmation = True
            pending_model = AdminPendingAction(**next_pending)
            executed_flag = True
            stop_reason = "awaiting_next_confirmation"
        else:
            summary = _summarize_workflow_tasks(
                workflow_tasks=advanced_tasks,
                executed_steps=executed_steps,
                language=language,
                request_message=str(
                    session.get("last_message") or payload.message or ""
                ),
            )
            answer = _llm_summarize_mutation_outcome(
                settings=self._settings,
                fallback_summary=summary,
                executed_steps=executed_steps,
                request_message=str(
                    session.get("last_message") or payload.message or ""
                ),
                language=language,
                workflow_tasks=advanced_tasks,
            )
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
                "pending_executed_steps": executed_steps
                if pending_next is not None
                else [],
                "workflow_tasks": advanced_tasks if pending_next is not None else [],
                "active_task_index": next_index if pending_next is not None else 0,
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
            self._sessions.invalidate_tool_cache(
                session_id, _cache_invalidation_tags(str(step.get("tool") or ""))
            )
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
                status="paused_for_confirmation"
                if requires_confirmation
                else "completed",
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

    def _emit_confirmed_mutation_event(
        self,
        *,
        payload: AdminChatRequest,
        session_id: str,
        pending_payload: dict[str, Any],
    ) -> None:
        tool_name = str(pending_payload.get("tool") or "").strip()
        if tool_name not in MUTATING_TOOLS:
            return

        arguments = pending_payload.get("arguments", {})
        if not isinstance(arguments, dict):
            arguments = {}

        metadata: dict[str, Any] = {
            "email": payload.actor_email or "",
            "user_id": payload.actor_user_id or "",
            "role": payload.actor_role or "",
            "tool": tool_name,
            "session_id": session_id,
        }
        for key in (
            "service_name",
            "document_id",
            "dataset_path",
            "baseline_report_id",
            "candidate_report_id",
        ):
            value = arguments.get(key)
            if value not in ("", None):
                metadata[key] = value
        changes = arguments.get("changes")
        if isinstance(changes, dict) and changes:
            metadata["change_keys"] = sorted(changes.keys())
            metadata["change_summary"] = ", ".join(
                f"{key}={changes[key]}" for key in sorted(changes.keys())
            )

        emit_security_event(
            self._settings,
            event_type="ADMIN_MUTATION_CONFIRMED",
            severity="info",
            title="Admin mutation confirmed",
            message="A confirmed admin chat mutation was executed.",
            metadata={
                key: value
                for key, value in metadata.items()
                if value not in ("", None, [], {})
            },
            fingerprint=f"admin-mutation-confirmed|{session_id}|{tool_name}|{uuid4()}",
        )

    def _reject_pending_action(
        self,
        session_id: str,
        payload: AdminChatRequest,
        pending_payload: dict[str, Any] | None,
        session: dict,
        access_token: str | None,
        language: str,
        progress_callback=None,
    ) -> AdminChatResponse:
        workflow_tasks = self._normalize_workflow_tasks(
            session.get("workflow_tasks"),
            pending_payload=pending_payload,
        )
        task_index = (pending_payload or {}).get("task_index")
        if not isinstance(task_index, int):
            task_index = int(session.get("active_task_index", 0) or 0)
        workflow_tasks = self._reject_mutation_task(
            workflow_tasks=workflow_tasks,
            task_index=task_index,
            language=language,
        )
        toolbox = (
            self._toolbox
            if access_token == getattr(self._toolbox, "_access_token", None)
            else self._toolbox.with_access_token(access_token)
        )
        workflow_tasks, auto_results, next_pending, next_index = (
            self._advance_workflow_tasks(
                toolbox=toolbox,
                workflow_tasks=workflow_tasks,
                start_index=task_index + 1,
                language=language,
                progress_callback=progress_callback,
            )
        )
        executed_steps = self._workflow_executed_steps(workflow_tasks)

        if next_pending is not None:
            answer = _build_confirmation_prompt(next_pending, language=language)
            pending_next = next_pending
            status = "needs_confirmation"
            requires_confirmation = True
            pending_model = AdminPendingAction(**next_pending)
            stop_reason = "awaiting_confirmation_after_rejection"
        else:
            answer = _summarize_rejected_flow(
                workflow_tasks=workflow_tasks,
                settings=self._settings,
                language=language,
                request_message=str(
                    session.get("last_message") or payload.message or ""
                ),
            )
            pending_next = None
            status = "ok"
            requires_confirmation = False
            pending_model = None
            stop_reason = "pending_action_rejected"

        self._sessions.append_turn(session_id, "user", payload.message)
        self._sessions.append_turn(session_id, "assistant", answer)
        self._sessions.save(
            session_id,
            {
                **self._memory_snapshot(session),
                "pending_action": pending_next,
                "pending_executed_steps": executed_steps
                if pending_next is not None
                else [],
                "workflow_tasks": workflow_tasks if pending_next is not None else [],
                "active_task_index": next_index if pending_next is not None else 0,
                "last_message": payload.message,
                "last_response": answer,
                "last_result": {
                    "route": "mutate",
                    "rejected": True,
                    "executed_steps": executed_steps,
                    "workflow_tasks": workflow_tasks,
                    "rejected_pending_action": pending_payload or {},
                    **(
                        {
                            "next_pending_action": pending_next,
                        }
                        if pending_next is not None
                        else {}
                    ),
                },
                "last_route": "mutate",
                "last_topic": str(
                    (pending_next or pending_payload or {}).get("tool")
                    or "reject pending mutation"
                ),
                "access_token": access_token,
            },
        )
        return _ensure_markdown_response(
            AdminChatResponse(
                status=status,
                mode="mutate",
                selected_mode=payload.selected_mode,
                session_id=session_id,
                message=payload.message,
                answer=answer,
                intent=str(
                    (pending_payload or {}).get("intent") or "reject_pending_action"
                ),
                tool=str((pending_payload or {}).get("tool") or ""),
                arguments=(pending_payload or {}).get("arguments", {})
                if isinstance((pending_payload or {}).get("arguments"), dict)
                else {},
                requires_confirmation=requires_confirmation,
                executed=False,
                pending_action=pending_model,
                citations=[],
                thinking_summary="The pending action was rejected and the remaining plan was advanced.",
                activity=[
                    AdminActivityItem(
                        phase="confirmation",
                        status="skipped",
                        title="Action rejected",
                        detail="The pending action was dismissed and no change was applied.",
                        tool=str((pending_payload or {}).get("tool") or ""),
                        arguments=(pending_payload or {}).get("arguments", {})
                        if isinstance((pending_payload or {}).get("arguments"), dict)
                        else {},
                    )
                ],
                result={
                    "route": "mutate",
                    "rejected": True,
                    "executed_steps": executed_steps,
                    "workflow_tasks": workflow_tasks,
                    "rejected_pending_action": pending_payload or {},
                    **(
                        {
                            "next_pending_action": pending_next,
                        }
                        if pending_next is not None
                        else {}
                    ),
                },
                agent_run=AdminAgentRunState(
                    status="paused_for_confirmation"
                    if requires_confirmation
                    else "completed",
                    iteration_count=1,
                    tool_call_count=len(executed_steps),
                    max_iterations=self._settings.max_iterations,
                    max_tool_calls=self._settings.max_tool_calls,
                    facts={"route": "mutate", "intent": "reject_pending_action"},
                    observations=[],
                    decision_history=[],
                    proposed_steps=[],
                    pending_confirmation=pending_next
                    if pending_next is not None
                    else None,
                    final_answer=answer,
                    stop_reason=stop_reason,
                ),
            ),
            language,
        )

    def _prepare_multi_step_response(
        self,
        *,
        response: AdminChatResponse,
        toolbox: AdminToolbox,
        language: str,
        progress_callback=None,
    ) -> AdminChatResponse:
        pending = response.pending_action
        if pending is None:
            return response

        workflow_tasks = self._normalize_workflow_tasks(
            pending.workflow_tasks,
            pending_payload=pending.model_dump(),
        )
        if not workflow_tasks:
            return response

        updated_tasks, auto_results, next_pending, next_index = (
            self._advance_workflow_tasks(
                toolbox=toolbox,
                workflow_tasks=workflow_tasks,
                start_index=0,
                language=language,
                progress_callback=progress_callback,
            )
        )

        result_payload = {
            "route": "mutate",
            "executed_steps": auto_results,
            "workflow_tasks": updated_tasks,
            "active_task_index": next_index,
            "tool_cache_updates": response.result.get("tool_cache_updates", {})
            if isinstance(response.result, dict)
            else {},
        }

        if next_pending is None:
            final_summary = _summarize_workflow_tasks(
                workflow_tasks=updated_tasks,
                executed_steps=auto_results,
                language=language,
                request_message=response.message,
            )
            final_summary = _llm_summarize_mutation_outcome(
                settings=self._settings,
                fallback_summary=final_summary,
                executed_steps=auto_results,
                request_message=response.message,
                language=language,
                workflow_tasks=updated_tasks,
            )
            next_agent_run = (
                response.agent_run.model_copy(
                    update={
                        "status": "completed",
                        "pending_confirmation": None,
                        "final_answer": final_summary,
                        "stop_reason": "all_tasks_completed",
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
                    "result": result_payload,
                    "agent_run": next_agent_run,
                }
            )

        next_model = AdminPendingAction(**next_pending)
        next_answer = _build_confirmation_prompt(next_pending, language=language)
        next_agent_run = (
            response.agent_run.model_copy(
                update={
                    "status": "paused_for_confirmation",
                    "pending_confirmation": next_model.model_dump(),
                    "final_answer": next_answer,
                    "stop_reason": "awaiting_confirmation_for_task",
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
                "pending_action": next_model,
                "tool": next_pending["tool"],
                "arguments": next_pending["arguments"],
                "executed": bool(auto_results),
                "result": result_payload,
                "agent_run": next_agent_run,
            }
        )

    def _normalize_workflow_tasks(
        self,
        workflow_tasks: list[Any] | None,
        *,
        pending_payload: dict[str, Any] | None = None,
    ) -> list[dict[str, Any]]:
        normalized: list[dict[str, Any]] = []
        for index, raw_task in enumerate(workflow_tasks or []):
            if hasattr(raw_task, "model_dump"):
                raw_task = raw_task.model_dump()
            if not isinstance(raw_task, dict):
                continue
            steps = [
                {
                    "tool": str(step.get("tool") or ""),
                    "arguments": step.get("arguments", {})
                    if isinstance(step.get("arguments"), dict)
                    else {},
                }
                for step in (
                    raw_task.get("steps", [])
                    if isinstance(raw_task.get("steps"), list)
                    else []
                )
                if isinstance(step, dict) and str(step.get("tool") or "").strip()
            ]
            if not steps:
                continue
            normalized.append(
                {
                    "task_id": str(raw_task.get("task_id") or f"task_{index + 1}"),
                    "kind": str(raw_task.get("kind") or _task_kind_for_steps(steps)),
                    "clause": str(raw_task.get("clause") or ""),
                    "status": str(raw_task.get("status") or "pending"),
                    "steps": steps,
                    "outcome": raw_task.get("outcome", {})
                    if isinstance(raw_task.get("outcome"), dict)
                    else {},
                }
            )
        if normalized:
            return normalized
        return _workflow_tasks_from_pending_payload(pending_payload or {})

    def _advance_workflow_tasks(
        self,
        *,
        toolbox: AdminToolbox,
        workflow_tasks: list[dict[str, Any]],
        start_index: int,
        language: str,
        progress_callback=None,
    ) -> tuple[list[dict[str, Any]], list[dict[str, Any]], dict[str, Any] | None, int]:
        updated_tasks = [dict(task) for task in workflow_tasks]
        executed_steps: list[dict[str, Any]] = []
        for index in range(max(0, start_index), len(updated_tasks)):
            task = updated_tasks[index]
            if str(task.get("status") or "") in {"completed", "rejected", "skipped"}:
                continue
            steps = task.get("steps", [])
            if not isinstance(steps, list) or not steps:
                task["status"] = "skipped"
                task["outcome"] = {"executed_steps": []}
                continue
            first_tool = str(steps[0].get("tool") or "")
            if first_tool in MUTATING_TOOLS:
                task["status"] = "pending"
                pending_action = {
                    "intent": "mutation",
                    "tool": first_tool,
                    "arguments": steps[0].get("arguments", {})
                    if isinstance(steps[0].get("arguments"), dict)
                    else {},
                    "steps": steps[1:],
                    "task_index": index,
                    "workflow_tasks": updated_tasks,
                }
                return updated_tasks, executed_steps, pending_action, index
            task_steps: list[dict[str, Any]] = []
            for step in steps:
                result = toolbox.execute_pending_action(step)
                task_steps.append(
                    {"tool": str(step.get("tool") or ""), "result": result}
                )
                executed_steps.append(
                    {"tool": str(step.get("tool") or ""), "result": result}
                )
                self._emit_execution_activity(
                    progress_callback,
                    str(step.get("tool") or ""),
                    step.get("arguments", {}),
                    result,
                    language,
                )
            task["status"] = "completed"
            task["outcome"] = {
                "executed_steps": task_steps,
                "summary": _summarize_step_results(
                    task_steps,
                    language=language,
                    request_message=str(task.get("clause") or ""),
                ),
            }
        return updated_tasks, executed_steps, None, len(updated_tasks)

    def _workflow_executed_steps(
        self, workflow_tasks: list[dict[str, Any]]
    ) -> list[dict[str, Any]]:
        executed_steps: list[dict[str, Any]] = []
        for task in workflow_tasks:
            if not isinstance(task, dict):
                continue
            outcome = task.get("outcome", {})
            steps = (
                outcome.get("executed_steps", []) if isinstance(outcome, dict) else []
            )
            if isinstance(steps, list):
                executed_steps.extend(step for step in steps if isinstance(step, dict))
        return executed_steps

    def _complete_mutation_task(
        self,
        *,
        workflow_tasks: list[dict[str, Any]],
        task_index: int,
        result: Any,
        language: str,
    ) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
        updated_tasks = [dict(task) for task in workflow_tasks]
        if task_index < 0 or task_index >= len(updated_tasks):
            return updated_tasks, []
        task = updated_tasks[task_index]
        steps = task.get("steps", [])
        current_step = steps[0] if isinstance(steps, list) and steps else {}
        executed_steps = (
            [{"tool": str(current_step.get("tool") or ""), "result": result}]
            if current_step
            else []
        )
        task["status"] = "completed"
        task["outcome"] = {
            "executed_steps": executed_steps,
            "summary": _summarize_step_results(
                executed_steps,
                language=language,
                request_message=str(task.get("clause") or ""),
            ),
        }
        return updated_tasks, executed_steps

    def _reject_mutation_task(
        self,
        *,
        workflow_tasks: list[dict[str, Any]],
        task_index: int,
        language: str,
    ) -> list[dict[str, Any]]:
        updated_tasks = [dict(task) for task in workflow_tasks]
        if task_index < 0 or task_index >= len(updated_tasks):
            return updated_tasks
        task = updated_tasks[task_index]
        task["status"] = "rejected"
        task["outcome"] = {
            "executed_steps": [],
            "summary": _describe_pending_step(
                task.get("steps", [{}])[0], language=language
            )
            if isinstance(task.get("steps"), list) and task.get("steps")
            else "",
        }
        return updated_tasks

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
                "arguments": step.get("arguments", {})
                if isinstance(step.get("arguments"), dict)
                else {},
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
            self._emit_execution_activity(
                progress_callback, tool_name, step["arguments"], result, language
            )
        return executed, None, []

    def _emit_execution_activity(
        self,
        progress_callback,
        tool_name: str,
        arguments: dict,
        result: Any,
        language: str,
    ) -> None:
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

    def _ensure_required_information(
        self,
        *,
        message: str,
        toolbox: AdminToolbox,
        executed_steps: list[dict[str, Any]],
        language: str,
        progress_callback=None,
    ) -> list[dict[str, Any]]:
        required_tools = _required_read_tools_from_message(message)
        if not required_tools:
            return executed_steps
        executed_tool_names = {
            str(step.get("tool") or "")
            for step in executed_steps
            if isinstance(step, dict)
        }
        extended = list(executed_steps)
        for tool_name in required_tools:
            if tool_name in executed_tool_names:
                continue
            step_payload = {"tool": tool_name, "arguments": {}}
            result = toolbox.execute_pending_action(step_payload)
            extended.append({"tool": tool_name, "result": result})
            self._emit_execution_activity(
                progress_callback, tool_name, {}, result, language
            )
        return extended

    def _recent_history(self, session: dict) -> list[dict]:
        history = session.get("history", [])
        return history[-6:] if isinstance(history, list) else []

    def _memory_snapshot(self, session: dict) -> dict:
        if not isinstance(session, dict):
            return {}
        return {
            "history": self._recent_history(session),
            "tool_cache": session.get("tool_cache", {})
            if isinstance(session.get("tool_cache"), dict)
            else {},
            "pending_action": session.get("pending_action"),
            "pending_executed_steps": session.get("pending_executed_steps", []),
            "workflow_tasks": session.get("workflow_tasks", []),
            "active_task_index": session.get("active_task_index", 0),
            "last_message": session.get("last_message"),
            "last_response": session.get("last_response"),
            "last_route": session.get("last_route"),
            "last_topic": session.get("last_topic"),
            "last_result": session.get("last_result")
            if isinstance(session.get("last_result"), dict)
            else {},
            "access_token": session.get("access_token"),
            "cache_invalidated_at": session.get("cache_invalidated_at"),
        }


def _cache_invalidation_tags(tool_name: str) -> list[str]:
    if tool_name == "update_repo_config":
        return ["config"]
    if tool_name in {
        "reindex_document",
        "reindex_validated_documents",
        "delete_document_completely",
    }:
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
            parts.append(
                f"**Retrieval window:** pull `{top_k_retrieve}`, return `{top_k_return}`"
            )
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
        parts.append(
            f"**Embedding model:** `{embedding_model if embedding_model is not None else 'unset'}`"
        )
        parts.append(
            f"**Embedding dimensions:** `{embedding_dimensions if embedding_dimensions is not None else 'unset'}`"
        )
        parts.append(
            f"**Embedding batch size:** `{embedding_batch_size if embedding_batch_size is not None else 'unset'}`"
        )
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
                parts.append(
                    f"evaluation completed: {report.get('report_id', 'report created')}"
                )
            elif step_tool == "compare_evaluation_reports" and isinstance(
                step_result, dict
            ):
                parts.append("evaluation comparison completed")
            elif step_tool in {
                "reindex_document",
                "reindex_validated_documents",
            } and isinstance(step_result, dict):
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
    if tool_name == "read_evaluation_report":
        report = result.get("report", {}) if isinstance(result, dict) else {}
        return f"Done. The evaluation report {report.get('report_id', '')} was loaded.".strip()
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
        methods = []
        for item in (
            result.get("methods", []) if isinstance(result.get("methods"), list) else []
        ):
            if isinstance(item, dict) and item.get("implemented"):
                name = str(item.get("name") or "").strip()
                if name:
                    methods.append(name)
        methods_text = (
            ", ".join(f"`{name}`" for name in methods)
            if methods
            else "`late`, `overlap`, `semantic`"
        )
        if language == "fr":
            return f"strategies de decoupage disponibles: {methods_text}; strategie actuelle: `{current}`"
        if language == "ar":
            return f"Ø§Ø³ØªØ±Ø§ØªÙŠØ¬ÙŠØ§Øª Ø§Ù„ØªÙ‚Ø³ÙŠÙ… Ø§Ù„Ù…ØªØ§Ø­Ø©: {methods_text}Ø› Ø§Ù„Ø§Ø³ØªØ±Ø§ØªÙŠØ¬ÙŠØ© Ø§Ù„Ø­Ø§Ù„ÙŠØ©: `{current}`"
        return f"available chunking strategies: {methods_text}; current strategy: `{current}`"
    if tool_name == "get_reranking_methods" and isinstance(result, dict):
        methods = []
        for item in (
            result.get("methods", []) if isinstance(result.get("methods"), list) else []
        ):
            if isinstance(item, dict) and item.get("implemented"):
                name = str(item.get("name") or "").strip()
                if name:
                    methods.append(name)
        methods_text = (
            ", ".join(f"`{name}`" for name in methods)
            if methods
            else "`cross_encoder`, `llm_batch`, `none`"
        )
        current = result.get("current_default_ranker_type")
        if language == "fr":
            return f"strategies de reranking disponibles: {methods_text}; strategie actuelle: `{current}`"
        if language == "ar":
            return f"Ø§Ø³ØªØ±Ø§ØªÙŠØ¬ÙŠØ§Øª Ø¥Ø¹Ø§Ø¯Ø© Ø§Ù„ØªØ±ØªÙŠØ¨ Ø§Ù„Ù…ØªØ§Ø­Ø©: {methods_text}Ø› Ø§Ù„Ø§Ø³ØªØ±Ø§ØªÙŠØ¬ÙŠØ© Ø§Ù„Ø­Ø§Ù„ÙŠØ©: `{current}`"
        return f"available reranking strategies: {methods_text}; current strategy: `{current}`"
    if tool_name == "get_ingestion_status" and isinstance(result, dict):
        total = result.get("total_documents", 0)
        embedded = result.get("embedded_documents", 0)
        if language == "fr":
            return f"etat d'ingestion verifie: total=`{total}`, indexes=`{embedded}`"
        if language == "ar":
            return f"ØªÙ… Ø§Ù„ØªØ­Ù‚Ù‚ Ù…Ù† Ø­Ø§Ù„Ø© Ø§Ù„Ø¥Ø¯Ø®Ø§Ù„: Ø§Ù„Ø¥Ø¬Ù…Ø§Ù„ÙŠ=`{total}`ØŒ Ø§Ù„Ù…ÙÙ‡Ø±Ø³=`{embedded}`"
        return f"ingestion status checked: total=`{total}`, embedded=`{embedded}`"
    if tool_name == "list_loaded_documents" and isinstance(result, dict):
        documents = result.get("documents", [])
        count = len(documents) if isinstance(documents, list) else 0
        if language == "fr":
            return f"documents charges verifies (`{count}` trouves)"
        if language == "ar":
            return f"ØªÙ… Ø§Ù„ØªØ­Ù‚Ù‚ Ù…Ù† Ø§Ù„Ù…Ø³ØªÙ†Ø¯Ø§Øª Ø§Ù„Ù…Ø­Ù…Ù„Ø© (ØªÙ… Ø§Ù„Ø¹Ø«ÙˆØ± Ø¹Ù„Ù‰ `{count}`)"
        return f"loaded documents checked (`{count}` found)"
    if tool_name == "list_evaluation_reports" and isinstance(result, dict):
        reports = result.get("reports", [])
        count = len(reports) if isinstance(reports, list) else 0
        if language == "fr":
            return f"rapports d'evaluation verifies (`{count}` trouves)"
        if language == "ar":
            return f"ØªÙ… Ø§Ù„ØªØ­Ù‚Ù‚ Ù…Ù† ØªÙ‚Ø§Ø±ÙŠØ± Ø§Ù„ØªÙ‚ÙŠÙŠÙ… (ØªÙ… Ø§Ù„Ø¹Ø«ÙˆØ± Ø¹Ù„Ù‰ `{count}`)"
        return f"evaluation reports checked (`{count}` found)"
    if tool_name == "read_evaluation_report" and isinstance(result, dict):
        report = result.get("report", {}) if isinstance(result.get("report"), dict) else {}
        report_id = report.get("report_id", "latest")
        sample_count = report.get("sample_count", 0)
        summary = report.get("summary", {}) if isinstance(report.get("summary"), dict) else {}
        metrics = ", ".join(f"{key}={value}" for key, value in summary.items()) or "no summary metrics recorded"
        return f"evaluation report read: `{report_id}` (`{sample_count}` samples); summary: {metrics}"
    if tool_name in {"reindex_document", "reindex_validated_documents"}:
        return (
            "reindex termine"
            if language == "fr"
            else (
                "Ø§ÙƒØªÙ…Ù„Øª Ø¥Ø¹Ø§Ø¯Ø© Ø§Ù„ÙÙ‡Ø±Ø³Ø©"
                if language == "ar"
                else "reindex completed"
            )
        )
    if tool_name == "run_evaluation" and isinstance(result, dict):
        report = (
            result.get("report", {}) if isinstance(result.get("report"), dict) else {}
        )
        report_id = report.get("report_id", "report created")
        if language == "fr":
            return f"evaluation terminee: `{report_id}`"
        if language == "ar":
            return f"Ø§ÙƒØªÙ…Ù„ Ø§Ù„ØªÙ‚ÙŠÙŠÙ…: `{report_id}`"
        return f"evaluation completed: `{report_id}`"
    if tool_name == "read_evaluation_report" and isinstance(result, dict):
        report = (
            result.get("report", {}) if isinstance(result.get("report"), dict) else {}
        )
        report_id = report.get("report_id", "latest")
        return f"evaluation report read: `{report_id}`"
    if tool_name == "compare_evaluation_reports":
        return (
            "comparaison terminee"
            if language == "fr"
            else (
                "Ø§ÙƒØªÙ…Ù„Øª Ø§Ù„Ù…Ù‚Ø§Ø±Ù†Ø©"
                if language == "ar"
                else "evaluation comparison completed"
            )
        )
    if tool_name == "delete_document_completely":
        return (
            "suppression terminee"
            if language == "fr"
            else (
                "Ø§ÙƒØªÙ…Ù„ Ø­Ø°Ù Ø§Ù„Ù…Ø³ØªÙ†Ø¯"
                if language == "ar"
                else "document deletion completed"
            )
        )
    return f"{tool_name} completed"


def _summarize_step_results(
    executed_steps: list[dict[str, Any]],
    language: str = "en",
    request_message: str = "",
) -> str:
    if not executed_steps:
        if language == "fr":
            return "## Resume\n\nAucune etape n'a encore ete executee."
        if language == "ar":
            return "## Ø§Ù„Ù…Ù„Ø®Øµ\n\nÙ„Ù… ÙŠØªÙ… ØªÙ†ÙÙŠØ° Ø£ÙŠ Ø®Ø·ÙˆØ© Ø¨Ø¹Ø¯."
        return "## Summary\n\nNo steps were executed yet."

    info_parts_by_key: dict[str, str] = {}
    update_parts: list[str] = []
    for step in executed_steps:
        if not isinstance(step, dict):
            continue
        tool_name = str(step.get("tool") or "").strip() or "unknown_tool"
        summary = _summarize_single_step(
            str(step.get("tool") or ""), step.get("result"), language=language
        )
        if not summary:
            continue
        if tool_name in MUTATING_TOOLS:
            update_parts.append(summary)
        else:
            info_parts_by_key[_info_summary_key(step)] = summary
    info_parts = _dedupe_preserve_order(list(info_parts_by_key.values()))
    update_parts = _dedupe_preserve_order(update_parts)

    if not info_parts and not update_parts:
        if language == "fr":
            return "## Resume\n\nLes etapes demandees ont ete executees."
        if language == "ar":
            return "## Ø§Ù„Ù…Ù„Ø®Øµ\n\nØªÙ… ØªÙ†ÙÙŠØ° Ø§Ù„Ø®Ø·ÙˆØ§Øª Ø§Ù„Ù…Ø·Ù„ÙˆØ¨Ø©."
        return "## Summary\n\nThe requested steps were executed."

    sections = [
        "## Resume"
        if language == "fr"
        else ("## Ø§Ù„Ù…Ù„Ø®Øµ" if language == "ar" else "## Summary")
    ]
    if info_parts:
        sections.append(
            "### Informations collectees"
            if language == "fr"
            else (
                "### Ø§Ù„Ù…Ø¹Ù„ÙˆÙ…Ø§Øª Ø§Ù„ØªÙŠ ØªÙ… Ø¬Ù…Ø¹Ù‡Ø§"
                if language == "ar"
                else "### Information Gathered"
            )
        )
        sections.extend(f"- {item}" for item in info_parts)
    if update_parts:
        sections.append("")
        sections.append(
            "### Mises a jour appliquees"
            if language == "fr"
            else (
                "### Ø§Ù„ØªØ­Ø¯ÙŠØ«Ø§Øª Ø§Ù„Ù…Ø·Ø¨Ù‚Ø©"
                if language == "ar"
                else "### Updates Applied"
            )
        )
        sections.extend(f"- {item}" for item in update_parts)
    chunking_advice = _chunking_advantages_lines(
        request_message, executed_steps, language
    )
    if chunking_advice:
        sections.append("")
        sections.append(
            "### Avantages des strategies de decoupage"
            if language == "fr"
            else (
                "### Ù…Ø²Ø§ÙŠØ§ Ø§Ø³ØªØ±Ø§ØªÙŠØ¬ÙŠØ§Øª Ø§Ù„ØªÙ‚Ø³ÙŠÙ…"
                if language == "ar"
                else "### Advantages of Available Chunking Strategies"
            )
        )
        sections.extend(f"- {item}" for item in chunking_advice)
    reranking_advice = _reranking_advantages_lines(
        request_message, executed_steps, language
    )
    if reranking_advice:
        sections.append("")
        sections.append(
            "### Avantages des strategies de reranking"
            if language == "fr"
            else (
                "### Ù…Ø²Ø§ÙŠØ§ Ø§Ø³ØªØ±Ø§ØªÙŠØ¬ÙŠØ§Øª Ø¥Ø¹Ø§Ø¯Ø© Ø§Ù„ØªØ±ØªÙŠØ¨"
                if language == "ar"
                else "### Advantages of Available Reranking Strategies"
            )
        )
        sections.extend(f"- {item}" for item in reranking_advice)
    return "\n".join(sections).strip()


def _task_kind_for_steps(steps: list[dict[str, Any]]) -> str:
    first_tool = str((steps[0] if steps else {}).get("tool") or "")
    if first_tool in MUTATING_TOOLS:
        return "mutation"
    return "read"


def _workflow_tasks_from_pending_payload(
    pending_payload: dict[str, Any],
) -> list[dict[str, Any]]:
    if not isinstance(pending_payload, dict):
        return []
    workflow_tasks = pending_payload.get("workflow_tasks", [])
    if isinstance(workflow_tasks, list) and workflow_tasks:
        normalized = []
        for index, task in enumerate(workflow_tasks):
            if hasattr(task, "model_dump"):
                task = task.model_dump()
            if not isinstance(task, dict):
                continue
            steps = [
                {
                    "tool": str(step.get("tool") or ""),
                    "arguments": step.get("arguments", {})
                    if isinstance(step.get("arguments"), dict)
                    else {},
                }
                for step in (
                    task.get("steps", []) if isinstance(task.get("steps"), list) else []
                )
                if isinstance(step, dict) and str(step.get("tool") or "").strip()
            ]
            if steps:
                normalized.append(
                    {
                        "task_id": str(task.get("task_id") or f"task_{index + 1}"),
                        "kind": str(task.get("kind") or _task_kind_for_steps(steps)),
                        "clause": str(task.get("clause") or ""),
                        "status": str(task.get("status") or "pending"),
                        "steps": steps,
                        "outcome": task.get("outcome", {})
                        if isinstance(task.get("outcome"), dict)
                        else {},
                    }
                )
        if normalized:
            return normalized

    if str(pending_payload.get("tool") or "") == "compound_action":
        tasks = []
        for index, step in enumerate(
            pending_payload.get("steps", [])
            if isinstance(pending_payload.get("steps"), list)
            else []
        ):
            if not isinstance(step, dict) or not str(step.get("tool") or "").strip():
                continue
            tasks.append(
                {
                    "task_id": f"task_{index + 1}",
                    "kind": _task_kind_for_steps([step]),
                    "clause": "",
                    "status": "pending",
                    "steps": [
                        {
                            "tool": str(step.get("tool") or ""),
                            "arguments": step.get("arguments", {})
                            if isinstance(step.get("arguments"), dict)
                            else {},
                        }
                    ],
                    "outcome": {},
                }
            )
        return tasks

    current_tool = str(pending_payload.get("tool") or "")
    if not current_tool:
        return []
    current_step = {
        "tool": current_tool,
        "arguments": pending_payload.get("arguments", {})
        if isinstance(pending_payload.get("arguments"), dict)
        else {},
    }
    return [
        {
            "task_id": "task_1",
            "kind": _task_kind_for_steps([current_step]),
            "clause": "",
            "status": "pending",
            "steps": [current_step],
            "outcome": {},
        }
    ]


def _workflow_task_step_summaries(
    task: dict[str, Any], language: str
) -> tuple[list[str], list[str], list[str]]:
    outcome = task.get("outcome", {}) if isinstance(task.get("outcome"), dict) else {}
    executed_steps = (
        outcome.get("executed_steps", [])
        if isinstance(outcome.get("executed_steps"), list)
        else []
    )
    clause = str(task.get("clause") or "")
    info_map: dict[str, str] = {}
    update_parts: list[str] = []
    for step in executed_steps:
        if not isinstance(step, dict):
            continue
        tool_name = str(step.get("tool") or "")
        summary = _summarize_single_step(
            tool_name, step.get("result"), language=language
        )
        if not summary:
            continue
        if tool_name in MUTATING_TOOLS:
            update_parts.append(summary)
        else:
            info_map[_info_summary_key(step)] = summary
    advice_parts: list[str] = []
    if clause:
        advice_parts.extend(
            _chunking_advantages_lines(clause, executed_steps, language)
        )
        advice_parts.extend(
            _reranking_advantages_lines(clause, executed_steps, language)
        )
    return (
        list(info_map.values()),
        _dedupe_preserve_order(update_parts),
        _dedupe_preserve_order(advice_parts),
    )


def _summarize_workflow_tasks(
    *,
    workflow_tasks: list[dict[str, Any]],
    executed_steps: list[dict[str, Any]],
    language: str,
    request_message: str,
) -> str:
    if not workflow_tasks:
        return _summarize_step_results(
            executed_steps, language=language, request_message=request_message
        )

    info_parts_by_key: dict[str, str] = {}
    update_parts: list[str] = []
    rejected_parts: list[str] = []
    advice_parts: list[str] = []
    for task in workflow_tasks:
        if not isinstance(task, dict):
            continue
        status = str(task.get("status") or "")
        if status == "completed":
            info_parts, task_updates, task_advice = _workflow_task_step_summaries(
                task, language
            )
            for step in (
                task.get("outcome", {}).get("executed_steps", [])
                if isinstance(task.get("outcome"), dict)
                else []
            ):
                if (
                    isinstance(step, dict)
                    and str(step.get("tool") or "") not in MUTATING_TOOLS
                ):
                    summary = _summarize_single_step(
                        str(step.get("tool") or ""),
                        step.get("result"),
                        language=language,
                    )
                    if summary:
                        info_parts_by_key[_info_summary_key(step)] = summary
            update_parts.extend(task_updates)
            advice_parts.extend(task_advice)
        elif status == "rejected":
            steps = task.get("steps", [])
            if isinstance(steps, list) and steps:
                rejected_parts.append(
                    _describe_pending_step(steps[0], language=language)
                )

    info_parts = _dedupe_preserve_order(list(info_parts_by_key.values()))
    update_parts = _dedupe_preserve_order(update_parts)
    advice_parts = _dedupe_preserve_order(advice_parts)
    rejected_parts = _dedupe_preserve_order(rejected_parts)

    sections = [
        "## Resume"
        if language == "fr"
        else ("## الملخص" if language == "ar" else "## Summary")
    ]
    if info_parts:
        sections.append(
            "### Informations collectees"
            if language == "fr"
            else (
                "### المعلومات التي تم جمعها"
                if language == "ar"
                else "### Information Gathered"
            )
        )
        sections.extend(f"- {item}" for item in info_parts)
    if update_parts:
        sections.append("")
        sections.append(
            "### Mises a jour appliquees"
            if language == "fr"
            else (
                "### التحديثات المطبقة" if language == "ar" else "### Updates Applied"
            )
        )
        sections.extend(f"- {item}" for item in update_parts)
    if rejected_parts:
        sections.append("")
        sections.append(
            "### Action Refusee"
            if language == "fr"
            else ("### الإجراء المرفوض" if language == "ar" else "### Rejected Action")
        )
        sections.extend(f"- {item}" for item in rejected_parts)
    if advice_parts:
        sections.append("")
        sections.append(
            "### Requested Guidance"
            if language == "fr"
            else (
                "### التوجيه المطلوب" if language == "ar" else "### Requested Guidance"
            )
        )
        sections.extend(f"- {item}" for item in advice_parts)
    return "\n".join(part for part in sections if part is not None).strip()


def _info_summary_key(step: dict[str, Any]) -> str:
    tool_name = str(step.get("tool") or "").strip() or "unknown_tool"
    result = step.get("result")
    if tool_name == "get_repo_config" and isinstance(result, dict):
        return f"{tool_name}:{result.get('scope', 'system')}"
    if tool_name in {
        "get_chunking_methods",
        "get_reranking_methods",
        "get_ingestion_status",
        "list_loaded_documents",
        "list_evaluation_reports",
    }:
        return tool_name
    return f"{tool_name}:{len(str(result))}"


def _dedupe_preserve_order(items: list[str]) -> list[str]:
    seen: set[str] = set()
    unique: list[str] = []
    for item in items:
        normalized = item.strip()
        if not normalized:
            continue
        key = normalized.lower()
        if key in seen:
            continue
        seen.add(key)
        unique.append(normalized)
    return unique


def _chunking_advantages_lines(
    message: str, executed_steps: list[dict[str, Any]], language: str
) -> list[str]:
    if not _is_chunking_advantages_request(message):
        return []
    methods_result = _latest_chunking_methods_result(executed_steps)
    if not isinstance(methods_result, dict):
        return []
    methods: list[str] = []
    for item in (
        methods_result.get("methods", [])
        if isinstance(methods_result.get("methods"), list)
        else []
    ):
        if not isinstance(item, dict) or not item.get("implemented"):
            continue
        name = str(item.get("name") or "").strip().lower()
        if name:
            methods.append(name)
    lines: list[str] = []
    for method in methods:
        line = _single_chunking_advantage(method, language)
        if line:
            lines.append(line)
    return _dedupe_preserve_order(lines)


def _split_request_clauses(message: str) -> list[str]:
    clauses = [
        clause.strip(" ,;")
        for clause in re.split(
            r"\b(?:and also|also|and then|then|and|et aussi|et puis|puis|ensuite)\b",
            str(message or ""),
            flags=re.IGNORECASE,
        )
        if clause.strip(" ,;")
    ]
    return clauses or [str(message or "").strip()]


def _is_chunking_methods_question(message: str) -> bool:
    lowered = str(message or "").lower()
    if any(
        token in lowered for token in ["chunk_strategy", "chunk_size", "chunk_overlap"]
    ):
        return False
    asks_about_chunking = bool(re.search(r"\b(chunking|chunk|chunks)\b", lowered))
    asks_for_options = bool(
        re.search(
            r"\b(available|supported|methods|method|strategies|options|types)\b",
            lowered,
        )
    )
    return asks_about_chunking and asks_for_options


def _is_chunking_advantages_request(message: str) -> bool:
    lowered = str(message or "").lower()
    asks_chunking = bool(
        re.search(
            r"(chunking|chunk|chunks|decoupage|d[eé]coupage|تقسيم|التقسيم)", lowered
        )
    )
    asks_advantages = bool(
        re.search(
            r"(advantage|advantages|benefit|benefits|pros|best for|when to use|avantage|avantages|فائدة|فوائد|ميزة|مزايا)",
            lowered,
        )
    )
    return asks_chunking and asks_advantages


def _is_reranking_methods_question(message: str) -> bool:
    lowered = str(message or "").lower()
    if "default_ranker_type" in lowered:
        return False
    if any(token in lowered for token in ["change", "set", "switch", "update"]):
        return False
    asks_about_reranking = bool(
        re.search(r"\b(rerank|reranking|reranker|ranker|ranking)\b", lowered)
    )
    asks_for_options = bool(
        re.search(
            r"\b(available|supported|methods|strategies|options|types)\b", lowered
        )
    )
    return asks_about_reranking and asks_for_options


def _is_reranking_advantages_request(message: str) -> bool:
    lowered = str(message or "").lower()
    asks_reranking = bool(
        re.search(
            r"(rerank|reranking|reranker|ranker|ranking|reranking|rerankers)", lowered
        )
    )
    asks_advantages = bool(
        re.search(
            r"(advantage|advantages|benefit|benefits|pros|best for|when to use|avantage|avantages|فائدة|فوائد|ميزة|مزايا)",
            lowered,
        )
    )
    return asks_reranking and asks_advantages


# Override the broad detectors with clause-aware versions so mixed requests
# keep the user's ordering and don't attach advice to the wrong topic.
def _is_chunking_advantages_request(message: str) -> bool:
    for clause in _split_request_clauses(message):
        lowered = clause.lower()
        asks_chunking = bool(
            re.search(
                r"(chunking|chunk|chunks|decoupage|d[eÃ©]coupage|ØªÙ‚Ø³ÙŠÙ…|Ø§Ù„ØªÙ‚Ø³ÙŠÙ…)",
                lowered,
            )
        )
        asks_advantages = bool(
            re.search(
                r"(advantage|advantages|benefit|benefits|pros|best for|when to use|avantage|avantages|ÙØ§Ø¦Ø¯Ø©|ÙÙˆØ§Ø¦Ø¯|Ù…ÙŠØ²Ø©|Ù…Ø²Ø§ÙŠØ§)",
                lowered,
            )
        )
        if asks_chunking and asks_advantages:
            return True
    return False


def _is_reranking_advantages_request(message: str) -> bool:
    for clause in _split_request_clauses(message):
        lowered = clause.lower()
        asks_reranking = bool(
            re.search(r"(rerank|reranking|reranker|ranker|ranking|rerankers)", lowered)
        )
        asks_advantages = bool(
            re.search(
                r"(advantage|advantages|benefit|benefits|pros|best for|when to use|avantage|avantages|ÙØ§Ø¦Ø¯Ø©|ÙÙˆØ§Ø¦Ø¯|Ù…ÙŠØ²Ø©|Ù…Ø²Ø§ÙŠØ§)",
                lowered,
            )
        )
        if asks_reranking and asks_advantages:
            return True
    return False


def _latest_chunking_methods_result(
    executed_steps: list[dict[str, Any]],
) -> dict[str, Any] | None:
    for step in reversed(executed_steps):
        if not isinstance(step, dict):
            continue
        if str(step.get("tool") or "") != "get_chunking_methods":
            continue
        result = step.get("result")
        if isinstance(result, dict):
            return result
    return None


def _latest_reranking_methods_result(
    executed_steps: list[dict[str, Any]],
) -> dict[str, Any] | None:
    for step in reversed(executed_steps):
        if not isinstance(step, dict):
            continue
        if str(step.get("tool") or "") != "get_reranking_methods":
            continue
        result = step.get("result")
        if isinstance(result, dict):
            return result
    return None


def _single_chunking_advantage(method: str, language: str) -> str:
    if language == "fr":
        if method == "late":
            return "`late`: conserve plus de contexte global, utile pour les documents longs."
        if method == "overlap":
            return (
                "`overlap`: reduit la perte d'information aux frontieres entre chunks."
            )
        if method == "semantic":
            return "`semantic`: suit les ruptures de sens, souvent plus precis pour la recherche."
        if method == "sentence":
            return "`sentence`: garde des unites linguistiques propres, utile pour des reponses tres fideles."
        if method == "late":
            return "`late`: يحافظ على سياق أوسع، ومفيد للمستندات الطويلة."
        if method == "overlap":
            return "`overlap`: يقلل فقدان المعلومات عند حدود الأجزاء."
        if method == "semantic":
            return "`semantic`: يقسم حسب المعنى، وغالبا يعطي دقة أعلى في الاسترجاع."
        if method == "sentence":
            return "`sentence`: يحافظ على جمل كاملة، مناسب لإجابات دقيقة النص."
    else:
        if method == "late":
            return "`late`: keeps broader context, which helps on long documents."
        if method == "overlap":
            return (
                "`overlap`: reduces boundary information loss between adjacent chunks."
            )
        if method == "semantic":
            return (
                "`semantic`: splits by meaning, usually improving retrieval precision."
            )
        if method == "sentence":
            return "`sentence`: preserves sentence boundaries for cleaner, quote-faithful answers."
    return ""


def _reranking_advantages_lines(
    message: str, executed_steps: list[dict[str, Any]], language: str
) -> list[str]:
    if not _is_reranking_advantages_request(message):
        return []
    methods_result = _latest_reranking_methods_result(executed_steps)
    if not isinstance(methods_result, dict):
        return []
    methods: list[str] = []
    for item in (
        methods_result.get("methods", [])
        if isinstance(methods_result.get("methods"), list)
        else []
    ):
        if not isinstance(item, dict) or not item.get("implemented"):
            continue
        name = str(item.get("name") or "").strip().lower()
        if name:
            methods.append(name)
    lines: list[str] = []
    for method in methods:
        line = _single_reranking_advantage(method, language)
        if line:
            lines.append(line)
    return _dedupe_preserve_order(lines)


def _single_reranking_advantage(method: str, language: str) -> str:
    if language == "fr":
        if method == "cross_encoder":
            return "`cross_encoder`: donne souvent le meilleur tri de pertinence, utile quand la precision compte le plus."
        if method == "llm_batch":
            return "`llm_batch`: gere mieux les nuances semantiques complexes, utile pour des requetes ambigues ou riches en contexte."
        if method == "none":
            return "`none`: le plus rapide et le moins couteux, utile quand la latence prime."
        if method == "cross_encoder":
            return "`cross_encoder`: يعطي عادة أفضل دقة في إعادة الترتيب عندما تكون جودة الصلة أهم شيء."
        if method == "llm_batch":
            return "`llm_batch`: أفضل في التقاط الفروق الدلالية الدقيقة، ومفيد للاستفسارات المعقدة."
        if method == "none":
            return "`none`: الأسرع والأقل تكلفة، ومناسب عندما تكون السرعة هي الأولوية."
    else:
        if method == "cross_encoder":
            return "`cross_encoder`: usually gives the strongest relevance ordering when precision matters most."
        if method == "llm_batch":
            return "`llm_batch`: handles more nuanced semantic judgments, which helps on complex queries."
        if method == "none":
            return (
                "`none`: fastest and cheapest, which helps when latency matters most."
            )
    return ""


def _describe_pending_step(step: dict[str, Any], language: str = "en") -> str:
    tool_name = str(step.get("tool") or "")
    arguments = (
        step.get("arguments", {}) if isinstance(step.get("arguments"), dict) else {}
    )
    if tool_name == "update_repo_config":
        scope = str(arguments.get("service_name") or "system")
        changes = arguments.get("changes", {})
        if language == "fr":
            return f"mettre a jour les parametres `{scope}` avec {changes}"
        if language == "ar":
            return f"ØªØ­Ø¯ÙŠØ« Ø¥Ø¹Ø¯Ø§Ø¯Ø§Øª `{scope}` Ø¨Ø§Ù„Ù‚ÙŠÙ… {changes}"
        return f"update the {scope} settings with {changes}"
    if tool_name == "delete_document_completely":
        if language == "fr":
            return f"supprimer le document `{arguments.get('document_id', '')}` et nettoyer les vecteurs"
        if language == "ar":
            return f"Ø­Ø°Ù Ø§Ù„Ù…Ø³ØªÙ†Ø¯ `{arguments.get('document_id', '')}` ÙˆØªÙ†Ø¸ÙŠÙ Ø§Ù„Ù…ØªØ¬Ù‡Ø§Øª"
        return f"delete document '{arguments.get('document_id', '')}' and clean vectors"
    if tool_name == "reindex_document":
        if language == "fr":
            return f"reindexer le document `{arguments.get('document_id', '')}`"
        if language == "ar":
            return f"Ø¥Ø¹Ø§Ø¯Ø© ÙÙ‡Ø±Ø³Ø© Ø§Ù„Ù…Ø³ØªÙ†Ø¯ `{arguments.get('document_id', '')}`"
        return f"reindex document '{arguments.get('document_id', '')}'"
    if tool_name == "reindex_validated_documents":
        return (
            "reindexer tous les documents valides"
            if language == "fr"
            else (
                "Ø¥Ø¹Ø§Ø¯Ø© ÙÙ‡Ø±Ø³Ø© Ø¬Ù…ÙŠØ¹ Ø§Ù„Ù…Ø³ØªÙ†Ø¯Ø§Øª Ø§Ù„Ù…Ø¹ØªÙ…Ø¯Ø©"
                if language == "ar"
                else "reindex all validated documents"
            )
        )
    if tool_name == "run_evaluation":
        dataset = arguments.get("dataset_path", "evals/sample_eval_dataset.json")
        if language == "fr":
            return f"lancer l'evaluation avec le dataset `{dataset}`"
        if language == "ar":
            return f"ØªØ´ØºÙŠÙ„ Ø§Ù„ØªÙ‚ÙŠÙŠÙ… Ø¨Ø§Ø³ØªØ®Ø¯Ø§Ù… Ù…Ø¬Ù…ÙˆØ¹Ø© Ø§Ù„Ø¨ÙŠØ§Ù†Ø§Øª `{dataset}`"
        return f"run evaluation with dataset '{dataset}'"
    if tool_name == "compare_evaluation_reports":
        baseline = arguments.get("baseline_report_id", "")
        candidate = arguments.get("candidate_report_id", "")
        if language == "fr":
            return f"comparer les rapports d'evaluation `{baseline}` et `{candidate}`"
        if language == "ar":
            return (
                f"Ù…Ù‚Ø§Ø±Ù†Ø© ØªÙ‚Ø±ÙŠØ±ÙŠ Ø§Ù„ØªÙ‚ÙŠÙŠÙ… `{baseline}` Ùˆ`{candidate}`"
            )
        return f"compare evaluation reports '{baseline}' and '{candidate}'"
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
            "## Ø§Ù„Ø¥Ø¬Ø±Ø§Ø¡ Ø§Ù„ØªØ§Ù„ÙŠ\n\n"
            "### ÙŠØªØ·Ù„Ø¨ ØªØ£ÙƒÙŠØ¯Ù‹Ø§\n"
            f"- {_describe_pending_step(step, language=language)}\n\n"
            "Ø£Ø±Ø³Ù„ **`confirm`** Ù„Ù„Ù…ØªØ§Ø¨Ø¹Ø©."
        )
    return (
        "## Next Action\n\n"
        "### Confirmation Required\n"
        f"- {_describe_pending_step(step, language=language)}\n\n"
        "Reply with **`confirm`** to continue."
    )


def _build_rejection_message(language: str = "en") -> str:
    if language == "fr":
        return "## Action Annulee\n\nLa modification en attente a ete refusee. Aucun changement n'a ete applique."
    if language == "ar":
        return "## تم الإلغاء\n\nتم رفض الإجراء المعلق. لم يتم تطبيق أي تغيير."
    return (
        "## Action Canceled\n\nThe pending change was rejected. No update was applied."
    )


def _summarize_rejected_flow(
    *,
    workflow_tasks: list[dict[str, Any]],
    settings: Settings,
    language: str,
    request_message: str,
) -> str:
    executed_steps: list[dict[str, Any]] = []
    for task in workflow_tasks:
        outcome = task.get("outcome", {}) if isinstance(task, dict) else {}
        steps = outcome.get("executed_steps", []) if isinstance(outcome, dict) else []
        if isinstance(steps, list):
            executed_steps.extend(step for step in steps if isinstance(step, dict))
    fallback_summary = (
        _summarize_workflow_tasks(
            workflow_tasks=workflow_tasks,
            executed_steps=executed_steps,
            language=language,
            request_message=request_message,
        )
        if workflow_tasks
        else _build_rejection_message(language)
    )
    if False:
        rejected_heading = "### الإجراء المرفوض"
    return _llm_summarize_mutation_outcome(
        settings=settings,
        fallback_summary=fallback_summary,
        executed_steps=executed_steps,
        request_message=request_message,
        language=language,
        workflow_tasks=workflow_tasks,
    )


def _make_summary_model(settings: Settings):
    if not settings.openai_key.strip():
        return None
    return ChatOpenAI(
        api_key=settings.openai_key,
        model=settings.admin_model,
        temperature=0.1,
    )


def _compact_step_for_llm(step: dict[str, Any]) -> dict[str, Any]:
    tool_name = str(step.get("tool") or "")
    result = step.get("result")
    compact: dict[str, Any] = {"tool": tool_name}
    if isinstance(result, dict):
        if tool_name == "update_repo_config":
            compact["scope"] = result.get("scope")
            compact["updated"] = result.get("updated", {})
        elif tool_name == "get_repo_config":
            compact["scope"] = result.get("scope")
            compact["config"] = result.get("config", {})
        elif tool_name in {"get_chunking_methods", "get_reranking_methods"}:
            compact["scope"] = result.get("scope")
            compact["current_strategy"] = result.get("current_strategy")
            compact["current_default_ranker_type"] = result.get(
                "current_default_ranker_type"
            )
            compact["methods"] = result.get("methods", [])
        else:
            compact["result"] = result
    else:
        compact["result"] = result
    compact["summary_line"] = _summarize_single_step(tool_name, result, language="en")
    return compact


def _llm_summarize_mutation_outcome(
    *,
    settings: Settings,
    fallback_summary: str,
    executed_steps: list[dict[str, Any]],
    request_message: str,
    language: str,
    workflow_tasks: list[dict[str, Any]] | None = None,
    rejected_pending_action: dict[str, Any] | None = None,
) -> str:
    model = _make_summary_model(settings)
    if model is None:
        return fallback_summary

    compact_steps = [
        _compact_step_for_llm(step) for step in executed_steps if isinstance(step, dict)
    ]
    rejected_step = None
    if isinstance(rejected_pending_action, dict):
        rejected_step = {
            "tool": str(rejected_pending_action.get("tool") or ""),
            "arguments": rejected_pending_action.get("arguments", {})
            if isinstance(rejected_pending_action.get("arguments"), dict)
            else {},
            "description": _describe_pending_step(
                rejected_pending_action, language="en"
            ),
        }

    try:
        response = model.invoke(
            [
                SystemMessage(
                    content=(
                        "your name is Synapse"
                        "You summarize completed admin workflows for a non-technical operator. "
                        "Write concise Markdown. Use the user's language when possible. "
                        "Summarize what was completed, what information mattered, and if a pending action was rejected, say so clearly. "
                        "Do not mention source code, repositories, environment files, models, or internal implementation details. "
                        "Do not duplicate the same state twice if there was a before/after check; prefer the final state. "
                        "If there is helpful operational advice, keep it to one short point only when it materially helps."
                    )
                ),
                HumanMessage(
                    content=(
                        f"Language: {language}\n"
                        f"Original user request: {request_message}\n"
                        f"Executed steps: {compact_steps}\n"
                        f"Workflow tasks: {workflow_tasks or []}\n"
                        f"Rejected pending action: {rejected_step}\n"
                        f"Fallback summary:\n{fallback_summary}"
                    )
                ),
            ]
        )
        content = getattr(response, "content", "")
        if isinstance(content, list):
            content = " ".join(
                part.get("text", "") for part in content if isinstance(part, dict)
            )
        text = str(content or "").strip()
        if not text:
            return fallback_summary
        if workflow_tasks and not _llm_summary_covers_workflow(text, workflow_tasks):
            return fallback_summary
        return text
    except Exception:
        return fallback_summary


def _llm_summary_covers_workflow(
    text: str, workflow_tasks: list[dict[str, Any]]
) -> bool:
    lowered = str(text or "").lower()
    for task in workflow_tasks:
        if not isinstance(task, dict):
            continue
        status = str(task.get("status") or "")
        if status not in {"completed", "rejected"}:
            return False
        steps = task.get("steps", [])
        first_step = steps[0] if isinstance(steps, list) and steps else {}
        tool_name = str(first_step.get("tool") or "")
        if status == "rejected":
            service_name = str(
                (
                    first_step.get("arguments", {})
                    if isinstance(first_step.get("arguments"), dict)
                    else {}
                ).get("service_name")
                or ""
            ).lower()
            if (
                "rejected" not in lowered
                and "canceled" not in lowered
                and "cancelled" not in lowered
            ):
                return False
            if service_name and service_name not in lowered:
                return False
            continue
        outcome = (
            task.get("outcome", {}) if isinstance(task.get("outcome"), dict) else {}
        )
        executed_steps = (
            outcome.get("executed_steps", [])
            if isinstance(outcome.get("executed_steps"), list)
            else []
        )
        if tool_name == "update_repo_config":
            result = (
                executed_steps[0].get("result", {})
                if executed_steps and isinstance(executed_steps[0], dict)
                else {}
            )
            updated = result.get("updated", {}) if isinstance(result, dict) else {}
            values = [str(value).lower() for value in updated.values()]
            if values and not any(value in lowered for value in values):
                return False
        elif tool_name in {"get_chunking_methods", "get_reranking_methods"}:
            result = (
                executed_steps[-1].get("result", {})
                if executed_steps and isinstance(executed_steps[-1], dict)
                else {}
            )
            methods = result.get("methods", []) if isinstance(result, dict) else []
            implemented = [
                str(item.get("name") or "").lower()
                for item in methods
                if isinstance(item, dict) and item.get("implemented")
            ]
            if implemented and not any(name in lowered for name in implemented):
                return False
    return True


def _ensure_markdown_response(
    response: AdminChatResponse, language: str = "en"
) -> AdminChatResponse:
    answer = str(response.answer or "").strip()
    if not answer:
        return response

    if response.requires_confirmation and response.pending_action is not None:
        confirmation_only = _build_confirmation_prompt(
            response.pending_action.model_dump(), language=language
        )
        return response.model_copy(update={"answer": confirmation_only})

    # Keep already-structured Markdown, but ensure confirmation block is present when needed.
    if answer.startswith("#"):
        expected = (
            "## Prochaine Action"
            if language == "fr"
            else (
                "## Ø§Ù„Ø¥Ø¬Ø±Ø§Ø¡ Ø§Ù„ØªØ§Ù„ÙŠ"
                if language == "ar"
                else "## Next Action"
            )
        )
        if (
            response.requires_confirmation
            and expected not in answer
            and response.pending_action is not None
        ):
            next_block = _build_confirmation_prompt(
                response.pending_action.model_dump(), language=language
            )
            return response.model_copy(update={"answer": f"{answer}\n\n{next_block}"})
        return response

    heading = (
        "## Resume"
        if language == "fr"
        else ("## Ø§Ù„Ù…Ù„Ø®Øµ" if language == "ar" else "## Summary")
    )
    if response.mode == "advisory":
        heading = (
            "## Conseil"
            if language == "fr"
            else ("## Ù†ØµÙŠØ­Ø©" if language == "ar" else "## Advice")
        )
    elif response.mode == "inspect":
        heading = (
            "## Inspection"
            if language == "fr"
            else ("## ÙØ­Øµ" if language == "ar" else "## Inspection")
        )
    elif response.mode == "mutate":
        heading = (
            "## Resume Des Modifications"
            if language == "fr"
            else (
                "## Ù…Ù„Ø®Øµ Ø§Ù„ØªØ­Ø¯ÙŠØ«" if language == "ar" else "## Update Summary"
            )
        )

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
    if any(
        re.search(pattern, lowered)
        for pattern in [
            r"\bbonjour\b",
            r"\bmerci\b",
            r"\bquelle\b",
            r"\bquelles\b",
            r"\bquel\b",
            r"\bpourquoi\b",
            r"\bcomment\b",
            r"\bparametres\b",
            r"\bchanger\b",
            r"\bmodifie(?:r|z)\b",
        ]
    ):
        return "fr"
    generic_follow_up = lowered in {
        "ok",
        "yes",
        "confirm",
        "continue",
        "go",
        "done",
        "oui",
        "نعم",
        "تابع",
    }
    if (
        generic_follow_up
        and isinstance(preferred_language, str)
        and preferred_language.strip() in {"en", "fr", "ar"}
    ):
        return preferred_language.strip()
    return "en"


def _required_read_tools_from_message(message: str) -> list[str]:
    required: list[str] = []
    if _is_chunking_methods_question(message) or _is_chunking_advantages_request(
        message
    ):
        required.append("get_chunking_methods")
    if _is_reranking_methods_question(message) or _is_reranking_advantages_request(
        message
    ):
        required.append("get_reranking_methods")
    return required


def _request_coverage_lines(
    message: str, executed_steps: list[dict[str, Any]], language: str
) -> list[str]:
    required = _required_read_tools_from_message(message)
    if not required:
        return []
    executed = {
        str(step.get("tool") or "") for step in executed_steps if isinstance(step, dict)
    }
    lines = []
    for tool in required:
        done = tool in executed
        if tool == "get_chunking_methods":
            label = (
                "Chunking strategies covered"
                if language == "en"
                else (
                    "Strategies de decoupage couvertes"
                    if language == "fr"
                    else "ØªÙ…Øª ØªØºØ·ÙŠØ© Ø§Ø³ØªØ±Ø§ØªÙŠØ¬ÙŠØ§Øª Ø§Ù„ØªÙ‚Ø³ÙŠÙ…"
                )
            )
        elif tool == "get_reranking_methods":
            label = (
                "Reranking strategies covered"
                if language == "en"
                else (
                    "Strategies de reranking couvertes"
                    if language == "fr"
                    else "ØªÙ…Øª ØªØºØ·ÙŠØ© Ø§Ø³ØªØ±Ø§ØªÙŠØ¬ÙŠØ§Øª Ø¥Ø¹Ø§Ø¯Ø© Ø§Ù„ØªØ±ØªÙŠØ¨"
                )
            )
        else:
            label = tool
        lines.append(f"- [{'x' if done else ' '}] {label}")
    return lines
