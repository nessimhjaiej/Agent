import re

from app.models import PlannedAction


class IntentParser:
    """Conservative fallback parser used only when LLM planning is unavailable."""

    def parse(self, message: str) -> PlannedAction:
        lowered = message.strip().lower()

        if any(token in lowered for token in ("revert", "undo", "rollback")):
            return PlannedAction(
                mode="tool_call",
                intent="revert_changes",
                tool_name="revert_changes",
                arguments=self._extract_revert_arguments(lowered),
                answer="",
                requires_confirmation=True,
            )

        if any(token in lowered for token in ("status", "health", "services up", "pipeline status")):
            return PlannedAction(
                mode="tool_call",
                intent="get_pipeline_status",
                tool_name="get_pipeline_status",
                answer="I can check the health of the pipeline services now.",
            )

        if "embedding" in lowered and any(token in lowered for token in ("config", "model", "current")):
            return PlannedAction(
                mode="tool_call",
                intent="get_embedding_config",
                tool_name="get_embedding_config",
                answer="I can show the current embedding configuration.",
            )

        if any(token in lowered for token in ("chunking config", "chunk config", "chunk strategy")) and any(
            token in lowered for token in ("show", "current", "inspect", "what is")
        ):
            return PlannedAction(
                mode="tool_call",
                intent="get_chunking_config",
                tool_name="get_chunking_config",
                answer="I can show the current chunking configuration.",
            )

        if any(token in lowered for token in ("reranker", "rerank config", "ranker config")) and any(
            token in lowered for token in ("show", "current", "inspect", "what is")
        ):
            return PlannedAction(
                mode="tool_call",
                intent="get_reranker_config",
                tool_name="get_reranker_config",
                answer="I can show the current reranker configuration.",
            )

        return PlannedAction(mode="qa", intent="qa", tool_name=None, answer="")

    def _extract_revert_arguments(self, lowered: str) -> dict:
        count = 1
        number_words = {
            "one": 1,
            "two": 2,
            "three": 3,
            "four": 4,
            "five": 5,
        }
        for word, value in number_words.items():
            if f" {word} " in f" {lowered} ":
                count = value
                break
        digits_match = re.search(r"\b(\d+)\b", lowered)
        if digits_match:
            count = max(1, int(digits_match.group(1)))

        tool_names: list[str] = []
        if "rerank" in lowered or "reranker" in lowered or "ranker" in lowered:
            tool_names.append("update_reranker_config")
        if "chunk" in lowered:
            tool_names.append("update_chunking_config")
        if "embedding" in lowered:
            tool_names.append("update_embedding_model")

        return {
            "count": count,
            "tool_names": tool_names,
        }
