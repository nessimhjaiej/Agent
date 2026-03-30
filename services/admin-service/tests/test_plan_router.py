from pathlib import Path
import sys

SERVICE_ROOT = Path(__file__).resolve().parents[1]
if str(SERVICE_ROOT) not in sys.path:
    sys.path.insert(0, str(SERVICE_ROOT))

from app.models import AdminRequestContext  # noqa: E402
from app.plan_router import SemanticPlanRouter  # noqa: E402


class _FakeRouterClient:
    def __init__(self, payload: str) -> None:
        self._payload = payload

    def complete_json(self, system_prompt: str, user_prompt: str) -> str:
        return self._payload


def test_semantic_plan_router_routes_conceptual_question_to_qa() -> None:
    router = SemanticPlanRouter(
        client=_FakeRouterClient(
            """
            {
              "route": "qa",
              "subject": "reindexation",
              "bundle_id": "",
              "reason": "The user is asking for a conceptual definition, not the current live system state.",
              "request_kind": "conceptual_explanation"
            }
            """
        ),
        bundle_catalog={
            "system_overview": {"description": "overview", "tools": ["get_pipeline_status"]},
        },
    )

    decision = router.route(
        AdminRequestContext(
            message="que veut dire réindexation",
            selected_mode="plan",
            latest_user_language="fr",
        )
    )

    assert decision.route == "qa"
    assert decision.request_kind == "conceptual_explanation"
    assert decision.bundle_id == ""


def test_semantic_plan_router_routes_latency_reduction_goal_to_recursive_agent() -> None:
    router = SemanticPlanRouter(
        client=_FakeRouterClient(
            """
            {
              "route": "recursive_agent",
              "subject": "latency",
              "bundle_id": "",
              "reason": "The user is asking which system changes could reduce response latency, which is an optimization goal.",
              "request_kind": "optimization_goal"
            }
            """
        ),
        bundle_catalog={
            "system_overview": {"description": "overview", "tools": ["get_pipeline_status"]},
            "evaluation_review": {"description": "evaluation", "tools": ["get_evaluation_report"]},
        },
    )

    decision = router.route(
        AdminRequestContext(
            message="quels sont les opérations possibles à faire pour réduire le temps d'attente des réponses ?",
            selected_mode="plan",
            latest_user_language="fr",
        )
    )

    assert decision.route == "recursive_agent"
    assert decision.request_kind == "optimization_goal"
    assert decision.subject == "latency"
