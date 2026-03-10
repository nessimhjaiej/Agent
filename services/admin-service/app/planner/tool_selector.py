from app.clients.openai_planner_client import OpenAIPlannerClient
from app.config import Settings
from app.models import AdminRequestContext, PlannedAction
from app.planner.intent_parser import IntentParser
from app.planner.llm_planner import LLMPlanner
from app.planner.plan_builder import PlanBuilder


class ToolSelector:
    def __init__(
        self,
        settings: Settings,
        parser: IntentParser | None = None,
        llm_planner: LLMPlanner | None = None,
        plan_builder: PlanBuilder | None = None,
    ) -> None:
        self._settings = settings
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
                )
            )

    def select(self, context: AdminRequestContext) -> PlannedAction:
        parsed = self._parser.parse(context.message)
        if parsed.mode != "qa":
            return self._plan_builder.build(parsed)
        if self._llm_planner is not None:
            try:
                planned = self._llm_planner.plan(context)
            except Exception:
                planned = None
            if planned is not None:
                return self._plan_builder.build(planned)
        return parsed
