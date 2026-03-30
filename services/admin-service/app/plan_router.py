from __future__ import annotations

import json
from dataclasses import dataclass

from app.models import AdminRequestContext


@dataclass(slots=True)
class PlanRouteDecision:
    route: str
    subject: str = ""
    bundle_id: str = ""
    reason: str = ""
    request_kind: str = ""


class SemanticPlanRouter:
    def __init__(self, client, bundle_catalog: dict[str, dict]) -> None:  # noqa: ANN001
        self._client = client
        self._bundle_catalog = bundle_catalog

    def route(self, context: AdminRequestContext) -> PlanRouteDecision:
        if self._client is None:
            return PlanRouteDecision(route="recursive_agent", reason="planner_unavailable")
        try:
            raw = self._client.complete_json(
                system_prompt=self._build_system_prompt(),
                user_prompt=self._build_user_prompt(context),
            ).strip()
            payload = json.loads(raw)
        except Exception:
            return PlanRouteDecision(route="recursive_agent", reason="router_error")

        route = str(payload.get("route", "")).strip()
        if route not in {"fast_read_only", "recursive_agent", "legacy_planner", "qa"}:
            return PlanRouteDecision(route="recursive_agent", reason="invalid_route")

        bundle_id = str(payload.get("bundle_id", "")).strip()
        if route == "fast_read_only" and bundle_id not in self._bundle_catalog:
            return PlanRouteDecision(route="recursive_agent", reason="invalid_bundle")

        return PlanRouteDecision(
            route=route,
            subject=str(payload.get("subject", "")).strip(),
            bundle_id=bundle_id,
            reason=str(payload.get("reason", "")).strip(),
            request_kind=str(payload.get("request_kind", "")).strip(),
        )

    def _build_system_prompt(self) -> str:
        return (
            "You route plan-mode admin requests semantically. "
            "Respond with valid JSON only. "
            "Supported routes are: fast_read_only, recursive_agent, legacy_planner, qa. "
            "Use fast_read_only only when the user is asking about the current live system state, current configuration, "
            "current metrics, or a narrow comparison that can be answered from one fixed bundle of read-only admin tools. "
            "When the user asks about the current strategy, current configuration, or current metrics of one specific subsystem, "
            "choose the exact subsystem bundle rather than a broader bundle. "
            "Example: a question about chunking, decomposition, or decoupage must route to the chunking read-only bundle, "
            "not to reranking, evaluation, or a broad system-overview bundle. "
            "Example: a question about current performance or metrics should route to the evaluation read-only bundle. "
            "Do not use fast_read_only for conceptual definitions, architecture explanations, terminology questions, "
            "or educational questions such as 'what does reindexation mean', 'how does reranking work', or "
            "'what is chunking'. Those should route to qa unless the user explicitly asks about the current live setup. "
            "Do not use qa for admin optimization goals such as reducing latency, reducing cost, improving quality, "
            "increasing throughput, or choosing what operational changes should be made to reach a system objective. "
            "Those requests should route to recursive_agent because the user is implicitly asking for grounded admin recommendations "
            "and possible parameter changes, even if the message is phrased as a question. "
            "Examples: 'how can I reduce response latency', 'what operations are possible to reduce waiting time', "
            "'how should I lower costs', or 'what should I change to improve retrieval quality' should route to recursive_agent. "
            "Use recursive_agent when the request needs iterative reasoning, planning, follow-up actions, or possible mutation or confirmation. "
            "Use legacy_planner only for unsupported or destructive flows that should stay on the older plan executor path. "
            "Use qa for conceptual explanations, architecture questions, and normal knowledge-base questions that do not require admin tool inspection. "
            "Do not rely on surface keywords; infer meaning across languages. "
            "If the request is narrow and read-only, do not upgrade it into broader optimization planning. "
            "If the user is asking what a concept means, how something works in principle, or the difference between concepts, "
            "prefer qa over fast_read_only."
        )

    def _build_user_prompt(self, context: AdminRequestContext) -> str:
        return json.dumps(
            {
                "message": context.message,
                "latest_user_language": context.latest_user_language,
                "selected_mode": context.selected_mode,
                "recent_chat_history": [
                    {"role": item.role, "content": item.content}
                    for item in context.chat_history[-6:]
                ],
                "available_fast_read_only_bundles": self._bundle_catalog,
                "required_output_schema": {
                    "route": "fast_read_only | recursive_agent | legacy_planner | qa",
                    "subject": "string",
                    "request_kind": "read_only_status | read_only_compare | planning | execution | conceptual_explanation | optimization_goal | knowledge",
                    "bundle_id": "string or empty",
                    "reason": "string",
                },
            },
            ensure_ascii=True,
            indent=2,
        )
