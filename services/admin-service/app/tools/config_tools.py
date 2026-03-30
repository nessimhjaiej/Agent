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


class GetRerankerStrategyCatalogTool:
    name = "get_reranker_strategy_catalog"
    metadata = ToolMetadata(
        name=name,
        description="Describe the supported retrieval reranker strategies, tradeoffs, and current active reranker settings.",
        arguments_schema={},
        output_description="Returns the current reranker configuration and a grounded catalog of supported reranker options.",
        requires_confirmation=False,
        goal_tags=["cost", "latency", "quality", "ranking"],
        affects=["retrieval", "generation"],
        impact_summary="Helps the admin compare reranker choices by quality, latency, and cost before making a retrieval change.",
        expected_tradeoffs=[
            "Higher-quality rerankers usually add latency and runtime cost.",
            "The current default reranker can materially change answer relevance and generation quality.",
        ],
        best_for=["reranker comparison", "quality vs cost decisions", "read-only diagnostics"],
        risk_level="low",
        typical_followups=["update_reranker_config", "run_rag_evaluation"],
    )

    def __init__(self, store: EnvConfigStore | None = None) -> None:
        self._store = store or EnvConfigStore()

    def execute(self, arguments: dict) -> ToolExecutionResult:
        current_config = {
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
        options = [
            {
                "name": "none",
                "label": "No reranking",
                "description": "Keep the fused retrieval order without an extra reranking pass.",
                "quality": "baseline",
                "latency": "low",
                "cost": "low",
                "best_for": ["maximum speed", "minimal resource usage"],
                "tunable_fields": [],
            },
            {
                "name": "cross_encoder",
                "label": "Cross-encoder reranking",
                "description": "Score each query-chunk pair with a dedicated cross-encoder model for strong relevance ordering.",
                "quality": "high",
                "latency": "medium",
                "cost": "medium",
                "best_for": ["balanced quality and efficiency", "resource-sensitive quality improvements"],
                "tunable_fields": ["rerank_top_n", "cross_encoder_model"],
            },
            {
                "name": "llm_batch",
                "label": "LLM batch reranking",
                "description": "Use an LLM to evaluate candidate chunks in batches for more nuanced ranking decisions.",
                "quality": "high",
                "latency": "high",
                "cost": "high",
                "best_for": ["quality-first ranking", "complex relevance judgments"],
                "tunable_fields": ["rerank_top_n", "llm_rerank_model"],
            },
        ]
        return ToolExecutionResult(
            status="ok",
            answer=(
                f"Supported reranker strategies: none, cross_encoder, llm_batch. "
                f"The current default is '{current_config['default_ranker']}' with top_n={current_config['rerank_top_n']}."
            ),
            result={
                "subject": "reranker",
                "current_config": current_config,
                "options": options,
            },
        )


class GetChunkingStrategyCatalogTool:
    name = "get_chunking_strategy_catalog"
    metadata = ToolMetadata(
        name=name,
        description="Describe the supported preprocessing chunking strategies, tradeoffs, and current active chunking settings.",
        arguments_schema={},
        output_description="Returns the current chunking configuration and a grounded catalog of supported chunking options.",
        requires_confirmation=False,
        goal_tags=["cost", "latency", "quality", "chunking", "ingestion"],
        affects=["preprocessing", "retrieval", "citation_quality"],
        impact_summary="Helps the admin compare chunking strategies by indexing cost, retrieval quality, and chunk volume.",
        expected_tradeoffs=[
            "Smaller or more granular chunks can improve precision but increase chunk count and indexing cost.",
            "More context-preserving strategies can improve retrieval quality but may increase preprocessing complexity.",
        ],
        best_for=["chunking comparison", "cost reduction planning", "retrieval tuning"],
        risk_level="low",
        typical_followups=["update_chunking_config", "reindex_corpus", "run_rag_evaluation"],
    )

    def __init__(self, store: EnvConfigStore | None = None) -> None:
        self._store = store or EnvConfigStore()

    def execute(self, arguments: dict) -> ToolExecutionResult:
        current_config = {
            "chunk_strategy": self._store.get("PREPROCESSING_CHUNK_STRATEGY", "late"),
            "chunk_size": _parse_positive_int(
                self._store.get("PREPROCESSING_CHUNK_SIZE", "800"),
                "PREPROCESSING_CHUNK_SIZE",
            ),
            "chunk_overlap": int(self._store.get("PREPROCESSING_CHUNK_OVERLAP", "120") or "120"),
        }
        options = [
            {
                "name": "overlap",
                "label": "Sliding overlap chunks",
                "description": "Create fixed-size overlapping chunks for predictable coverage and simple tuning.",
                "quality": "stable",
                "latency": "low",
                "cost": "low",
                "best_for": ["simple ingestion pipelines", "predictable chunk counts"],
                "tunable_fields": ["chunk_size", "chunk_overlap"],
            },
            {
                "name": "semantic",
                "label": "Semantic chunks",
                "description": "Split content around semantic boundaries to preserve meaning across chunk edges.",
                "quality": "high",
                "latency": "medium",
                "cost": "medium",
                "best_for": ["meaning-preserving retrieval", "documents with uneven structure"],
                "tunable_fields": ["chunk_size", "chunk_overlap"],
            },
            {
                "name": "late",
                "label": "Late chunking",
                "description": "Use a larger first pass and derive retrieval-sized chunks later for better context retention.",
                "quality": "high",
                "latency": "medium",
                "cost": "medium",
                "best_for": ["long dense documents", "richer retrieval context"],
                "tunable_fields": ["chunk_size", "chunk_overlap"],
            },
            {
                "name": "sentence",
                "label": "Sentence chunks",
                "description": "Build chunks around sentence boundaries for high readability and precise citations.",
                "quality": "targeted",
                "latency": "low",
                "cost": "low",
                "best_for": ["citation-sensitive outputs", "short-form documents"],
                "tunable_fields": ["chunk_size", "chunk_overlap"],
            },
        ]
        return ToolExecutionResult(
            status="ok",
            answer=(
                f"Supported chunking strategies: overlap, semantic, late, sentence. "
                f"The current strategy is '{current_config['chunk_strategy']}' with size={current_config['chunk_size']} "
                f"and overlap={current_config['chunk_overlap']}."
            ),
            result={
                "subject": "chunking",
                "current_config": current_config,
                "options": options,
            },
        )


class GetEmbeddingCapabilityCatalogTool:
    name = "get_embedding_capability_catalog"
    metadata = ToolMetadata(
        name=name,
        description="Describe the current embedding configuration, available embedding controls, and the embedding service endpoint.",
        arguments_schema={},
        output_description="Returns the current embedding settings and the tunable embedding capabilities exposed by the stack.",
        requires_confirmation=False,
        goal_tags=["cost", "quality", "indexing", "embedding"],
        affects=["embedding", "retrieval", "indexing"],
        impact_summary="Explains the active embedding setup and the controls that influence embedding quality, throughput, and indexing cost.",
        expected_tradeoffs=[
            "Stronger embedding models can improve retrieval quality but raise indexing cost.",
            "Changing embedding space often implies corpus reindexing to stay consistent.",
        ],
        best_for=["embedding diagnostics", "cost vs quality decisions", "indexing planning"],
        risk_level="low",
        typical_followups=["update_embedding_model", "reindex_corpus", "run_rag_evaluation"],
    )

    def __init__(self, settings: Settings, store: EnvConfigStore | None = None) -> None:
        self._settings = settings
        self._store = store or EnvConfigStore()

    def execute(self, arguments: dict) -> ToolExecutionResult:
        current_config = {
            "embedding_model": self._store.get("EMBEDDING_MODEL", self._settings.embedding_model),
            "embedding_dimensions": self._store.get("EMBEDDING_DIMENSIONS", "") or None,
            "embedding_batch_size": self._store.get("EMBEDDING_BATCH_SIZE", "64"),
            "embedding_service_base_url": self._settings.embedding_base_url,
        }
        capabilities = {
            "supported_controls": [
                "embedding_model",
                "embedding_dimensions",
                "embedding_batch_size",
            ],
            "service_endpoint": self._settings.embedding_base_url,
            "operational_notes": [
                "Changing the embedding model affects future indexing behavior.",
                "Reindexing is typically required when switching embedding space.",
            ],
        }
        return ToolExecutionResult(
            status="ok",
            answer=(
                f"The embedding service is '{self._settings.embedding_base_url}' and the current model is "
                f"'{current_config['embedding_model']}'."
            ),
            result={
                "subject": "embedding",
                "current_config": current_config,
                "capabilities": capabilities,
            },
        )


class GetEvaluationCapabilityCatalogTool:
    name = "get_evaluation_capability_catalog"
    metadata = ToolMetadata(
        name=name,
        description="Describe the evaluation capabilities available to the admin agent, including report access and RAG evaluation execution.",
        arguments_schema={},
        output_description="Returns the evaluation endpoint, report location, and supported evaluation operations.",
        requires_confirmation=False,
        goal_tags=["quality", "validation", "risk_reduction"],
        affects=["evaluation"],
        impact_summary="Helps the admin understand how to validate changes before or after adjusting system configuration.",
        expected_tradeoffs=[
            "Evaluation adds time and compute cost but reduces guesswork when changing configuration.",
            "Evaluation does not change production behavior by itself; it validates proposed changes.",
        ],
        best_for=["post-change validation", "baseline comparison", "quality monitoring"],
        risk_level="low",
        typical_followups=["get_evaluation_report", "run_rag_evaluation"],
    )

    def __init__(self, settings: Settings) -> None:
        self._settings = settings

    def execute(self, arguments: dict) -> ToolExecutionResult:
        operations = [
            {
                "name": "run_rag_evaluation",
                "description": "Execute the generation-service Ragas evaluation runner against a dataset.",
                "risk": "medium",
            },
            {
                "name": "get_evaluation_report",
                "description": "Read and summarize the latest available evaluation report.",
                "risk": "low",
            },
        ]
        return ToolExecutionResult(
            status="ok",
            answer=(
                f"Evaluation operations are available through '{self._settings.evaluation_base_url}', "
                "with report reading and evaluation execution supported."
            ),
            result={
                "subject": "evaluation",
                "current_config": {
                    "evaluation_base_url": self._settings.evaluation_base_url,
                    "report_directory": "services/generation-service/evaluation_reports",
                },
                "operations": operations,
            },
        )


class GetPipelineStatusTool:
    name = "get_pipeline_status"
    metadata = ToolMetadata(
        name=name,
        description="Check the health and availability of the backend pipeline services.",
        arguments_schema={},
        output_description="Returns per-service health details keyed by service name.",
        requires_confirmation=False,
        goal_tags=["stability", "latency", "operations"],
        affects=["auth", "embedding", "retrieval", "generation", "ingestion"],
        impact_summary="Provides current service health so the admin can rule out outages before making configuration changes.",
        expected_tradeoffs=[
            "This is diagnostic only and does not change system state.",
        ],
        best_for=["incident triage", "pre-change checks", "service diagnostics"],
        risk_level="low",
        typical_followups=["restart_services"],
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
        goal_tags=["cost", "quality", "embedding"],
        affects=["embedding", "retrieval", "indexing"],
        impact_summary="Shows the current embedding setup that drives indexing cost and retrieval quality.",
        expected_tradeoffs=[
            "Embedding-model changes can alter retrieval quality and indexing cost.",
        ],
        best_for=["current-state inspection", "embedding diagnostics"],
        risk_level="low",
        typical_followups=["update_embedding_model", "reindex_corpus"],
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
        goal_tags=["cost", "quality", "embedding", "indexing"],
        affects=["embedding", "retrieval", "indexing"],
        impact_summary="Changes the embedding model, which can reduce or increase indexing cost and retrieval quality across the stack.",
        expected_tradeoffs=[
            "Cheaper embedding models can lower cost but may reduce retrieval quality.",
            "Changing embedding space often requires reindexing to apply consistently.",
        ],
        best_for=["embedding cost reduction", "embedding quality upgrades"],
        risk_level="medium",
        requires_reindex=True,
        typical_followups=["reindex_corpus", "run_rag_evaluation"],
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
        goal_tags=["cost", "quality", "latency", "chunking"],
        affects=["preprocessing", "retrieval", "citation_quality"],
        impact_summary="Shows the current chunking setup that influences chunk count, retrieval behavior, and indexing cost.",
        expected_tradeoffs=[
            "More chunks can improve retrieval precision but raise preprocessing and indexing cost.",
        ],
        best_for=["current-state inspection", "chunking diagnostics"],
        risk_level="low",
        typical_followups=["get_chunking_strategy_catalog", "update_chunking_config"],
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
        goal_tags=["cost", "quality", "latency", "chunking"],
        affects=["preprocessing", "retrieval", "citation_quality", "indexing"],
        impact_summary="Changes chunking behavior, which affects chunk volume, indexing cost, retrieval quality, and citation granularity.",
        expected_tradeoffs=[
            "Larger chunks can reduce chunk count and cost but may lower precision.",
            "Changing chunking usually needs reindexing to affect existing indexed data.",
        ],
        best_for=["cost reduction planning", "retrieval tuning", "citation tuning"],
        risk_level="medium",
        requires_reindex=True,
        typical_followups=["reindex_corpus", "run_rag_evaluation"],
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
        goal_tags=["cost", "latency", "quality", "ranking"],
        affects=["retrieval", "generation"],
        impact_summary="Shows the active reranker settings that influence ranking quality, latency, and serving cost.",
        expected_tradeoffs=[
            "Higher-quality rerankers usually add latency and cost to retrieval.",
        ],
        best_for=["current-state inspection", "reranker diagnostics"],
        risk_level="low",
        typical_followups=["get_reranker_strategy_catalog", "update_reranker_config"],
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
        goal_tags=["cost", "latency", "quality", "ranking"],
        affects=["retrieval", "generation"],
        impact_summary="Changes the reranker used at retrieval time, which can improve answer relevance but also increase latency and serving cost.",
        expected_tradeoffs=[
            "Cross-encoder usually improves quality with moderate latency and cost.",
            "LLM batch reranking usually increases quality further but is slower and more expensive.",
            "Disabling reranking reduces cost and latency but may lower answer quality.",
        ],
        best_for=["cost vs quality tuning", "latency reduction", "ranking optimization"],
        risk_level="medium",
        typical_followups=["restart_services", "run_rag_evaluation"],
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
