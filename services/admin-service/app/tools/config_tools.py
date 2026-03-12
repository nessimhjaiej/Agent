from __future__ import annotations

from app.clients.auth_client import AuthClient
from app.clients.embedding_client import EmbeddingClient
from app.clients.generation_client import GenerationClient
from app.clients.ingestion_client import IngestionClient
from app.clients.retrieval_client import RetrievalClient
from app.config import Settings
from app.models import ToolExecutionResult
from app.tools.base import ToolMetadata
from app.tools.env_store import EnvConfigStore


def _parse_positive_int(raw: object, field_name: str) -> int:
    try:
        value = int(str(raw).strip())
    except ValueError as exc:
        raise ValueError(f"{field_name} must be an integer") from exc
    if value <= 0:
        raise ValueError(f"{field_name} must be greater than 0")
    return value


def _normalize_text(raw: object, field_name: str) -> str:
    value = str(raw).strip()
    if not value:
        raise ValueError(f"{field_name} is required")
    return value


class GetPipelineStatusTool:
    name = "get_pipeline_status"
    metadata = ToolMetadata(
        name=name,
        description="Check the health and availability of the backend pipeline services.",
        arguments_schema={},
        output_description="Returns per-service health details keyed by service name.",
        requires_confirmation=False,
    )

    def __init__(
        self,
        auth_client: AuthClient,
        embedding_client: EmbeddingClient,
        retrieval_client: RetrievalClient,
        generation_client: GenerationClient,
        ingestion_client: IngestionClient,
    ) -> None:
        self._auth_client = auth_client
        self._embedding_client = embedding_client
        self._retrieval_client = retrieval_client
        self._generation_client = generation_client
        self._ingestion_client = ingestion_client

    def execute(self, arguments: dict) -> ToolExecutionResult:
        services = {
            "auth": self._auth_client.health(),
            "embedding": self._embedding_client.health(),
            "retrieval": self._retrieval_client.health(),
            "generation": self._generation_client.health(),
            "ingestion": self._ingestion_client.health(),
        }
        answer = ", ".join(
            f"{service}={details.get('status', 'unknown')}" for service, details in services.items()
        )
        return ToolExecutionResult(
            status="ok",
            answer=f"Pipeline status: {answer}.",
            result={"services": services},
        )


class GetEmbeddingConfigTool:
    name = "get_embedding_config"
    metadata = ToolMetadata(
        name=name,
        description="Read the current embedding configuration and active embedding service endpoint.",
        arguments_schema={},
        output_description="Returns embedding model, optional dimensions, batch size, and service base URL.",
        requires_confirmation=False,
    )

    def __init__(self, settings: Settings, store: EnvConfigStore | None = None) -> None:
        self._settings = settings
        self._store = store or EnvConfigStore()

    def execute(self, arguments: dict) -> ToolExecutionResult:
        result = {
            "embedding_model": self._store.get("EMBEDDING_MODEL", self._settings.embedding_model),
            "embedding_dimensions": self._store.get("EMBEDDING_DIMENSIONS", "") or None,
            "embedding_batch_size": self._store.get("EMBEDDING_BATCH_SIZE", "64"),
            "embedding_service_base_url": self._settings.embedding_base_url,
        }
        return ToolExecutionResult(
            status="ok",
            answer=(
                f"The current embedding model is '{result['embedding_model']}' "
                f"and the embedding service is '{self._settings.embedding_base_url}'."
            ),
            result=result,
        )


class UpdateEmbeddingModelTool:
    name = "update_embedding_model"
    metadata = ToolMetadata(
        name=name,
        description="Change the configured embedding model used across the stack.",
        arguments_schema={
            "embedding_model": {
                "type": "string",
                "required": True,
                "description": "The embedding model identifier to persist in environment config.",
            },
            "restart_services": {
                "type": "array",
                "required": False,
                "items": {"type": "string"},
                "description": "Optional services that should be restarted after the config change.",
            },
        },
        output_description="Returns the updated embedding model, previous model, config file path, and rollback payload.",
        requires_confirmation=True,
    )

    def __init__(self, store: EnvConfigStore | None = None) -> None:
        self._store = store or EnvConfigStore()

    def execute(self, arguments: dict) -> ToolExecutionResult:
        embedding_model = _normalize_text(arguments.get("embedding_model", ""), "embedding_model")
        previous_embedding_model = self._store.get("EMBEDDING_MODEL", "")
        path = self._store.set_many({"EMBEDDING_MODEL": embedding_model})
        return ToolExecutionResult(
            status="ok",
            answer=(
                f"Updated the embedding model to '{embedding_model}' in '{path.name}'. "
                "The new value will be picked up by services that reload settings on each request."
            ),
            result={
                "embedding_model": embedding_model,
                "previous_embedding_model": previous_embedding_model,
                "config_path": str(path),
                "rollback": {
                    "tool": "update_embedding_model",
                    "arguments": {"embedding_model": previous_embedding_model},
                },
            },
        )


class GetChunkingConfigTool:
    name = "get_chunking_config"
    metadata = ToolMetadata(
        name=name,
        description="Read the current preprocessing chunking strategy and chunk size settings.",
        arguments_schema={},
        output_description="Returns chunk strategy, chunk size, and chunk overlap.",
        requires_confirmation=False,
    )

    def __init__(self, store: EnvConfigStore | None = None) -> None:
        self._store = store or EnvConfigStore()

    def execute(self, arguments: dict) -> ToolExecutionResult:
        result = {
            "chunk_strategy": self._store.get("PREPROCESSING_CHUNK_STRATEGY", "late"),
            "chunk_size": _parse_positive_int(
                self._store.get("PREPROCESSING_CHUNK_SIZE", "800"),
                "PREPROCESSING_CHUNK_SIZE",
            ),
            "chunk_overlap": int(self._store.get("PREPROCESSING_CHUNK_OVERLAP", "120") or "120"),
        }
        return ToolExecutionResult(
            status="ok",
            answer=(
                f"Chunking is configured as strategy='{result['chunk_strategy']}', "
                f"size={result['chunk_size']}, overlap={result['chunk_overlap']}."
            ),
            result=result,
        )


class UpdateChunkingConfigTool:
    name = "update_chunking_config"
    metadata = ToolMetadata(
        name=name,
        description="Update preprocessing chunking settings used during ingestion.",
        arguments_schema={
            "chunk_strategy": {
                "type": "string",
                "required": False,
                "enum": ["overlap", "semantic", "late", "sentence"],
                "description": "Chunking strategy to use during preprocessing.",
            },
            "chunk_size": {
                "type": "integer",
                "required": False,
                "description": "Maximum chunk size in tokens or characters depending on the strategy.",
            },
            "chunk_overlap": {
                "type": "integer",
                "required": False,
                "description": "Overlap size between adjacent chunks.",
            },
            "restart_services": {
                "type": "array",
                "required": False,
                "items": {"type": "string"},
                "description": "Optional services that should be restarted after the change.",
            },
        },
        output_description="Returns the new chunking config, previous values, config file path, and rollback payload.",
        requires_confirmation=True,
    )

    def __init__(self, store: EnvConfigStore | None = None) -> None:
        self._store = store or EnvConfigStore()

    def execute(self, arguments: dict) -> ToolExecutionResult:
        current_size = _parse_positive_int(
            self._store.get("PREPROCESSING_CHUNK_SIZE", "800"),
            "PREPROCESSING_CHUNK_SIZE",
        )
        updates: dict[str, str] = {}
        result = {
            "chunk_strategy": self._store.get("PREPROCESSING_CHUNK_STRATEGY", "late"),
            "chunk_size": current_size,
            "chunk_overlap": int(self._store.get("PREPROCESSING_CHUNK_OVERLAP", "120") or "120"),
        }
        previous_result = dict(result)

        if "chunk_strategy" in arguments:
            strategy = _normalize_text(arguments["chunk_strategy"], "chunk_strategy").lower()
            if strategy not in {"overlap", "semantic", "late", "sentence"}:
                raise ValueError("chunk_strategy must be one of: overlap, semantic, late, sentence")
            updates["PREPROCESSING_CHUNK_STRATEGY"] = strategy
            result["chunk_strategy"] = strategy

        if "chunk_size" in arguments:
            chunk_size = _parse_positive_int(arguments["chunk_size"], "chunk_size")
            updates["PREPROCESSING_CHUNK_SIZE"] = str(chunk_size)
            result["chunk_size"] = chunk_size

        if "chunk_overlap" in arguments:
            chunk_overlap = int(str(arguments["chunk_overlap"]).strip())
            if chunk_overlap < 0:
                raise ValueError("chunk_overlap must be 0 or greater")
            result["chunk_overlap"] = chunk_overlap
            updates["PREPROCESSING_CHUNK_OVERLAP"] = str(chunk_overlap)

        if result["chunk_overlap"] >= result["chunk_size"]:
            raise ValueError("chunk_overlap must be smaller than chunk_size")
        path = self._store.set_many(updates)
        return ToolExecutionResult(
            status="ok",
            answer=(
                "Updated chunking configuration in "
                f"'{path.name}'. The new value will be picked up on the next preprocessing request."
            ),
            result={
                **result,
                "previous": previous_result,
                "config_path": str(path),
                "rollback": {
                    "tool": "update_chunking_config",
                    "arguments": previous_result,
                },
            },
        )


class GetRerankerConfigTool:
    name = "get_reranker_config"
    metadata = ToolMetadata(
        name=name,
        description="Read the current retrieval reranker configuration.",
        arguments_schema={},
        output_description="Returns default reranker, rerank top N, and configured reranker model names.",
        requires_confirmation=False,
    )

    def __init__(self, store: EnvConfigStore | None = None) -> None:
        self._store = store or EnvConfigStore()

    def execute(self, arguments: dict) -> ToolExecutionResult:
        result = {
            "default_ranker": self._store.get("RETRIEVAL_DEFAULT_RANKER", "none"),
            "rerank_top_n": _parse_positive_int(
                self._store.get("RETRIEVAL_DEFAULT_RERANK_TOP_N", "20"),
                "RETRIEVAL_DEFAULT_RERANK_TOP_N",
            ),
            "cross_encoder_model": self._store.get(
                "RETRIEVAL_CROSS_ENCODER_MODEL",
                "cross-encoder/ms-marco-MiniLM-L-6-v2",
            ),
            "llm_rerank_model": self._store.get("RETRIEVAL_LLM_RERANK_MODEL", "gpt-4.1-mini"),
        }
        return ToolExecutionResult(
            status="ok",
            answer=(
                f"The default reranker is '{result['default_ranker']}' with top_n={result['rerank_top_n']}."
            ),
            result=result,
        )


class UpdateRerankerConfigTool:
    name = "update_reranker_config"
    metadata = ToolMetadata(
        name=name,
        description="Update the default reranker configuration used by retrieval and generation.",
        arguments_schema={
            "default_ranker": {
                "type": "string",
                "required": False,
                "enum": ["none", "cross_encoder", "llm_batch"],
                "description": "Default reranker strategy.",
            },
            "rerank_top_n": {
                "type": "integer",
                "required": False,
                "description": "How many retrieved items to rerank.",
            },
            "cross_encoder_model": {
                "type": "string",
                "required": False,
                "description": "Cross-encoder model name when cross-encoder reranking is used.",
            },
            "llm_rerank_model": {
                "type": "string",
                "required": False,
                "description": "LLM model name when LLM batch reranking is used.",
            },
            "restart_services": {
                "type": "array",
                "required": False,
                "items": {"type": "string"},
                "description": "Optional services that should be restarted after the change.",
            },
        },
        output_description="Returns the updated reranker config, previous values, config file path, and rollback payload.",
        requires_confirmation=True,
    )

    def __init__(self, store: EnvConfigStore | None = None) -> None:
        self._store = store or EnvConfigStore()

    def execute(self, arguments: dict) -> ToolExecutionResult:
        result = {
            "default_ranker": self._store.get("RETRIEVAL_DEFAULT_RANKER", "none"),
            "rerank_top_n": _parse_positive_int(
                self._store.get("RETRIEVAL_DEFAULT_RERANK_TOP_N", "20"),
                "RETRIEVAL_DEFAULT_RERANK_TOP_N",
            ),
            "cross_encoder_model": self._store.get(
                "RETRIEVAL_CROSS_ENCODER_MODEL",
                "cross-encoder/ms-marco-MiniLM-L-6-v2",
            ),
            "llm_rerank_model": self._store.get("RETRIEVAL_LLM_RERANK_MODEL", "gpt-4.1-mini"),
        }
        previous_result = dict(result)
        updates: dict[str, str] = {}

        if "default_ranker" in arguments:
            default_ranker = _normalize_text(arguments["default_ranker"], "default_ranker").lower()
            if default_ranker not in {"none", "cross_encoder", "llm_batch"}:
                raise ValueError("default_ranker must be one of: none, cross_encoder, llm_batch")
            result["default_ranker"] = default_ranker
            updates["RETRIEVAL_DEFAULT_RANKER"] = default_ranker

        if "rerank_top_n" in arguments:
            rerank_top_n = _parse_positive_int(arguments["rerank_top_n"], "rerank_top_n")
            result["rerank_top_n"] = rerank_top_n
            updates["RETRIEVAL_DEFAULT_RERANK_TOP_N"] = str(rerank_top_n)

        if "cross_encoder_model" in arguments:
            cross_encoder_model = _normalize_text(arguments["cross_encoder_model"], "cross_encoder_model")
            result["cross_encoder_model"] = cross_encoder_model
            updates["RETRIEVAL_CROSS_ENCODER_MODEL"] = cross_encoder_model

        if "llm_rerank_model" in arguments:
            llm_rerank_model = _normalize_text(arguments["llm_rerank_model"], "llm_rerank_model")
            result["llm_rerank_model"] = llm_rerank_model
            updates["RETRIEVAL_LLM_RERANK_MODEL"] = llm_rerank_model

        path = self._store.set_many(updates)
        return ToolExecutionResult(
            status="ok",
            answer=(
                f"Updated reranker configuration in '{path.name}'. "
                "The new value will be picked up on the next retrieval or generation request."
            ),
            result={
                **result,
                "previous": previous_result,
                "config_path": str(path),
                "rollback": {
                    "tool": "update_reranker_config",
                    "arguments": previous_result,
                },
            },
        )
