from app.clients.openai_planner_client import OpenAIPlannerClient
from app.config import Settings
from app.models import AdminRequestContext, PlanStep, PlannedAction
from app.planner.intent_parser import IntentParser
from app.planner.llm_planner import LLMPlanner
from app.planner.plan_builder import PlanBuilder
from app.tools.registry import ToolRegistry


class ToolSelector:
    def __init__(
        self,
        settings: Settings,
        registry: ToolRegistry,
        parser: IntentParser | None = None,
        llm_planner: LLMPlanner | None = None,
        plan_builder: PlanBuilder | None = None,
    ) -> None:
        self._settings = settings
        self._registry = registry
        self._parser = parser or IntentParser()
        self._llm_planner = llm_planner
        self._plan_builder = plan_builder or PlanBuilder()
        if self._llm_planner is None and settings.planner_enabled:
            self._llm_planner = LLMPlanner(
                client=OpenAIPlannerClient(
                    api_key=settings.openai_key,
                    model=settings.planner_model,
                    temperature=settings.planner_temperature,
                    timeout_seconds=settings.http_timeout_seconds,
                    max_retries=settings.planner_http_max_retries,
                    retry_base_seconds=settings.planner_retry_base_seconds,
                ),
                tool_catalog=registry.planning_tools(),
            )

    def select(self, context: AdminRequestContext) -> PlannedAction:
        follow_up = self._maybe_build_follow_up_explanation(context)
        if follow_up is not None:
            return follow_up
        if self._llm_planner is not None:
            try:
                planned = self._sanitize(self._llm_planner.plan(context))
            except Exception:
                planned = None
            if planned is not None:
                return self._plan_builder.build(planned) if planned.mode != "qa" else planned
        parsed = self._sanitize(self._parser.parse(context.message))
        if parsed is not None and parsed.mode != "qa":
            return self._plan_builder.build(parsed)
        return parsed or PlannedAction(mode="qa", intent="qa", tool_name=None, answer="")

    def _maybe_build_follow_up_explanation(
        self,
        context: AdminRequestContext,
    ) -> PlannedAction | None:
        lowered = context.message.strip().lower()
        if lowered not in {
            "what does this mean",
            "what does that mean",
            "explain this",
            "explain that",
            "clarify this",
            "clarify that",
        }:
            return None

        last_assistant_message = next(
            (
                turn.content.strip()
                for turn in reversed(context.chat_history)
                if turn.role == "assistant" and turn.content.strip()
            ),
            "",
        )
        if not last_assistant_message:
            return None

        return PlannedAction(
            mode="qa",
            intent="explain_last_agent_response",
            tool_name=None,
            arguments={"assistant_message": last_assistant_message},
            answer="",
        )

    def _sanitize(self, planned: PlannedAction | None) -> PlannedAction | None:
        if planned is None:
            return None
        if planned.mode == "qa":
            return PlannedAction(mode="qa", intent=planned.intent or "qa", tool_name=None, answer=planned.answer)
        if planned.intent == "revert_changes":
            return PlannedAction(
                mode="tool_call",
                intent="revert_changes",
                tool_name="revert_changes",
                arguments=planned.arguments if isinstance(planned.arguments, dict) else {},
                answer=planned.answer,
                requires_confirmation=planned.requires_confirmation,
                steps=planned.steps,
            )

        valid_steps: list[PlanStep] = [
            PlanStep(tool_name=step.tool_name, arguments=step.arguments)
            for step in planned.steps
            if self._registry.has(step.tool_name)
        ]

        tool_name = planned.tool_name
        if tool_name is not None and not self._registry.has(tool_name):
            if not valid_steps:
                return None

        if tool_name is None and valid_steps:
            tool_name = valid_steps[0].tool_name

        if tool_name is None:
            return None

        return PlannedAction(
            mode="tool_call",
            intent=planned.intent or tool_name,
            tool_name=tool_name,
            arguments=planned.arguments if isinstance(planned.arguments, dict) else {},
            answer=planned.answer,
            requires_confirmation=planned.requires_confirmation,
            steps=valid_steps,
        )
