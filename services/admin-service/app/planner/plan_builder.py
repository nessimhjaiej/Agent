from __future__ import annotations

from app.models import PlanStep, PlannedAction


class PlanBuilder:
    def build(self, planned: PlannedAction) -> PlannedAction:
        if planned.mode != "tool_call":
            return planned
        if planned.steps:
            return planned

        tool_name = planned.tool_name
        arguments = dict(planned.arguments)
        if tool_name is None:
            return planned

        if tool_name == "reindex_corpus":
            return PlannedAction(
                mode="tool_call",
                intent="reindex_corpus",
                tool_name="reindex_corpus",
                arguments=arguments,
                answer=planned.answer,
                requires_confirmation=True,
                steps=[
                    PlanStep(tool_name="delete_validated_documents", arguments=arguments),
                    PlanStep(tool_name="embed_validated_documents", arguments=arguments),
                ],
            )

        if tool_name == "update_chunking_config":
            follow_up = {
                "raw_dir": arguments.get("raw_dir", "shared/raw_data/supabase/validated"),
                "local_root": arguments.get("local_root", "shared/raw_data"),
                "source_root_in_preprocessing": arguments.get(
                    "source_root_in_preprocessing",
                    "/shared/raw_data/supabase/validated",
                ),
                "patterns": arguments.get("patterns"),
            }
            restart_services = arguments.get("restart_services")
            steps = [
                PlanStep(tool_name="update_chunking_config", arguments=arguments),
                PlanStep(tool_name="delete_validated_documents", arguments=follow_up),
                PlanStep(tool_name="embed_validated_documents", arguments=follow_up),
            ]
            if isinstance(restart_services, list) and restart_services:
                steps.append(
                    PlanStep(
                        tool_name="restart_services",
                        arguments={"services": restart_services, "delay_seconds": 2},
                    )
                )
            return PlannedAction(
                mode="tool_call",
                intent="apply_chunking_change",
                tool_name="apply_chunking_change",
                arguments=arguments,
                answer=planned.answer,
                requires_confirmation=True,
                steps=steps,
            )

        if tool_name == "update_embedding_model":
            follow_up = {
                "raw_dir": arguments.get("raw_dir", "shared/raw_data/supabase/validated"),
                "local_root": arguments.get("local_root", "shared/raw_data"),
                "source_root_in_preprocessing": arguments.get(
                    "source_root_in_preprocessing",
                    "/shared/raw_data/supabase/validated",
                ),
                "patterns": arguments.get("patterns"),
            }
            restart_services = arguments.get("restart_services")
            steps = [
                PlanStep(tool_name="update_embedding_model", arguments=arguments),
                PlanStep(tool_name="delete_validated_documents", arguments=follow_up),
                PlanStep(tool_name="embed_validated_documents", arguments=follow_up),
            ]
            if isinstance(restart_services, list) and restart_services:
                steps.append(
                    PlanStep(
                        tool_name="restart_services",
                        arguments={"services": restart_services, "delay_seconds": 2},
                    )
                )
            return PlannedAction(
                mode="tool_call",
                intent="apply_embedding_model_change",
                tool_name="apply_embedding_model_change",
                arguments=arguments,
                answer=planned.answer,
                requires_confirmation=True,
                steps=steps,
            )

        if tool_name == "embed_document":
            target_relative_path = arguments.get("target_relative_path")
            if target_relative_path:
                return PlannedAction(
                    mode="tool_call",
                    intent="embed_document",
                    tool_name="embed_document",
                    arguments=arguments,
                    answer=planned.answer,
                    requires_confirmation=True,
                    steps=[
                        PlanStep(
                            tool_name="delete_document",
                            arguments={"target_relative_path": target_relative_path},
                        ),
                        PlanStep(
                            tool_name="embed_document",
                            arguments={**arguments, "skip_if_exists": False},
                        ),
                    ],
                )

        if tool_name == "restart_services":
            return PlannedAction(
                mode="tool_call",
                intent="restart_services",
                tool_name="restart_services",
                arguments=arguments,
                answer=planned.answer,
                requires_confirmation=True,
                steps=[PlanStep(tool_name="restart_services", arguments=arguments)],
            )

        return PlannedAction(
            mode="tool_call",
            intent=planned.intent,
            tool_name=tool_name,
            arguments=arguments,
            answer=planned.answer,
            requires_confirmation=planned.requires_confirmation,
            steps=[PlanStep(tool_name=tool_name, arguments=arguments)],
        )
