from __future__ import annotations

import json
from collections.abc import Callable

from app.models import AdminRequestContext
from app.response_factory import AdminResponseFactory
from app.schemas import AdminActivityItem


class FastPathPlanService:
    def __init__(
        self,
        *,
        registry,
        explainer_client,
        response_factory: AdminResponseFactory,
        bundle_catalog: dict[str, dict],
        emit: Callable[[Callable[[dict], None] | None, dict], None],
    ) -> None:
        self._registry = registry
        self._explainer_client = explainer_client
        self._response_factory = response_factory
        self._bundle_catalog = bundle_catalog
        self._emit = emit

    def handle(
        self,
        context: AdminRequestContext,
        *,
        bundle_id: str,
        subject: str,
        reason: str,
        progress_callback: Callable[[dict], None] | None = None,
    ):
        bundle = self._bundle_catalog[bundle_id]
        tool_names = [str(item) for item in bundle.get("tools", []) if str(item).strip()]
        self._emit(
            progress_callback,
            {
                "type": "activity",
                "activity": [
                    {
                        "phase": "planning",
                        "status": "in_progress",
                        "title": "Running fast read-only path",
                        "detail": f"Using the semantic fast path for '{subject or bundle_id}'.",
                    }
                ],
            },
        )

        observations: list[dict] = []
        activity: list[AdminActivityItem] = [
            AdminActivityItem(
                phase="planning",
                status="completed",
                title="Semantic route selected",
                detail=reason or f"Selected fast read-only bundle '{bundle_id}'.",
            )
        ]
        for tool_name in tool_names:
            self._emit(
                progress_callback,
                {
                    "type": "agent_tool_call",
                    "tool_name": tool_name,
                    "arguments": {},
                },
            )
            try:
                execution = self._registry.get(tool_name).execute({})
                observation = {
                    "tool_name": tool_name,
                    "answer": execution.answer,
                    "result": execution.result if isinstance(execution.result, dict) else {},
                    "status": execution.status,
                }
            except Exception as exc:
                observation = {
                    "tool_name": tool_name,
                    "answer": f"Tool '{tool_name}' failed: {exc}",
                    "result": {"error": str(exc)},
                    "status": "failed",
                }
            observations.append(observation)
            self._emit(
                progress_callback,
                {
                    "type": "agent_observation",
                    "observation": {
                        "source": tool_name,
                        "content": observation["answer"],
                        "data": observation["result"],
                    },
                },
            )
            activity.append(
                AdminActivityItem(
                    phase="observation",
                    status="completed" if observation["status"] == "ok" else "failed",
                    title=f"Read {tool_name}",
                    detail=observation["answer"],
                    tool=tool_name,
                    arguments={},
                )
            )

        answer = self._synthesize_answer(context, subject, bundle_id, observations)
        return self._response_factory.build_response(
            status="ok",
            mode="advisory",
            selected_mode=context.selected_mode,
            session_id=context.session_id,
            message=context.message,
            answer=answer,
            intent="fast_read_only_plan",
            tool=None,
            arguments={},
            requires_confirmation=False,
            executed=False,
            pending_action=None,
            citations=[],
            thinking_summary=(
                "I semantically classified this as a read-only admin request and answered it from a fixed tool bundle "
                "instead of using the recursive loop."
            ),
            activity=activity,
            result={
                "route": "fast_read_only",
                "bundle_id": bundle_id,
                "subject": subject,
                "observations": observations,
            },
            agent_run=None,
        )

    def _synthesize_answer(
        self,
        context: AdminRequestContext,
        subject: str,
        bundle_id: str,
        observations: list[dict],
    ) -> str:
        if self._explainer_client is not None:
            try:
                answer = self._explainer_client.complete_text(
                    system_prompt=(
                        "You answer admin configuration questions using grounded read-only tool outputs. "
                        "Always answer in the same language as the user's latest message. "
                        "Explain the current setup, compare meaningful choices if asked, and recommend practical next steps. "
                        "Stay strictly within the subsystem identified by the subject and bundle id. "
                        "Do not introduce unrelated subsystems, unrelated config changes, or execution proposals unless the user explicitly asked for them. "
                        "If the subject is chunking, answer only about chunking. "
                        "If the subject is evaluation/performance, answer only about evaluation metrics and reports. "
                        "Do not ask the user to switch modes."
                    ),
                    user_prompt=(
                        f"User request:\n{context.message.strip()}\n\n"
                        f"Latest user language: {context.latest_user_language}\n"
                        f"Subject: {subject}\n"
                        f"Bundle id: {bundle_id}\n\n"
                        f"Grounded tool observations:\n{json.dumps(observations, ensure_ascii=True, indent=2)}"
                    ),
                )
                if isinstance(answer, str) and answer.strip():
                    return answer
            except Exception:
                pass

        if bundle_id == "chunking_review":
            return self._build_chunking_comparison_answer(context.message, observations)
        if bundle_id == "reranking_review":
            return self._build_reranking_comparison_answer(context.message, observations)

        lines = []
        for item in observations:
            lines.append(f"- {item['tool_name']}: {item['answer']}")
        return "Grounded read-only summary:\n" + "\n".join(lines)

    def _build_chunking_comparison_answer(self, user_message: str, observations: list[dict]) -> str:
        current = self._result_for_tool(observations, "get_chunking_config")
        catalog = self._result_for_tool(observations, "get_chunking_strategy_catalog")
        options = catalog.get("options", []) if isinstance(catalog.get("options"), list) else []
        current_strategy = str(current.get("chunk_strategy", "")) if isinstance(current, dict) else ""
        chunk_size = current.get("chunk_size") if isinstance(current, dict) else None
        chunk_overlap = current.get("chunk_overlap") if isinstance(current, dict) else None

        comparison_lines = []
        for option in options:
            if not isinstance(option, dict):
                continue
            comparison_lines.append(
                f"- {option.get('name')}: quality={option.get('quality')}, latency={option.get('latency')}, "
                f"cost={option.get('cost')}, best_for={', '.join(option.get('best_for', []))}"
            )

        recommendation = (
            "For performance/retrieval quality, the strongest options are usually 'late' and 'semantic'. "
            "'late' is the best default when you have long dense documents and want more context retention. "
            "'semantic' is better when document structure is uneven and preserving meaning across boundaries matters more. "
            "If your priority is lower cost and simplicity, 'overlap' is the lighter option."
        )

        return (
            f"La strategie actuelle est '{current_strategy}'"
            + (f" avec chunk_size={chunk_size}" if chunk_size is not None else "")
            + (f" et chunk_overlap={chunk_overlap}" if chunk_overlap is not None else "")
            + ".\n\n"
            + "Comparaison directe des strategies disponibles :\n"
            + "\n".join(comparison_lines)
            + "\n\n"
            + recommendation
            + (f"\n\nDans l'etat actuel, vous utilisez deja '{current_strategy}', ce qui est coherent si votre objectif est une bonne performance globale." if current_strategy == "late" else "")
        )

    def _build_reranking_comparison_answer(self, user_message: str, observations: list[dict]) -> str:
        current = self._result_for_tool(observations, "get_reranker_config")
        catalog = self._result_for_tool(observations, "get_reranker_strategy_catalog")
        options = catalog.get("options", []) if isinstance(catalog.get("options"), list) else []
        current_ranker = str(current.get("default_ranker", "")) if isinstance(current, dict) else ""
        top_n = current.get("rerank_top_n") if isinstance(current, dict) else None

        comparison_lines = []
        for option in options:
            if not isinstance(option, dict):
                continue
            comparison_lines.append(
                f"- {option.get('name')}: quality={option.get('quality')}, latency={option.get('latency')}, "
                f"cost={option.get('cost')}, best_for={', '.join(option.get('best_for', []))}"
            )

        recommendation = (
            "If your goal is the best ranking quality, 'llm_batch' is the strongest but also the most expensive and slowest. "
            "If you want a better quality/cost balance, 'cross_encoder' is usually the best default recommendation. "
            "If speed and minimal resource usage matter most, keep 'none'."
        )

        return (
            f"The current reranker is '{current_ranker}'"
            + (f" with top_n={top_n}" if top_n is not None else "")
            + ".\n\n"
            + "Direct comparison of the available reranking strategies:\n"
            + "\n".join(comparison_lines)
            + "\n\n"
            + recommendation
        )

    def _result_for_tool(self, observations: list[dict], tool_name: str) -> dict:
        for item in observations:
            if item.get("tool_name") == tool_name and isinstance(item.get("result"), dict):
                return item["result"]
        return {}
