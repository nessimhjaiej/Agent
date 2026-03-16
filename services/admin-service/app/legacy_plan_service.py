import re
from collections.abc import Callable
from pathlib import Path

from app.models import AdminRequestContext, PlanStep, PlannedAction
from app.operation_history import AdminOperationHistoryStore
from app.planner.confirmation import needs_confirmation
from app.planner.tool_selector import ToolSelector
from app.response_factory import AdminResponseFactory
from app.schemas import AdminActivityItem
from app.tools.knowledge_tools import (
    resolve_document_reference,
    resolve_synced_supabase_reference,
    resolve_supabase_document_reference,
)
from app.tools.registry import ToolRegistry


class LegacyPlanService:
    def __init__(
        self,
        *,
        settings,
        selector: ToolSelector,
        registry: ToolRegistry,
        security_client,
        retrieval_client,
        history_store: AdminOperationHistoryStore,
        supabase_documents_client,
        explainer_client,
        response_factory: AdminResponseFactory,
        emit: Callable[[Callable[[dict], None] | None, dict], None],
    ) -> None:
        self._settings = settings
        self._selector = selector
        self._registry = registry
        self._security_client = security_client
        self._retrieval_client = retrieval_client
        self._history_store = history_store
        self._supabase_documents_client = supabase_documents_client
        self._explainer_client = explainer_client
        self._response_factory = response_factory
        self._emit = emit

    def handle(
        self,
        context: AdminRequestContext,
        progress_callback: Callable[[dict], None] | None = None,
    ):
        self._emit(
            progress_callback,
            {
                "type": "activity",
                "activity": [
                    {
                        "phase": "planning",
                        "status": "in_progress",
                        "title": "Using Plan mode",
                        "detail": "Resolving the request into an executable admin plan. Informational questions should be asked in Q&A mode.",
                    }
                ],
            },
        )
        planned = self.resolve_action(context)
        self.publish_event("admin.agent.intent_resolved", context, planned, {})
        steps = self.resolve_steps(planned)
        self._emit(
            progress_callback,
            {
                "type": "activity",
                "thinking_summary": self._response_factory.build_planning_summary(
                    planned,
                    steps,
                    requires_confirmation=self.requires_confirmation(planned, steps) and not context.confirm,
                ),
                "activity": [
                    {
                        "phase": "planning",
                        "status": "completed",
                        "title": "Resolved admin intent",
                        "detail": (
                            "This request belongs in Q&A mode."
                            if planned.mode == "qa"
                            else f"Built a {len(steps)}-step admin plan."
                        ),
                    }
                ],
            },
        )

        if planned.mode == "qa":
            return self._response_factory.build_mode_switch_response(
                context=context,
                response_mode="qa",
                answer=(
                    "You are in Plan mode, but this message looks informational rather than operational. "
                    "Switch to Q&A mode to ask questions, explanations, or comparisons."
                ),
                thinking_summary="I stayed in Plan mode and declined to answer an informational request there.",
                activity=[
                    AdminActivityItem(
                        phase="planning",
                        status="completed",
                        title="Plan mode kept active",
                        detail="The planner classified this as an informational request, so it should be retried in Q&A mode.",
                    )
                ],
                intent=planned.intent,
            )

        if not steps:
            return self._response_factory.build_response(
                status="error",
                mode="tool_call",
                selected_mode=context.selected_mode,
                session_id=context.session_id,
                message=context.message,
                answer="I could not determine which admin action to run.",
                intent=planned.intent,
                tool=planned.tool_name,
                arguments=planned.arguments,
                requires_confirmation=False,
                executed=False,
                pending_action=None,
                citations=[],
                thinking_summary="I did not find a supported admin action for this request.",
                activity=[
                    AdminActivityItem(
                        phase="planning",
                        status="failed",
                        title="No executable admin action found",
                        detail="The request did not map cleanly to a known tool or plan.",
                    )
                ],
                result={},
            )

        if self.requires_confirmation(planned, steps) and not context.confirm:
            activity = self._response_factory.build_confirmation_activity(steps)
            self._emit(
                progress_callback,
                {
                    "type": "activity",
                    "thinking_summary": self._response_factory.build_planning_summary(planned, steps, True),
                    "activity": [item.model_dump() for item in activity],
                },
            )
            return self._response_factory.build_response(
                status="needs_confirmation",
                mode="tool_call",
                selected_mode=context.selected_mode,
                session_id=context.session_id,
                message=context.message,
                answer=planned.answer or f"Are you sure you want to run '{planned.tool_name or planned.intent}'?",
                intent=planned.intent,
                tool=planned.tool_name,
                arguments=planned.arguments,
                requires_confirmation=True,
                executed=False,
                pending_action=self._response_factory.build_pending_action(
                    intent=planned.intent,
                    tool=planned.tool_name or planned.intent,
                    arguments=planned.arguments,
                    steps=steps,
                ),
                citations=[],
                thinking_summary=self._response_factory.build_planning_summary(planned, steps, True),
                activity=activity,
                result={"steps": [{"tool": step.tool_name, "arguments": step.arguments} for step in steps]},
            )

        execution_payload = self.execute_steps(steps, progress_callback=progress_callback)
        event_type = (
            "admin.agent.tool_execution_succeeded"
            if execution_payload.get("status") == "ok"
            else "admin.agent.tool_execution_failed"
        )
        self.publish_event(event_type, context, planned, execution_payload)
        self.record_reversible_steps(context, execution_payload)
        return self._response_factory.build_response(
            status=str(execution_payload.get("status", "ok")),
            mode="tool_call",
            selected_mode=context.selected_mode,
            session_id=context.session_id,
            message=context.message,
            answer=str(execution_payload.get("answer", "")),
            intent=planned.intent,
            tool=planned.tool_name,
            arguments=planned.arguments,
            requires_confirmation=False,
            executed=bool(execution_payload.get("executed", True)),
            pending_action=None,
            citations=[],
            thinking_summary=self._response_factory.build_execution_summary(planned, execution_payload),
            activity=self._response_factory.build_execution_activity(steps, execution_payload),
            result=execution_payload,
        )

    def handle_confirmed(
        self,
        context: AdminRequestContext,
        progress_callback: Callable[[dict], None] | None = None,
    ):
        self._emit(
            progress_callback,
            {
                "type": "activity",
                "activity": [
                    {
                        "phase": "planning",
                        "status": "completed",
                        "title": "Confirmed admin plan",
                        "detail": "Executing the previously approved plan.",
                    }
                ],
            },
        )
        planned = self.resolve_action(context)
        steps = self.resolve_steps(planned)
        execution_payload = self.execute_steps(steps, progress_callback=progress_callback)
        event_type = (
            "admin.agent.tool_execution_succeeded"
            if execution_payload.get("status") == "ok"
            else "admin.agent.tool_execution_failed"
        )
        self.publish_event(event_type, context, planned, execution_payload)
        self.record_reversible_steps(context, execution_payload)
        return self._response_factory.build_response(
            status=str(execution_payload.get("status", "ok")),
            mode="tool_call",
            selected_mode=context.selected_mode,
            session_id=context.session_id,
            message=context.message,
            answer=str(execution_payload.get("answer", "")),
            intent=planned.intent,
            tool=planned.tool_name,
            arguments=planned.arguments,
            requires_confirmation=False,
            executed=bool(execution_payload.get("executed", True)),
            pending_action=None,
            citations=[],
            thinking_summary=self._response_factory.build_execution_summary(planned, execution_payload),
            activity=self._response_factory.build_execution_activity(steps, execution_payload),
            result=execution_payload,
        )

    def resolve_action(self, context: AdminRequestContext) -> PlannedAction:
        if context.confirm and context.pending_action is not None:
            return PlannedAction(
                mode="tool_call",
                intent=context.pending_action.intent,
                tool_name=context.pending_action.tool_name,
                arguments=context.pending_action.arguments,
                answer="Confirmed. Executing the requested admin plan.",
                requires_confirmation=False,
                steps=context.pending_action.steps,
            )
        planned = self._selector.select(context)
        if planned.intent == "revert_changes":
            return self.build_revert_plan(context, planned)
        return self.enrich_document_reference(planned)

    def resolve_steps(self, planned: PlannedAction) -> list[PlanStep]:
        if planned.steps:
            return planned.steps
        if planned.tool_name is None:
            return []
        return [PlanStep(tool_name=planned.tool_name, arguments=planned.arguments)]

    def requires_confirmation(self, planned: PlannedAction, steps: list[PlanStep]) -> bool:
        if planned.requires_confirmation:
            return True
        return any(
            needs_confirmation(
                step.tool_name,
                require_confirmation_for_mutations=self._settings.require_confirmation_for_mutations,
            )
            for step in steps
        )

    def execute_steps(
        self,
        steps: list[PlanStep],
        progress_callback: Callable[[dict], None] | None = None,
    ) -> dict:
        executed_steps: list[dict] = []
        final_answer = ""
        overall_status = "ok"
        executed_any = False

        for index, step in enumerate(steps, start=1):
            self._emit(
                progress_callback,
                {
                    "type": "activity",
                    "activity": [
                        {
                            "phase": "execution",
                            "status": "in_progress",
                            "title": f"Running step {index}: {step.tool_name}",
                            "detail": "Calling the admin tool now.",
                            "tool": step.tool_name,
                            "arguments": step.arguments,
                        }
                    ],
                },
            )
            tool = self._registry.get(step.tool_name)
            execution = tool.execute(step.arguments)
            executed_any = executed_any or execution.executed
            final_answer = execution.answer or final_answer
            step_payload = {
                "tool": step.tool_name,
                "arguments": step.arguments,
                "status": execution.status,
                "answer": execution.answer,
                "result": execution.result,
                "executed": execution.executed,
            }
            executed_steps.append(step_payload)
            self._emit(
                progress_callback,
                {
                    "type": "activity",
                    "activity": [
                        {
                            "phase": "execution",
                            "status": "completed" if execution.status == "ok" else "failed",
                            "title": f"Finished step {index}: {step.tool_name}",
                            "detail": execution.answer,
                            "tool": step.tool_name,
                            "arguments": step.arguments,
                        }
                    ],
                },
            )
            if execution.status != "ok":
                overall_status = execution.status
                break

        if len(executed_steps) > 1 and overall_status == "ok":
            final_answer = "Completed admin plan successfully."

        return {
            "status": overall_status,
            "answer": final_answer,
            "executed": executed_any,
            "steps": executed_steps,
            "step_count": len(executed_steps),
        }

    def load_latest_evaluation_summary(self) -> dict | None:
        try:
            tool = self._registry.get("get_evaluation_report")
            execution = tool.execute({})
        except Exception:
            return None
        if execution.status != "ok" or not isinstance(execution.result, dict):
            return None
        return {
            "report_path": execution.result.get("report_path", ""),
            "generated_at_utc": execution.result.get("generated_at_utc", ""),
            "summary": execution.result.get("summary", {}) if isinstance(execution.result.get("summary"), dict) else {},
        }

    def build_evaluation_comparison(self, execution_payload: dict, baseline_report: dict | None) -> dict | None:
        steps = execution_payload.get("steps", [])
        if not isinstance(steps, list):
            return None
        latest_eval_step = next(
            (
                step
                for step in reversed(steps)
                if isinstance(step, dict)
                and step.get("tool") == "run_rag_evaluation"
                and isinstance(step.get("result"), dict)
            ),
            None,
        )
        if latest_eval_step is None:
            return None
        latest_result = latest_eval_step.get("result", {})
        latest_summary = latest_result.get("summary", {}) if isinstance(latest_result.get("summary"), dict) else {}
        baseline_summary = baseline_report.get("summary", {}) if isinstance(baseline_report, dict) else {}
        deltas: dict[str, float] = {}
        for metric, value in latest_summary.items():
            if metric not in baseline_summary:
                continue
            try:
                deltas[str(metric)] = round(float(value) - float(baseline_summary[metric]), 6)
            except (TypeError, ValueError):
                continue
        summary_parts: list[str] = []
        if deltas:
            for metric, delta in sorted(deltas.items()):
                direction = "improved" if delta > 0 else "declined" if delta < 0 else "held steady"
                summary_parts.append(f"{metric} {direction} by {abs(delta):.3f}")
        else:
            summary_parts.append("A post-change evaluation was run, but there was no prior numeric report to compare against.")
        return {
            "baseline_report_path": baseline_report.get("report_path", "") if isinstance(baseline_report, dict) else "",
            "latest_report_path": latest_result.get("report_path", ""),
            "baseline_summary": baseline_summary,
            "latest_summary": latest_summary,
            "deltas": deltas,
            "summary_text": "; ".join(summary_parts),
        }

    def publish_event(
        self,
        event_type: str,
        context: AdminRequestContext,
        planned: PlannedAction,
        result: dict,
    ) -> None:
        self._security_client.publish_event(
            {
                "event_type": event_type,
                "session_id": context.session_id,
                "message": context.message,
                "actor": (
                    {
                        "id": context.actor.id,
                        "email": context.actor.email,
                        "role": context.actor.role,
                    }
                    if context.actor
                    else None
                ),
                "mode": planned.mode,
                "intent": planned.intent,
                "tool": planned.tool_name,
                "arguments": planned.arguments,
                "steps": [
                    {"tool": step.tool_name, "arguments": step.arguments}
                    for step in self.resolve_steps(planned)
                ],
                "result": result,
            }
        )

    def record_reversible_steps(self, context: AdminRequestContext, execution_payload: dict) -> None:
        session_id = (context.session_id or "").strip()
        if not session_id:
            return
        steps = execution_payload.get("steps", [])
        if not isinstance(steps, list):
            return
        for step in steps:
            if not isinstance(step, dict) or step.get("status") != "ok":
                continue
            result = step.get("result", {})
            if not isinstance(result, dict):
                continue
            rollback = result.get("rollback")
            if not isinstance(rollback, dict):
                continue
            arguments = step.get("arguments", {})
            if not isinstance(arguments, dict):
                arguments = {}
            self._history_store.append(
                {
                    "session_id": session_id,
                    "tool_name": step.get("tool"),
                    "arguments": arguments,
                    "rollback": rollback,
                    "reversible": True,
                    "restart_services": arguments.get("restart_services", []),
                }
            )

    def enrich_document_reference(self, planned: PlannedAction) -> PlannedAction:
        if planned.tool_name == "delete_document":
            return self._enrich_supabase_delete_reference(planned)
        if planned.tool_name != "embed_document":
            return planned
        document_query = str(planned.arguments.get("document_query", "")).strip()
        target_relative_path = str(planned.arguments.get("target_relative_path", "")).strip()
        semantic_first = self._should_use_semantic_document_resolution(document_query)
        resolution = {"status": "unresolved", "target_relative_path": None, "candidates": []}
        if not semantic_first:
            resolution = resolve_document_reference(
                document_query,
                raw_root=str(planned.arguments.get("raw_root", "shared/raw_data")),
                local_root=str(planned.arguments.get("local_root", "shared/raw_data")),
            )
        if resolution["status"] == "resolved" and target_relative_path not in {"", "UNKNOWN_DOCUMENT"}:
            return planned
        if resolution["status"] == "ambiguous":
            candidates = [str(item) for item in resolution.get("candidates", [])]
            chosen = self._choose_document_candidate(document_query, candidates)
            if chosen:
                resolution = {
                    "status": "resolved",
                    "target_relative_path": chosen,
                    "candidates": candidates,
                }
        if resolution["status"] != "resolved":
            semantic_paths = self._resolve_documents_by_semantic_search(document_query)
            if len(semantic_paths) > 1 and planned.tool_name == "delete_document":
                listed = "\n".join(f"- {path}" for path in semantic_paths)
                return PlannedAction(
                    mode="tool_call",
                    intent="delete_documents_batch",
                    tool_name="delete_documents_batch",
                    arguments={"target_relative_paths": semantic_paths, "document_query": document_query},
                    answer=(
                        "I found multiple indexed files that match your request. "
                        "Deleting them is irreversible. Confirm to delete these files:\n"
                        f"{listed}"
                    ),
                    requires_confirmation=True,
                    steps=[],
                )
            if len(semantic_paths) == 1:
                resolution = {
                    "status": "resolved",
                    "target_relative_path": semantic_paths[0],
                    "candidates": semantic_paths,
                }
        if resolution["status"] != "resolved":
            return planned
        resolved_path = str(resolution["target_relative_path"])
        arguments = dict(planned.arguments)
        arguments["target_relative_path"] = resolved_path
        answer = planned.answer.replace("UNKNOWN_DOCUMENT", resolved_path)
        return PlannedAction(
            mode=planned.mode,
            intent=planned.intent,
            tool_name=planned.tool_name,
            arguments=arguments,
            answer=answer,
            requires_confirmation=planned.requires_confirmation,
            steps=planned.steps,
        )

    def _enrich_supabase_delete_reference(self, planned: PlannedAction) -> PlannedAction:
        document_query = str(planned.arguments.get("document_query", "")).strip()
        try:
            documents = self._supabase_documents_client.list_documents()
        except Exception:
            documents = []
        resolution = resolve_supabase_document_reference(document_query, documents)
        if resolution["status"] == "ambiguous":
            candidates = [str(item) for item in resolution.get("candidates", [])]
            chosen = self._choose_document_candidate(document_query, candidates)
            if chosen:
                resolution = {"status": "resolved", "storage_path": chosen, "candidates": candidates}
        if resolution["status"] == "resolved":
            storage_path = str(resolution["storage_path"])
            arguments = dict(planned.arguments)
            arguments["target_relative_path"] = f"supabase/{storage_path}"
            answer = planned.answer.replace("UNKNOWN_DOCUMENT", f"supabase/{storage_path}")
            return PlannedAction(
                mode=planned.mode,
                intent=planned.intent,
                tool_name=planned.tool_name,
                arguments=arguments,
                answer=answer,
                requires_confirmation=planned.requires_confirmation,
                steps=planned.steps,
            )
        semantic_paths = self._resolve_documents_by_semantic_search(document_query)
        if len(semantic_paths) > 1:
            listed = "\n".join(f"- {path}" for path in semantic_paths)
            return PlannedAction(
                mode="tool_call",
                intent="delete_documents_batch",
                tool_name="delete_documents_batch",
                arguments={
                    "target_relative_paths": semantic_paths,
                    "document_query": document_query,
                    "cleanup_index": True,
                },
                answer=(
                    "I found multiple Supabase indexed files that match your request. "
                    "Deleting them will remove them from Supabase and clear their indexed Weaviate chunks. "
                    "This deletion is irreversible. Confirm to delete these files:\n"
                    f"{listed}"
                ),
                requires_confirmation=True,
                steps=[],
            )
        if len(semantic_paths) == 1:
            storage_path = semantic_paths[0].removeprefix("supabase/").lstrip("/")
            arguments = dict(planned.arguments)
            arguments["target_relative_path"] = f"supabase/{storage_path}"
            answer = planned.answer.replace("UNKNOWN_DOCUMENT", f"supabase/{storage_path}")
            return PlannedAction(
                mode=planned.mode,
                intent=planned.intent,
                tool_name=planned.tool_name,
                arguments=arguments,
                answer=answer,
                requires_confirmation=planned.requires_confirmation,
                steps=planned.steps,
            )
        mirror_resolution = resolve_synced_supabase_reference(
            document_query,
            raw_root=str(planned.arguments.get("raw_root", "shared/raw_data/supabase")),
            local_root=str(planned.arguments.get("local_root", "shared/raw_data")),
        )
        if mirror_resolution["status"] == "resolved":
            relative_path = str(mirror_resolution["target_relative_path"]).lstrip("/")
            arguments = dict(planned.arguments)
            arguments["target_relative_path"] = (
                relative_path if relative_path.startswith("supabase/") else f"supabase/{relative_path}"
            )
            answer = planned.answer.replace("UNKNOWN_DOCUMENT", arguments["target_relative_path"])
            return PlannedAction(
                mode=planned.mode,
                intent=planned.intent,
                tool_name=planned.tool_name,
                arguments=arguments,
                answer=answer,
                requires_confirmation=planned.requires_confirmation,
                steps=planned.steps,
            )
        return planned

    def _choose_document_candidate(self, query: str, candidates: list[str]) -> str | None:
        if not candidates or self._explainer_client is None:
            return None
        try:
            raw_choice = self._explainer_client.complete_text(
                system_prompt=(
                    "You choose the single best matching document path for an admin action. "
                    "Return exactly one candidate path from the provided list, or NONE if nothing clearly matches."
                ),
                user_prompt=(f"User request: {query.strip()}\n\n" f"Candidates:\n- " + "\n- ".join(candidates)),
            ).strip()
        except Exception:
            return None
        normalized_choice = raw_choice.strip().strip("'\"")
        for candidate in candidates:
            if normalized_choice == candidate:
                return candidate
        return None

    def _should_use_semantic_document_resolution(self, query: str) -> bool:
        lowered = query.lower()
        semantic_markers = (
            "files ",
            "documents ",
            "contain",
            "contains",
            "information from",
            "from 19",
            "from 20",
            "year",
            "format",
            "pdf",
            "txt",
            "md",
            "docx",
        )
        return any(marker in lowered for marker in semantic_markers)

    def _resolve_documents_by_semantic_search(self, query: str) -> list[str]:
        if not query.strip():
            return []
        try:
            payload = self._retrieval_client.search(
                query=query,
                mode="hybrid",
                top_k_retrieve=16,
                top_k_return=16,
            )
        except Exception:
            return []
        chunks = payload.get("chunks", [])
        if not isinstance(chunks, list):
            return []
        resolved_paths: list[str] = []
        seen: set[str] = set()
        requested_format = self._extract_requested_format(query)
        requested_year = self._extract_requested_year(query)
        for item in chunks:
            if not isinstance(item, dict):
                continue
            metadata = item.get("metadata", {})
            if not isinstance(metadata, dict):
                metadata = {}
            relative_path = self._relative_path_from_metadata(metadata)
            if not relative_path or relative_path in seen or not relative_path.startswith("supabase/"):
                continue
            filename = Path(relative_path).name.lower()
            if requested_format and not filename.endswith(f".{requested_format}"):
                continue
            if requested_year:
                path_years = self._extract_years(relative_path)
                if path_years:
                    if requested_year not in path_years:
                        continue
                else:
                    chunk_text = str(item.get("chunk_text", ""))
                    if requested_year not in chunk_text:
                        continue
            seen.add(relative_path)
            resolved_paths.append(relative_path)
        return resolved_paths[:8]

    def _relative_path_from_metadata(self, metadata: dict) -> str | None:
        source_uri = metadata.get("source_uri")
        if not isinstance(source_uri, str) or not source_uri.strip():
            return None
        raw = source_uri.strip().replace("\\", "/")
        marker = "/shared/raw_data/"
        if marker in raw:
            return raw.split(marker, 1)[1].strip("/")
        local_marker = "shared/raw_data/"
        if local_marker in raw:
            return raw.split(local_marker, 1)[1].strip("/")
        return None

    def _extract_requested_format(self, query: str) -> str | None:
        lowered = query.lower()
        for ext in ("pdf", "md", "txt", "docx"):
            if ext in lowered:
                return ext
        return None

    def _extract_requested_year(self, query: str) -> str | None:
        for token in query.split():
            stripped = token.strip(".,!?()[]{}")
            if len(stripped) == 4 and stripped.isdigit() and stripped.startswith(("19", "20")):
                return stripped
        return None

    def _extract_years(self, text: str) -> set[str]:
        return set(match.group(0) for match in re.finditer(r"(?:19|20)\d{2}", text))

    def build_revert_plan(self, context: AdminRequestContext, planned: PlannedAction) -> PlannedAction:
        session_id = (context.session_id or "").strip()
        if not session_id:
            return PlannedAction(
                mode="tool_call",
                intent="revert_changes",
                tool_name=None,
                arguments=planned.arguments,
                answer="I need a stable session id before I can look up prior reversible changes to undo.",
                requires_confirmation=False,
                steps=[],
            )
        count = int(planned.arguments.get("count", 1) or 1)
        tool_names_raw = planned.arguments.get("tool_names", [])
        tool_names = tool_names_raw if isinstance(tool_names_raw, list) and tool_names_raw else None
        records = self._history_store.get_recent(session_id=session_id, limit=count, tool_names=tool_names)
        if not records:
            return PlannedAction(
                mode="tool_call",
                intent="revert_changes",
                tool_name=None,
                arguments=planned.arguments,
                answer="I could not find any recent reversible changes in this admin session that match your request.",
                requires_confirmation=False,
                steps=[],
            )
        steps: list[PlanStep] = []
        restart_services: list[str] = []
        summary_lines: list[str] = []
        for record in records:
            rollback = record.get("rollback", {})
            if not isinstance(rollback, dict):
                continue
            rollback_tool = rollback.get("tool")
            rollback_args = rollback.get("arguments", {})
            if not isinstance(rollback_tool, str) or not rollback_tool.strip():
                continue
            if not isinstance(rollback_args, dict):
                rollback_args = {}
            steps.append(PlanStep(tool_name=rollback_tool, arguments=rollback_args))
            summary_lines.append(f"- {record.get('tool_name')} at {record.get('recorded_at_utc', 'unknown time')}")
            record_services = record.get("restart_services", [])
            if isinstance(record_services, list):
                for service in record_services:
                    service_name = str(service).strip()
                    if service_name and service_name not in restart_services:
                        restart_services.append(service_name)
        if restart_services:
            steps.append(
                PlanStep(
                    tool_name="restart_services",
                    arguments={"services": restart_services, "delay_seconds": 2},
                )
            )
        if not steps:
            return PlannedAction(
                mode="tool_call",
                intent="revert_changes",
                tool_name=None,
                arguments=planned.arguments,
                answer="I found matching history entries, but none contained a usable rollback action.",
                requires_confirmation=False,
                steps=[],
            )
        return PlannedAction(
            mode="tool_call",
            intent="revert_changes",
            tool_name="revert_changes",
            arguments=planned.arguments,
            answer=(
                "I found recent reversible changes in this admin session. "
                "Confirm to revert them in reverse order:\n" + "\n".join(summary_lines)
            ),
            requires_confirmation=True,
            steps=steps,
        )
