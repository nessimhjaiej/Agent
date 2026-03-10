import re

from app.models import PlannedAction


class IntentParser:
    def parse(self, message: str) -> PlannedAction:
        text = message.strip()
        lowered = text.lower()

        if (
            " or " in lowered
            and any(token in lowered for token in ("should we", "should i", "explain", "risk", "risks"))
        ):
            return PlannedAction(mode="qa", intent="qa", tool_name=None, answer="")

        if any(token in lowered for token in ("status", "health", "services up", "pipeline status")):
            return PlannedAction(
                mode="tool_call",
                intent="get_pipeline_status",
                tool_name="get_pipeline_status",
                answer="I can check the health of the pipeline services now.",
            )

        if any(token in lowered for token in ("restart service", "restart services", "bounce service")):
            services = self._extract_services(lowered)
            return PlannedAction(
                mode="tool_call",
                intent="restart_services",
                tool_name="restart_services",
                arguments={"services": services, "delay_seconds": 2},
                answer=f"Restarting services {', '.join(services)} will disrupt in-flight work. Confirm to proceed.",
                requires_confirmation=True,
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

        if any(token in lowered for token in ("update embedding model", "set embedding model", "change embedding model")):
            embedding_model = self._extract_assignment(text)
            arguments = {"embedding_model": embedding_model}
            if "restart" in lowered:
                arguments["restart_services"] = ["embedding-service", "retrieval-service", "generation-service"]
            return PlannedAction(
                mode="tool_call",
                intent="update_embedding_model",
                tool_name="update_embedding_model",
                arguments=arguments,
                answer=(
                    f"Changing the embedding model to '{embedding_model}' will trigger a clean corpus rebuild"
                    " so the index stays consistent. Confirm to proceed."
                ),
                requires_confirmation=True,
            )

        if any(token in lowered for token in ("update chunk", "set chunk", "change chunk")):
            arguments = self._extract_chunking_arguments(text)
            if "restart" in lowered:
                arguments["restart_services"] = ["preprocessing-service", "ingestion-service"]
            return PlannedAction(
                mode="tool_call",
                intent="update_chunking_config",
                tool_name="update_chunking_config",
                arguments=arguments,
                answer="Updating chunking settings will trigger a clean corpus rebuild. Confirm to proceed.",
                requires_confirmation=True,
            )

        if any(token in lowered for token in ("update reranker", "set reranker", "change reranker", "change ranker")):
            arguments = self._extract_reranker_arguments(text)
            if "restart" in lowered:
                arguments["restart_services"] = ["retrieval-service", "generation-service"]
            return PlannedAction(
                mode="tool_call",
                intent="update_reranker_config",
                tool_name="update_reranker_config",
                arguments=arguments,
                answer="Updating reranker settings changes future retrieval behavior. Confirm to proceed.",
                requires_confirmation=True,
            )

        if any(token in lowered for token in ("embed document", "index document")):
            target_relative_path = self._extract_document_reference(text)
            return PlannedAction(
                mode="tool_call",
                intent="embed_document",
                tool_name="embed_document",
                arguments={"target_relative_path": target_relative_path},
                answer=(
                    f"Embedding document '{target_relative_path}' will clean any existing indexed copy"
                    " and then re-index it. Confirm to proceed."
                ),
                requires_confirmation=True,
            )

        if any(token in lowered for token in ("embed all validated", "index all validated", "embed validated documents")):
            return PlannedAction(
                mode="tool_call",
                intent="embed_validated_documents",
                tool_name="embed_validated_documents",
                arguments={},
                answer="Embedding all validated documents may take time and will update the index. Confirm to proceed.",
                requires_confirmation=True,
            )

        if "reindex" in lowered and any(token in lowered for token in ("corpus", "knowledge base", "validated")):
            return PlannedAction(
                mode="tool_call",
                intent="reindex_corpus",
                tool_name="reindex_corpus",
                arguments={},
                answer="A clean corpus rebuild will delete indexed validated chunks and then re-index them. Confirm to proceed.",
                requires_confirmation=True,
            )

        if any(token in lowered for token in ("delete", "remove")) and "document" in lowered:
            target_relative_path = self._extract_document_reference(text)
            return PlannedAction(
                mode="tool_call",
                intent="delete_document",
                tool_name="delete_document",
                arguments={"target_relative_path": target_relative_path},
                answer=(
                    f"Deleting document '{target_relative_path}' will remove its indexed chunks. "
                    "Confirm to proceed."
                ),
                requires_confirmation=True,
            )

        if any(token in lowered for token in ("run evaluation", "run ragas", "evaluate rag", "evaluate retrieval")):
            dataset_path = self._extract_dataset_path(text)
            return PlannedAction(
                mode="tool_call",
                intent="run_rag_evaluation",
                tool_name="run_rag_evaluation",
                arguments={"dataset_path": dataset_path},
                answer=f"Running RAG evaluation with dataset '{dataset_path}' may take a while and incur model cost. Confirm to proceed.",
                requires_confirmation=True,
            )

        if any(token in lowered for token in ("evaluation report", "ragas report")) and any(
            token in lowered for token in ("show", "get", "latest", "fetch")
        ):
            report_path = self._extract_report_path(text)
            return PlannedAction(
                mode="tool_call",
                intent="get_evaluation_report",
                tool_name="get_evaluation_report",
                arguments={"report_path": report_path} if report_path else {},
                answer="I can load the requested evaluation report.",
            )

        return PlannedAction(mode="qa", intent="qa", tool_name=None, answer="")

    def _extract_document_reference(self, text: str) -> str:
        quoted = re.findall(r"['\"]([^'\"]+)['\"]", text)
        if quoted:
            return quoted[0].strip()

        match = re.search(r"document\s+([^\s]+)", text, flags=re.IGNORECASE)
        if match:
            return match.group(1).strip().rstrip("?.!,")

        return "UNKNOWN_DOCUMENT"

    def _extract_assignment(self, text: str) -> str:
        quoted = re.findall(r"['\"]([^'\"]+)['\"]", text)
        if quoted:
            return quoted[0].strip()

        match = re.search(r"(?:to|as)\s+([A-Za-z0-9._:/-]+)", text, flags=re.IGNORECASE)
        if match:
            return match.group(1).strip().rstrip("?.!,")
        return "UNKNOWN_VALUE"

    def _extract_chunking_arguments(self, text: str) -> dict:
        arguments: dict[str, object] = {}
        strategy_match = re.search(
            r"(?:strategy|chunking)\s+(?:to\s+)?(overlap|semantic|late|sentence)",
            text,
            flags=re.IGNORECASE,
        )
        size_match = re.search(r"chunk(?:_|\s)?size\s+(?:to\s+)?(\d+)", text, flags=re.IGNORECASE)
        overlap_match = re.search(
            r"chunk(?:_|\s)?overlap\s+(?:to\s+)?(\d+)",
            text,
            flags=re.IGNORECASE,
        )
        if strategy_match:
            arguments["chunk_strategy"] = strategy_match.group(1).lower()
        if size_match:
            arguments["chunk_size"] = int(size_match.group(1))
        if overlap_match:
            arguments["chunk_overlap"] = int(overlap_match.group(1))
        return arguments

    def _extract_reranker_arguments(self, text: str) -> dict:
        arguments: dict[str, object] = {}
        ranker_match = re.search(
            r"(?:reranker|ranker)\s+(?:to\s+)?(none|cross_encoder|llm_batch)",
            text,
            flags=re.IGNORECASE,
        )
        top_n_match = re.search(r"top(?:_|\s)?n\s+(?:to\s+)?(\d+)", text, flags=re.IGNORECASE)
        if ranker_match:
            arguments["default_ranker"] = ranker_match.group(1).lower()
        if top_n_match:
            arguments["rerank_top_n"] = int(top_n_match.group(1))
        return arguments

    def _extract_dataset_path(self, text: str) -> str:
        quoted = re.findall(r"['\"]([^'\"]+)['\"]", text)
        for value in quoted:
            if value.endswith(".json"):
                return value.strip()
        return "evals/sample_eval_dataset.json"

    def _extract_report_path(self, text: str) -> str | None:
        quoted = re.findall(r"['\"]([^'\"]+)['\"]", text)
        for value in quoted:
            if value.endswith(".json"):
                return value.strip()
        return None

    def _extract_services(self, lowered: str) -> list[str]:
        mapping = {
            "auth": "auth-service",
            "preprocessing": "preprocessing-service",
            "embedding": "embedding-service",
            "retrieval": "retrieval-service",
            "generation": "generation-service",
            "admin": "admin-service",
        }
        services = [service_name for token, service_name in mapping.items() if token in lowered]
        return services or ["admin-service"]
