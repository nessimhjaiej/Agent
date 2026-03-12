import json
from pathlib import Path
from typing import Protocol

from app.models import AdminRequestContext, PlanStep, PlannedAction
from app.tools.base import ToolMetadata


class PlannerClient(Protocol):
    def complete_json(self, system_prompt: str, user_prompt: str) -> str: ...


class LLMPlanner:
    def __init__(self, client: PlannerClient, tool_catalog: list[ToolMetadata]) -> None:
        self._client = client
        self._tool_catalog = tool_catalog
        prompt_dir = Path(__file__).resolve().parents[2] / "prompt_templates"
        self._system_prompt = (prompt_dir / "system_prompt.txt").read_text(encoding="utf-8").strip()

    def plan(self, context: AdminRequestContext) -> PlannedAction | None:
        history = "\n".join(
            f"- {turn.role}: {turn.content.strip()}" for turn in context.chat_history[-8:] if turn.content.strip()
        )
        tool_catalog = json.dumps(
            [
                {
                    "name": tool.name,
                    "description": tool.description,
                    "arguments_schema": tool.arguments_schema,
                    "output_description": tool.output_description,
                    "requires_confirmation": tool.requires_confirmation,
                }
                for tool in self._tool_catalog
            ],
            ensure_ascii=True,
            indent=2,
        )
        user_prompt = "\n".join(
            [
                "Available admin tools:",
                tool_catalog,
                "",
                "Conversation history:",
                history or "- (none)",
                "",
                "Current admin message:",
                context.message.strip(),
            ]
        )
        raw = self._client.complete_json(self._system_prompt, user_prompt).strip()
        try:
            payload = json.loads(raw)
        except json.JSONDecodeError:
            return None
        if not isinstance(payload, dict):
            return None

        mode = str(payload.get("mode", "qa")).strip().lower()
        if mode not in {"qa", "tool_call"}:
            return None
        intent = str(payload.get("intent", "")).strip() or ("qa" if mode == "qa" else "unsupported_request")
        tool_name_raw = payload.get("tool")
        tool_name = str(tool_name_raw).strip() if isinstance(tool_name_raw, str) and tool_name_raw.strip() else None
        arguments = payload.get("arguments", {})
        if not isinstance(arguments, dict):
            arguments = {}
        steps_payload = payload.get("steps", [])
        steps: list[PlanStep] = []
        if isinstance(steps_payload, list):
            for item in steps_payload:
                if not isinstance(item, dict):
                    continue
                step_tool = item.get("tool")
                step_args = item.get("arguments", {})
                if not isinstance(step_tool, str) or not step_tool.strip():
                    continue
                if not isinstance(step_args, dict):
                    step_args = {}
                steps.append(PlanStep(tool_name=step_tool.strip(), arguments=step_args))
        answer = str(payload.get("answer", "")).strip()
        requires_confirmation = bool(payload.get("requires_confirmation", False))
        return PlannedAction(
            mode=mode,
            intent=intent,
            tool_name=tool_name,
            arguments=arguments,
            answer=answer,
            requires_confirmation=requires_confirmation,
            steps=steps,
        )
