from app.models import PlanStep, PlannedAction
from app.schemas import (
    AdminActivityItem,
    AdminChatResponse,
    AdminPendingAction,
    AdminPlanStep,
)


class AdminResponseFactory:
    def build_response(self, **kwargs) -> AdminChatResponse:
        return AdminChatResponse(**kwargs)

    def build_mode_switch_response(
        self,
        *,
        context,
        response_mode: str,
        answer: str,
        thinking_summary: str,
        activity: list[AdminActivityItem],
        intent: str,
    ) -> AdminChatResponse:
        return self.build_response(
            status="ok",
            mode=response_mode,
            selected_mode=context.selected_mode,
            session_id=context.session_id,
            message=context.message,
            answer=answer,
            intent=intent,
            tool=None,
            arguments={},
            requires_confirmation=False,
            executed=False,
            pending_action=None,
            citations=[],
            thinking_summary=thinking_summary,
            activity=activity,
            result={"suggested_mode": "qa"},
        )

    def build_planning_summary(
        self,
        planned: PlannedAction,
        steps: list[PlanStep],
        requires_confirmation: bool,
    ) -> str:
        step_count = len(steps)
        if planned.mode == "qa":
            return "I handled this as an informational request."
        if requires_confirmation:
            return (
                f"I resolved this request to a {step_count}-step admin plan and paused before execution "
                "because the plan includes high-risk or state-changing actions."
            )
        return f"I resolved this request to a {step_count}-step admin plan and executed it."

    def build_execution_summary(self, planned: PlannedAction, execution_payload: dict) -> str:
        step_count = int(execution_payload.get("step_count", 0) or 0)
        status = str(execution_payload.get("status", "ok"))
        if status == "ok":
            return (
                f"I executed the admin plan successfully across {step_count} step"
                f"{'' if step_count == 1 else 's'}."
            )
        failed_step = next(
            (
                step.get("tool")
                for step in execution_payload.get("steps", [])
                if isinstance(step, dict) and step.get("status") != "ok"
            ),
            planned.tool_name or planned.intent,
        )
        return f"I started the admin plan but it failed while running '{failed_step}'."

    def build_confirmation_activity(self, steps: list[PlanStep]) -> list[AdminActivityItem]:
        activity = [
            AdminActivityItem(
                phase="planning",
                status="completed",
                title="Built admin execution plan",
                detail=f"Prepared {len(steps)} step{'s' if len(steps) != 1 else ''} for this request.",
            )
        ]
        for index, step in enumerate(steps, start=1):
            activity.append(
                AdminActivityItem(
                    phase="confirmation",
                    status="pending",
                    title=f"Awaiting confirmation for step {index}",
                    detail=f"The agent is prepared to call '{step.tool_name}' after you confirm.",
                    tool=step.tool_name,
                    arguments=step.arguments,
                )
            )
        return activity

    def build_execution_activity(
        self,
        planned_steps: list[PlanStep],
        execution_payload: dict,
    ) -> list[AdminActivityItem]:
        activity = [
            AdminActivityItem(
                phase="planning",
                status="completed",
                title="Resolved admin plan",
                detail=f"Prepared {len(planned_steps)} executable step{'s' if len(planned_steps) != 1 else ''}.",
            )
        ]
        executed_steps = execution_payload.get("steps", [])
        if not isinstance(executed_steps, list):
            executed_steps = []
        for index, step in enumerate(executed_steps, start=1):
            if not isinstance(step, dict):
                continue
            step_status = "completed" if step.get("status") == "ok" else "failed"
            activity.append(
                AdminActivityItem(
                    phase="execution",
                    status=step_status,
                    title=f"Executed step {index}: {step.get('tool', 'unknown_tool')}",
                    detail=str(step.get("answer", "")),
                    tool=step.get("tool"),
                    arguments=step.get("arguments", {}) if isinstance(step.get("arguments"), dict) else {},
                )
            )
        executed_tool_names = {
            step.get("tool")
            for step in executed_steps
            if isinstance(step, dict) and isinstance(step.get("tool"), str)
        }
        if execution_payload.get("status") != "ok":
            for step in planned_steps:
                if step.tool_name in executed_tool_names:
                    continue
                activity.append(
                    AdminActivityItem(
                        phase="execution",
                        status="skipped",
                        title=f"Skipped step: {step.tool_name}",
                        detail="This step was not reached because an earlier step failed.",
                        tool=step.tool_name,
                        arguments=step.arguments,
                    )
                )
        return activity

    def build_pending_action(
        self,
        *,
        intent: str,
        tool: str,
        arguments: dict,
        steps: list[PlanStep],
    ) -> AdminPendingAction:
        return AdminPendingAction(
            intent=intent,
            tool=tool,
            arguments=arguments,
            steps=[AdminPlanStep(tool=step.tool_name, arguments=step.arguments) for step in steps],
        )
