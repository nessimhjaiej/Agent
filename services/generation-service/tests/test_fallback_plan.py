from pathlib import Path
import sys

SERVICE_ROOT = Path(__file__).resolve().parents[1]
if str(SERVICE_ROOT) not in sys.path:
    sys.path.insert(0, str(SERVICE_ROOT))

from fallback_model.plan import ModelFallbackPlan  # noqa: E402


def test_plan_returns_primary_and_fallback_when_enabled() -> None:
    plan = ModelFallbackPlan(
        primary_provider="openai",
        primary_model="gpt-4o",
        fallback_enabled=True,
        fallback_provider="ollama",
        fallback_model="gpt-4o-mini",
    )

    assert plan.sequence() == [("openai", "gpt-4o"), ("ollama", "gpt-4o-mini")]


def test_plan_returns_only_primary_when_disabled() -> None:
    plan = ModelFallbackPlan(
        primary_provider="openai",
        primary_model="gpt-4o",
        fallback_enabled=False,
        fallback_provider="ollama",
        fallback_model="gpt-4o-mini",
    )

    assert plan.sequence() == [("openai", "gpt-4o")]
