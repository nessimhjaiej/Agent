from __future__ import annotations

import asyncio
import dataclasses
import importlib.util
import os
import re
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import httpx
from pydantic import BaseModel, Field

from app.config import Settings


class MCPToolDescriptor(BaseModel):
    name: str
    description: str
    service: str
    operation: str
    mutation: bool = False
    requires_confirmation: bool = False
    timeout_seconds: int = 30
    input_schema: dict[str, Any] = Field(default_factory=dict)


class MCPToolResult(BaseModel):
    tool_name: str
    service: str
    operation: str
    arguments: dict[str, Any] = Field(default_factory=dict)
    result: dict[str, Any] = Field(default_factory=dict)
    executed_at_utc: datetime = Field(default_factory=lambda: datetime.now(UTC))


class MCPToolNotFoundError(ValueError):
    pass


class MCPToolSelection(BaseModel):
    tool_name: str
    arguments: dict[str, Any] = Field(default_factory=dict)
    rationale: str


class MCPToolValidationResult(BaseModel):
    valid: bool
    normalized_arguments: dict[str, Any] = Field(default_factory=dict)
    error: str | None = None


class MCPClient:
    def __init__(self, settings: Settings) -> None:
        self._settings = settings
        self._tool_catalog = self._build_tool_catalog()

    async def discover_tools(self) -> list[MCPToolDescriptor]:
        return list(self._tool_catalog.values())

    async def get_tool(self, tool_name: str) -> MCPToolDescriptor:
        descriptor = self._tool_catalog.get(tool_name)
        if descriptor is None:
            raise MCPToolNotFoundError(f"Unknown MCP tool '{tool_name}'.")
        return descriptor

    async def select_tool_for_message(self, message: str) -> MCPToolSelection | None:
        lowered = message.strip().lower()
        update_chunking_args = self._extract_chunking_update_args(message)
        if update_chunking_args:
            return MCPToolSelection(
                tool_name="update_chunking_config",
                arguments=update_chunking_args,
                rationale="The request is asking to change chunking settings for the preprocessing service.",
            )
        update_retrieval_args = self._extract_retrieval_update_args(message)
        if update_retrieval_args:
            return MCPToolSelection(
                tool_name="update_retrieval_config",
                arguments=update_retrieval_args,
                rationale="The request is asking to change retrieval defaults for the retrieval service.",
            )
        update_reranking_args = self._extract_reranking_update_args(message)
        if update_reranking_args:
            return MCPToolSelection(
                tool_name="update_reranking_config",
                arguments=update_reranking_args,
                rationale="The request is asking to change reranking settings for the retrieval service.",
            )
        if "rerank" in lowered and any(term in lowered for term in ("strategy", "config", "setting", "current", "what", "show")):
            return MCPToolSelection(
                tool_name="get_reranking_config",
                arguments={},
                rationale="The request is asking for the current reranking configuration.",
            )
        if "retrieval" in lowered and any(term in lowered for term in ("strategy", "config", "setting", "current", "what", "show")):
            return MCPToolSelection(
                tool_name="get_retrieval_config",
                arguments={},
                rationale="The request is asking for the current retrieval configuration.",
            )
        if "chunking" in lowered and any(term in lowered for term in ("strategy", "config", "setting", "current")):
            return MCPToolSelection(
                tool_name="get_chunking_config",
                arguments={},
                rationale="The request is asking for the current chunking configuration in the preprocessing service.",
            )
        if "config" in lowered and any(term in lowered for term in ("what", "current", "show", "display")):
            inferred_section = None
            for candidate in ("chunk", "retrieval", "rerank", "generation", "embedding", "ingestion", "preprocessing"):
                if candidate in lowered:
                    inferred_section = candidate
                    break
            if inferred_section == "chunk":
                return MCPToolSelection(
                    tool_name="get_chunking_config",
                    arguments={},
                    rationale="The request is asking for the current chunking configuration.",
                )
            if inferred_section == "retrieval":
                return MCPToolSelection(
                    tool_name="get_retrieval_config",
                    arguments={},
                    rationale="The request is asking for the current retrieval configuration.",
                )
            if inferred_section == "rerank":
                return MCPToolSelection(
                    tool_name="get_reranking_config",
                    arguments={},
                    rationale="The request is asking for the current reranking configuration.",
                )
            arguments = {"section": inferred_section} if inferred_section else {}
            return MCPToolSelection(
                tool_name="show_config",
                arguments=arguments,
                rationale="The request is asking to inspect runtime configuration.",
            )
        if lowered.startswith("delete document"):
            document_hint = message.strip()[len("delete document") :].strip()
            arguments: dict[str, Any] = {"query": message.strip()}
            if document_hint:
                arguments["document_id"] = document_hint
            return MCPToolSelection(
                tool_name="delete_document",
                arguments=arguments,
                rationale="The request is asking to remove a document from the knowledge base.",
            )
        if lowered.startswith("restart service"):
            service_name = message.strip()[len("restart service") :].strip()
            return MCPToolSelection(
                tool_name="restart_service",
                arguments={"service_name": service_name or "unknown-service"},
                rationale="The request is asking to restart a named backend service.",
            )
        if lowered.startswith("restart "):
            service_name = message.strip()[len("restart ") :].strip()
            return MCPToolSelection(
                tool_name="restart_service",
                arguments={"service_name": service_name or "unknown-service"},
                rationale="The request is asking to restart a named backend service.",
            )
        if lowered.startswith("reindex"):
            return MCPToolSelection(
                tool_name="reindex_embeddings",
                arguments={"scope": "all"},
                rationale="The request is asking to rebuild or refresh the embedding index.",
            )
        if lowered.startswith("run evaluation"):
            suite = message.strip()[len("run evaluation") :].strip() or "smoke"
            return MCPToolSelection(
                tool_name="run_evaluation",
                arguments={"suite": suite},
                rationale="The request is asking to execute an evaluation suite.",
            )
        if lowered.startswith("show config"):
            section = message.strip()[len("show config") :].strip() or None
            arguments = {"section": section} if section else {}
            return MCPToolSelection(
                tool_name="show_config",
                arguments=arguments,
                rationale="The request is asking to inspect runtime configuration.",
            )
        if lowered.startswith("vector stats"):
            collection = message.strip()[len("vector stats") :].strip() or "default"
            return MCPToolSelection(
                tool_name="get_vector_stats",
                arguments={"collection": collection},
                rationale="The request is asking for vector index statistics.",
            )
        return None

    async def execute_tool(self, tool_name: str, arguments: dict[str, Any]) -> MCPToolResult:
        descriptor = await self.get_tool(tool_name)
        executor_name = f"_execute_{tool_name}"
        executor = getattr(self, executor_name, None)
        if executor is None:
            raise NotImplementedError(f"No MCP adapter executor is implemented for tool '{tool_name}'.")
        payload = await executor(arguments)
        return MCPToolResult(
            tool_name=descriptor.name,
            service=descriptor.service,
            operation=descriptor.operation,
            arguments=dict(arguments),
            result=payload,
        )

    async def validate_tool_request(self, tool_name: str, arguments: dict[str, Any]) -> MCPToolValidationResult:
        validator_name = f"_validate_{tool_name}"
        validator = getattr(self, validator_name, None)
        if validator is None:
            return MCPToolValidationResult(valid=True, normalized_arguments=dict(arguments))
        return await validator(arguments)

    def _build_tool_catalog(self) -> dict[str, MCPToolDescriptor]:
        specs = [
            MCPToolDescriptor(
                name="get_vector_stats",
                description="Retrieve vector index statistics from the embedding stack.",
                service="embedding-service",
                operation="get_vector_stats",
                input_schema={
                    "type": "object",
                    "properties": {
                        "collection": {"type": "string"},
                    },
                    "required": [],
                },
            ),
            MCPToolDescriptor(
                name="show_config",
                description="Show runtime configuration for a named service or config section.",
                service="platform-config",
                operation="show_config",
                input_schema={
                    "type": "object",
                    "properties": {
                        "service_name": {"type": "string"},
                        "section": {"type": "string"},
                    },
                    "required": [],
                },
            ),
            MCPToolDescriptor(
                name="get_chunking_config",
                description="Retrieve the current chunking configuration from the preprocessing service.",
                service="preprocessing-service",
                operation="get_chunking_config",
            ),
            MCPToolDescriptor(
                name="update_chunking_config",
                description="Update chunking configuration in the preprocessing service env overrides.",
                service="preprocessing-service",
                operation="update_chunking_config",
                mutation=True,
                requires_confirmation=True,
                input_schema={
                    "type": "object",
                    "properties": {
                        "chunk_strategy": {"type": "string"},
                        "chunk_size": {"type": "integer"},
                        "chunk_overlap": {"type": "integer"},
                    },
                    "required": [],
                },
            ),
            MCPToolDescriptor(
                name="get_retrieval_config",
                description="Retrieve the current retrieval defaults from the retrieval service.",
                service="retrieval-service",
                operation="get_retrieval_config",
            ),
            MCPToolDescriptor(
                name="update_retrieval_config",
                description="Update retrieval defaults in the retrieval service env overrides.",
                service="retrieval-service",
                operation="update_retrieval_config",
                mutation=True,
                requires_confirmation=True,
                input_schema={
                    "type": "object",
                    "properties": {
                        "top_k_retrieve": {"type": "integer"},
                        "top_k_return": {"type": "integer"},
                        "fusion_type": {"type": "string"},
                        "alpha": {"type": "number"},
                        "rrf_k": {"type": "integer"},
                        "enforce_embedding_model_match": {"type": "boolean"},
                    },
                    "required": [],
                },
            ),
            MCPToolDescriptor(
                name="get_reranking_config",
                description="Retrieve the current reranking configuration from the retrieval service.",
                service="retrieval-service",
                operation="get_reranking_config",
            ),
            MCPToolDescriptor(
                name="update_reranking_config",
                description="Update reranking defaults in the retrieval service env overrides.",
                service="retrieval-service",
                operation="update_reranking_config",
                mutation=True,
                requires_confirmation=True,
                input_schema={
                    "type": "object",
                    "properties": {
                        "ranker_type": {"type": "string"},
                        "rerank_top_n": {"type": "integer"},
                        "cross_encoder_model": {"type": "string"},
                        "cross_encoder_batch_size": {"type": "integer"},
                        "llm_rerank_model": {"type": "string"},
                        "llm_rerank_batch_size": {"type": "integer"},
                        "llm_rerank_max_chars": {"type": "integer"},
                        "llm_rerank_temperature": {"type": "number"},
                        "llm_rerank_timeout_seconds": {"type": "integer"},
                    },
                    "required": [],
                },
            ),
            MCPToolDescriptor(
                name="reindex_embeddings",
                description="Trigger a reindexing operation for embeddings.",
                service="embedding-service",
                operation="reindex_embeddings",
                mutation=True,
                requires_confirmation=True,
                timeout_seconds=120,
                input_schema={
                    "type": "object",
                    "properties": {
                        "scope": {"type": "string"},
                    },
                    "required": ["scope"],
                },
            ),
            MCPToolDescriptor(
                name="delete_document",
                description="Delete a document from the knowledge base.",
                service="ingestion-service",
                operation="delete_document",
                mutation=True,
                requires_confirmation=True,
                timeout_seconds=60,
                input_schema={
                    "type": "object",
                    "properties": {
                        "document_id": {"type": "string"},
                        "query": {"type": "string"},
                    },
                    "required": [],
                },
            ),
            MCPToolDescriptor(
                name="run_evaluation",
                description="Run an evaluation workflow for the generation stack.",
                service="generation-service",
                operation="run_evaluation",
                mutation=True,
                requires_confirmation=False,
                timeout_seconds=180,
                input_schema={
                    "type": "object",
                    "properties": {
                        "suite": {"type": "string"},
                    },
                    "required": ["suite"],
                },
            ),
            MCPToolDescriptor(
                name="restart_service",
                description="Restart a named backend service.",
                service="platform-runtime",
                operation="restart_service",
                mutation=True,
                requires_confirmation=True,
                timeout_seconds=45,
                input_schema={
                    "type": "object",
                    "properties": {
                        "service_name": {"type": "string"},
                    },
                    "required": ["service_name"],
                },
            ),
        ]
        return {spec.name: spec for spec in specs}

    async def _execute_get_vector_stats(self, arguments: dict[str, Any]) -> dict[str, Any]:
        collection = str(arguments.get("collection") or self._load_embedding_settings().get("weaviate_collection", "Chunk"))
        if self._under_test():
            return {
                "status": "stubbed",
                "collection": collection,
                "vector_count": 0,
                "weaviate_url": self._load_embedding_settings().get("weaviate_http_url"),
                "note": "Live vector stats are skipped during tests.",
            }

        embedding_settings = self._load_embedding_settings()
        weaviate_url = str(embedding_settings.get("weaviate_http_url", "http://localhost:8080")).rstrip("/")
        query = {"query": f"{{ Aggregate {{ {collection} {{ meta {{ count }} }} }} }}"}
        try:
            async with httpx.AsyncClient(timeout=self._settings.integration_http_timeout_seconds) as client:
                response = await client.post(f"{weaviate_url}/v1/graphql", json=query)
                response.raise_for_status()
            payload = response.json()
            count = (
                payload.get("data", {})
                .get("Aggregate", {})
                .get(collection, [{}])[0]
                .get("meta", {})
                .get("count")
            )
            return {
                "status": "ok",
                "collection": collection,
                "vector_count": count,
                "weaviate_url": weaviate_url,
            }
        except Exception as exc:
            return {
                "status": "integration_error",
                "collection": collection,
                "vector_count": None,
                "weaviate_url": weaviate_url,
                "error": str(exc),
            }

    async def _execute_show_config(self, arguments: dict[str, Any]) -> dict[str, Any]:
        service_name = str(arguments.get("service_name") or self._infer_service_from_section(arguments.get("section")) or "generation-service")
        section = arguments.get("section")
        try:
            config_payload = self._load_service_config(service_name)
            if section:
                filtered = {
                    key: value
                    for key, value in config_payload.items()
                    if str(section).lower() in key.lower()
                }
                config_payload = filtered or config_payload
            return {
                "status": "ok",
                "service_name": service_name,
                "section": section,
                "config": config_payload,
            }
        except Exception as exc:
            return {
                "status": "integration_error",
                "service_name": service_name,
                "section": section,
                "error": str(exc),
            }

    async def _execute_get_chunking_config(self, arguments: dict[str, Any]) -> dict[str, Any]:
        config_payload = self._load_service_config("preprocessing-service")
        return {
            "status": "ok",
            "service_name": "preprocessing-service",
            "section": "chunk",
            "config": {
                "chunk_strategy": config_payload.get("chunk_strategy"),
                "chunk_size": config_payload.get("chunk_size"),
                "chunk_overlap": config_payload.get("chunk_overlap"),
            },
        }

    async def _execute_update_chunking_config(self, arguments: dict[str, Any]) -> dict[str, Any]:
        updated = self._write_env_overrides(
            {
                "PREPROCESSING_CHUNK_STRATEGY": arguments.get("chunk_strategy"),
                "PREPROCESSING_CHUNK_SIZE": arguments.get("chunk_size"),
                "PREPROCESSING_CHUNK_OVERLAP": arguments.get("chunk_overlap"),
            }
        )
        return {
            "status": "updated",
            "service_name": "preprocessing-service",
            "updated": updated,
            "env_file": str(self._settings.config_override_env_path),
            "restart_required": True,
            "restart_service": "preprocessing-service",
        }

    async def _execute_get_retrieval_config(self, arguments: dict[str, Any]) -> dict[str, Any]:
        config_payload = self._load_service_config("retrieval-service")
        return {
            "status": "ok",
            "service_name": "retrieval-service",
            "section": "retrieval",
            "config": {
                "top_k_retrieve": config_payload.get("default_top_k_retrieve"),
                "top_k_return": config_payload.get("default_top_k_return"),
                "fusion_type": config_payload.get("default_fusion_type"),
                "alpha": config_payload.get("default_alpha"),
                "rrf_k": config_payload.get("default_rrf_k"),
                "enforce_embedding_model_match": config_payload.get("enforce_embedding_model_match"),
            },
        }

    async def _execute_update_retrieval_config(self, arguments: dict[str, Any]) -> dict[str, Any]:
        updated = self._write_env_overrides(
            {
                "RETRIEVAL_DEFAULT_TOP_K_RETRIEVE": arguments.get("top_k_retrieve"),
                "RETRIEVAL_DEFAULT_TOP_K_RETURN": arguments.get("top_k_return"),
                "RETRIEVAL_DEFAULT_FUSION": arguments.get("fusion_type"),
                "RETRIEVAL_DEFAULT_ALPHA": arguments.get("alpha"),
                "RETRIEVAL_DEFAULT_RRF_K": arguments.get("rrf_k"),
                "RETRIEVAL_ENFORCE_EMBEDDING_MODEL_MATCH": arguments.get("enforce_embedding_model_match"),
            }
        )
        return {
            "status": "updated",
            "service_name": "retrieval-service",
            "section": "retrieval",
            "updated": updated,
            "env_file": str(self._settings.config_override_env_path),
            "restart_required": True,
            "restart_service": "retrieval-service",
        }

    async def _execute_get_reranking_config(self, arguments: dict[str, Any]) -> dict[str, Any]:
        config_payload = self._load_service_config("retrieval-service")
        return {
            "status": "ok",
            "service_name": "retrieval-service",
            "section": "reranking",
            "config": {
                "ranker_type": config_payload.get("default_ranker_type"),
                "rerank_top_n": config_payload.get("default_rerank_top_n"),
                "cross_encoder_model": os.getenv("RETRIEVAL_CROSS_ENCODER_MODEL"),
                "cross_encoder_batch_size": self._parse_optional_int(os.getenv("RETRIEVAL_CROSS_ENCODER_BATCH_SIZE")),
                "llm_rerank_model": os.getenv("RETRIEVAL_LLM_RERANK_MODEL"),
                "llm_rerank_batch_size": self._parse_optional_int(os.getenv("RETRIEVAL_LLM_RERANK_BATCH_SIZE")),
                "llm_rerank_max_chars": self._parse_optional_int(os.getenv("RETRIEVAL_LLM_RERANK_MAX_CHARS")),
                "llm_rerank_temperature": self._parse_optional_float(os.getenv("RETRIEVAL_LLM_RERANK_TEMPERATURE")),
                "llm_rerank_timeout_seconds": self._parse_optional_int(os.getenv("RETRIEVAL_LLM_RERANK_TIMEOUT_SECONDS")),
            },
        }

    async def _execute_update_reranking_config(self, arguments: dict[str, Any]) -> dict[str, Any]:
        updated = self._write_env_overrides(
            {
                "RETRIEVAL_DEFAULT_RANKER": arguments.get("ranker_type"),
                "RETRIEVAL_DEFAULT_RERANK_TOP_N": arguments.get("rerank_top_n"),
                "RETRIEVAL_CROSS_ENCODER_MODEL": arguments.get("cross_encoder_model"),
                "RETRIEVAL_CROSS_ENCODER_BATCH_SIZE": arguments.get("cross_encoder_batch_size"),
                "RETRIEVAL_LLM_RERANK_MODEL": arguments.get("llm_rerank_model"),
                "RETRIEVAL_LLM_RERANK_BATCH_SIZE": arguments.get("llm_rerank_batch_size"),
                "RETRIEVAL_LLM_RERANK_MAX_CHARS": arguments.get("llm_rerank_max_chars"),
                "RETRIEVAL_LLM_RERANK_TEMPERATURE": arguments.get("llm_rerank_temperature"),
                "RETRIEVAL_LLM_RERANK_TIMEOUT_SECONDS": arguments.get("llm_rerank_timeout_seconds"),
            }
        )
        return {
            "status": "updated",
            "service_name": "retrieval-service",
            "section": "reranking",
            "updated": updated,
            "env_file": str(self._settings.config_override_env_path),
            "restart_required": True,
            "restart_service": "retrieval-service",
        }

    async def _execute_reindex_embeddings(self, arguments: dict[str, Any]) -> dict[str, Any]:
        return {
            "status": "not_integrated",
            "scope": arguments.get("scope", "all"),
            "note": "No dedicated reindex endpoint exists in the current backend services yet.",
        }

    async def _execute_delete_document(self, arguments: dict[str, Any]) -> dict[str, Any]:
        document_id = arguments.get("document_id")
        if not document_id:
            return {
                "status": "integration_error",
                "document_id": None,
                "query": arguments.get("query"),
                "error": "delete_document requires a concrete document_id for the current ingestion API.",
            }
        if self._under_test():
            return {
                "status": "accepted",
                "document_id": document_id,
                "query": arguments.get("query"),
                "note": "Live document deletion is skipped during tests.",
            }

        url = f"{self._settings.ingestion_base_url.rstrip('/')}/ingestion/documents/{document_id}"
        try:
            async with httpx.AsyncClient(timeout=self._settings.integration_http_timeout_seconds) as client:
                response = await client.delete(url)
                response.raise_for_status()
            payload = response.json()
            return {
                "status": payload.get("status", "ok"),
                "document_id": payload.get("document_id", document_id),
                "storage_path": payload.get("storage_path"),
            }
        except Exception as exc:
            return {
                "status": "integration_error",
                "document_id": document_id,
                "query": arguments.get("query"),
                "error": str(exc),
            }

    async def _execute_run_evaluation(self, arguments: dict[str, Any]) -> dict[str, Any]:
        suite = str(arguments.get("suite", "smoke")).strip() or "smoke"
        dataset_path = self._dataset_for_suite(suite)
        if self._under_test():
            return {
                "status": "accepted",
                "suite": suite,
                "dataset": str(dataset_path),
                "note": "Live evaluation execution is skipped during tests.",
            }

        command = [
            "python",
            "-m",
            "app.evaluation.ragas_runner",
            "--dataset",
            str(dataset_path),
        ]
        process = await asyncio.create_subprocess_exec(
            *command,
            cwd=str(self._settings.project_root / "services" / "generation-service"),
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, stderr = await process.communicate()
        output = stdout.decode("utf-8", errors="ignore").strip()
        error_output = stderr.decode("utf-8", errors="ignore").strip()
        return {
            "status": "accepted" if process.returncode == 0 else "integration_error",
            "suite": suite,
            "dataset": str(dataset_path),
            "return_code": process.returncode,
            "stdout": output,
            "stderr": error_output,
        }

    async def _execute_restart_service(self, arguments: dict[str, Any]) -> dict[str, Any]:
        raw_service_name = str(arguments.get("service_name") or "").strip()
        service_name = self._normalize_service_name(raw_service_name)
        if self._under_test():
            return {
                "status": "accepted",
                "service_name": service_name,
                "note": "Live service restart is skipped during tests.",
            }

        script_path = self._settings.project_root / "scripts" / "restart-local-services.ps1"
        process = await asyncio.create_subprocess_exec(
            "powershell",
            "-ExecutionPolicy",
            "Bypass",
            "-File",
            str(script_path),
            "-Services",
            service_name,
            cwd=str(self._settings.project_root),
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, stderr = await process.communicate()
        return {
            "status": "accepted" if process.returncode == 0 else "integration_error",
            "service_name": service_name,
            "return_code": process.returncode,
            "stdout": stdout.decode("utf-8", errors="ignore").strip(),
            "stderr": stderr.decode("utf-8", errors="ignore").strip(),
        }

    async def _validate_restart_service(self, arguments: dict[str, Any]) -> MCPToolValidationResult:
        raw_service_name = str(arguments.get("service_name") or "").strip()
        if not raw_service_name:
            return MCPToolValidationResult(valid=False, error="restart_service requires a service_name.")
        normalized = self._normalize_service_name(raw_service_name)
        supported = {
            "auth-service",
            "preprocessing-service",
            "embedding-service",
            "retrieval-service",
            "generation-service",
            "ingestion-service",
            "admin-service",
        }
        if normalized not in supported:
            return MCPToolValidationResult(
                valid=False,
                error=f"Unsupported service '{raw_service_name}'. Allowed values: {', '.join(sorted(supported))}.",
            )
        return MCPToolValidationResult(valid=True, normalized_arguments={"service_name": normalized})

    async def _validate_delete_document(self, arguments: dict[str, Any]) -> MCPToolValidationResult:
        document_id = str(arguments.get("document_id") or "").strip()
        if not document_id:
            return MCPToolValidationResult(
                valid=False,
                error="delete_document requires a concrete document_id. Free-text search is not supported by the current ingestion API.",
            )
        return MCPToolValidationResult(valid=True, normalized_arguments={"document_id": document_id, "query": arguments.get("query")})

    async def _validate_run_evaluation(self, arguments: dict[str, Any]) -> MCPToolValidationResult:
        suite = str(arguments.get("suite", "smoke")).strip() or "smoke"
        dataset_path = self._dataset_for_suite(suite)
        if not dataset_path.exists():
            return MCPToolValidationResult(
                valid=False,
                error=f"Evaluation dataset '{dataset_path}' does not exist.",
            )
        return MCPToolValidationResult(valid=True, normalized_arguments={"suite": suite})

    async def _validate_update_chunking_config(self, arguments: dict[str, Any]) -> MCPToolValidationResult:
        normalized: dict[str, Any] = {}
        if arguments.get("chunk_strategy") is not None:
            strategy = str(arguments.get("chunk_strategy")).strip()
            if not strategy:
                return MCPToolValidationResult(valid=False, error="chunk_strategy cannot be empty.")
            normalized["chunk_strategy"] = strategy
        if arguments.get("chunk_size") is not None:
            chunk_size = self._coerce_positive_int(arguments.get("chunk_size"), "chunk_size")
            if chunk_size is None:
                return MCPToolValidationResult(valid=False, error="chunk_size must be a positive integer.")
            normalized["chunk_size"] = chunk_size
        if arguments.get("chunk_overlap") is not None:
            chunk_overlap = self._coerce_non_negative_int(arguments.get("chunk_overlap"), "chunk_overlap")
            if chunk_overlap is None:
                return MCPToolValidationResult(valid=False, error="chunk_overlap must be a non-negative integer.")
            normalized["chunk_overlap"] = chunk_overlap
        if not normalized:
            return MCPToolValidationResult(valid=False, error="update_chunking_config requires at least one config field.")
        return MCPToolValidationResult(valid=True, normalized_arguments=normalized)

    async def _validate_update_retrieval_config(self, arguments: dict[str, Any]) -> MCPToolValidationResult:
        normalized: dict[str, Any] = {}
        if arguments.get("top_k_retrieve") is not None:
            value = self._coerce_positive_int(arguments.get("top_k_retrieve"), "top_k_retrieve")
            if value is None:
                return MCPToolValidationResult(valid=False, error="top_k_retrieve must be a positive integer.")
            normalized["top_k_retrieve"] = value
        if arguments.get("top_k_return") is not None:
            value = self._coerce_positive_int(arguments.get("top_k_return"), "top_k_return")
            if value is None:
                return MCPToolValidationResult(valid=False, error="top_k_return must be a positive integer.")
            normalized["top_k_return"] = value
        if arguments.get("fusion_type") is not None:
            value = str(arguments.get("fusion_type")).strip().lower()
            if value not in {"alpha", "rrf"}:
                return MCPToolValidationResult(valid=False, error="fusion_type must be 'alpha' or 'rrf'.")
            normalized["fusion_type"] = value
        if arguments.get("alpha") is not None:
            try:
                alpha = float(arguments.get("alpha"))
            except (TypeError, ValueError):
                return MCPToolValidationResult(valid=False, error="alpha must be a number between 0 and 1.")
            if alpha < 0 or alpha > 1:
                return MCPToolValidationResult(valid=False, error="alpha must be a number between 0 and 1.")
            normalized["alpha"] = alpha
        if arguments.get("rrf_k") is not None:
            value = self._coerce_positive_int(arguments.get("rrf_k"), "rrf_k")
            if value is None:
                return MCPToolValidationResult(valid=False, error="rrf_k must be a positive integer.")
            normalized["rrf_k"] = value
        if arguments.get("enforce_embedding_model_match") is not None:
            parsed = self._coerce_bool(arguments.get("enforce_embedding_model_match"))
            if parsed is None:
                return MCPToolValidationResult(valid=False, error="enforce_embedding_model_match must be a boolean.")
            normalized["enforce_embedding_model_match"] = parsed
        if not normalized:
            return MCPToolValidationResult(valid=False, error="update_retrieval_config requires at least one config field.")
        return MCPToolValidationResult(valid=True, normalized_arguments=normalized)

    async def _validate_update_reranking_config(self, arguments: dict[str, Any]) -> MCPToolValidationResult:
        normalized: dict[str, Any] = {}
        if arguments.get("ranker_type") is not None:
            value = self._normalize_ranker_type(arguments.get("ranker_type"))
            if value not in {"none", "cross_encoder", "llm_batch"}:
                return MCPToolValidationResult(valid=False, error="ranker_type must be 'none', 'cross_encoder', or 'llm_batch'.")
            normalized["ranker_type"] = value
        for key in ("rerank_top_n", "cross_encoder_batch_size", "llm_rerank_batch_size", "llm_rerank_max_chars", "llm_rerank_timeout_seconds"):
            if arguments.get(key) is not None:
                value = self._coerce_positive_int(arguments.get(key), key)
                if value is None:
                    return MCPToolValidationResult(valid=False, error=f"{key} must be a positive integer.")
                normalized[key] = value
        if arguments.get("llm_rerank_temperature") is not None:
            try:
                normalized["llm_rerank_temperature"] = float(arguments.get("llm_rerank_temperature"))
            except (TypeError, ValueError):
                return MCPToolValidationResult(valid=False, error="llm_rerank_temperature must be a number.")
        for key in ("cross_encoder_model", "llm_rerank_model"):
            if arguments.get(key) is not None:
                value = str(arguments.get(key)).strip()
                if not value:
                    return MCPToolValidationResult(valid=False, error=f"{key} cannot be empty.")
                normalized[key] = value
        if not normalized:
            return MCPToolValidationResult(valid=False, error="update_reranking_config requires at least one config field.")
        return MCPToolValidationResult(valid=True, normalized_arguments=normalized)

    def _under_test(self) -> bool:
        return bool(os.getenv("PYTEST_CURRENT_TEST"))

    def _normalize_service_name(self, value: str) -> str:
        normalized = value.strip().lower()
        aliases = {
            "auth": "auth-service",
            "auth-service": "auth-service",
            "preprocessing": "preprocessing-service",
            "preprocessing-service": "preprocessing-service",
            "embedding": "embedding-service",
            "embedding-service": "embedding-service",
            "retrieval": "retrieval-service",
            "retrieval-service": "retrieval-service",
            "generation": "generation-service",
            "generation-service": "generation-service",
            "ingestion": "ingestion-service",
            "ingestion-service": "ingestion-service",
            "admin": "admin-service",
            "admin-service": "admin-service",
        }
        return aliases.get(normalized, normalized if normalized.endswith("-service") else f"{normalized}-service")

    def _dataset_for_suite(self, suite: str) -> Path:
        suite_map = {
            "smoke": self._settings.project_root / "services" / "generation-service" / "evals" / "sample_eval_dataset.json",
        }
        return suite_map.get(suite.lower(), Path(suite))

    def _infer_service_from_section(self, section: Any) -> str | None:
        if not section:
            return None
        value = str(section).lower()
        mapping = {
            "chunk": "preprocessing-service",
            "preprocessing": "preprocessing-service",
            "retrieval": "retrieval-service",
            "generation": "generation-service",
            "embedding": "embedding-service",
            "ingestion": "ingestion-service",
        }
        for key, service_name in mapping.items():
            if key in value:
                return service_name
        return None

    def _load_service_config(self, service_name: str) -> dict[str, Any]:
        normalized = self._normalize_service_name(service_name)
        config_path = self._settings.project_root / "services" / normalized / "app" / "config.py"
        if not config_path.exists():
            raise FileNotFoundError(f"No config module found for service '{normalized}'.")
        module = self._load_module(config_path, f"admin_service_config_{normalized.replace('-', '_')}")
        settings_factory = getattr(module, "Settings", None)
        if settings_factory is None:
            raise AttributeError(f"Config module for '{normalized}' does not define Settings.")
        if hasattr(settings_factory, "from_env"):
            settings_obj = settings_factory.from_env()
        else:
            settings_obj = settings_factory()
        if hasattr(settings_obj, "model_dump"):
            return settings_obj.model_dump(mode="json")
        if dataclasses.is_dataclass(settings_obj):
            return dataclasses.asdict(settings_obj)
        if hasattr(settings_obj, "__dict__"):
            return {
                key: value
                for key, value in vars(settings_obj).items()
                if not key.startswith("_")
            }
        raise TypeError(f"Unsupported settings object for '{normalized}'.")

    def _load_embedding_settings(self) -> dict[str, Any]:
        return self._load_service_config("embedding-service")

    def _write_env_overrides(self, updates: dict[str, Any]) -> dict[str, Any]:
        env_path = self._settings.config_override_env_path
        env_path.parent.mkdir(parents=True, exist_ok=True)
        existing_lines = env_path.read_text(encoding="utf-8").splitlines() if env_path.exists() else []
        pending = {
            key: self._stringify_env_value(value)
            for key, value in updates.items()
            if value is not None
        }
        if not pending:
            return {}

        updated: dict[str, Any] = {}
        new_lines: list[str] = []
        seen: set[str] = set()

        for line in existing_lines:
            stripped = line.strip()
            if not stripped or stripped.startswith("#") or "=" not in line:
                new_lines.append(line)
                continue
            key, _sep, _value = line.partition("=")
            env_key = key.strip()
            if env_key in pending:
                new_value = pending[env_key]
                new_lines.append(f"{env_key}={new_value}")
                seen.add(env_key)
                updated[env_key] = self._parse_env_value(new_value)
            else:
                new_lines.append(line)

        for env_key, env_value in pending.items():
            if env_key in seen:
                continue
            new_lines.append(f"{env_key}={env_value}")
            updated[env_key] = self._parse_env_value(env_value)

        env_path.write_text("\n".join(new_lines).rstrip() + "\n", encoding="utf-8")
        return updated

    def _extract_chunking_update_args(self, message: str) -> dict[str, Any]:
        lowered = message.lower()
        if "chunk" not in lowered or not any(term in lowered for term in ("set", "update", "change")):
            return {}
        arguments: dict[str, Any] = {}
        match = re.search(r"chunk(?:ing)? strategy(?:\s+\w+)*\s+(?:to|=)\s*([a-zA-Z_][\w-]*)", lowered)
        if match:
            arguments["chunk_strategy"] = match.group(1)
        match = re.search(r"chunk(?:ing)? size(?:\s+\w+)*\s+(?:to|=)\s*(\d+)", lowered)
        if match:
            arguments["chunk_size"] = int(match.group(1))
        match = re.search(r"overlap(?:\s+\w+)*\s+(?:to|=)\s*(\d+)", lowered)
        if match:
            arguments["chunk_overlap"] = int(match.group(1))
        return arguments

    def _extract_retrieval_update_args(self, message: str) -> dict[str, Any]:
        lowered = message.lower()
        if "retrieval" not in lowered or not any(term in lowered for term in ("set", "update", "change")):
            return {}
        arguments: dict[str, Any] = {}
        for pattern, key in (
            (r"top[_ ]k[_ ]retrieve(?:\s+\w+)*\s+(?:to|=)\s*(\d+)", "top_k_retrieve"),
            (r"top[_ ]k[_ ]return(?:\s+\w+)*\s+(?:to|=)\s*(\d+)", "top_k_return"),
            (r"rrf[_ ]k(?:\s+\w+)*\s+(?:to|=)\s*(\d+)", "rrf_k"),
        ):
            match = re.search(pattern, lowered)
            if match:
                arguments[key] = int(match.group(1))
        match = re.search(r"alpha(?:\s+\w+)*\s+(?:to|=)\s*([0-9]*\.?[0-9]+)", lowered)
        if match:
            arguments["alpha"] = float(match.group(1))
        match = re.search(r"fusion(?: type)?(?:\s+\w+)*\s+(?:to|=)\s*(alpha|rrf)", lowered)
        if match:
            arguments["fusion_type"] = match.group(1)
        match = re.search(r"retrieval strategy(?:\s+\w+)*\s+(?:to|=)\s*(alpha|rrf)", lowered)
        if match:
            arguments["fusion_type"] = match.group(1)
        if "enforce embedding model match" in lowered:
            bool_value = self._extract_boolean_phrase(lowered, "enforce embedding model match")
            if bool_value is not None:
                arguments["enforce_embedding_model_match"] = bool_value
        return arguments

    def _extract_reranking_update_args(self, message: str) -> dict[str, Any]:
        lowered = message.lower()
        if "rerank" not in lowered and "ranker" not in lowered:
            return {}
        if not any(term in lowered for term in ("set", "update", "change")):
            return {}
        arguments: dict[str, Any] = {}
        match = re.search(r"(?:rerank(?:ing)?|ranker)(?: type| strategy)?(?:\s+\w+)*\s+(?:to|=)\s*(none|cross[_ -]?encoder|llm[_ -]?batch)", lowered)
        if match:
            arguments["ranker_type"] = self._normalize_ranker_type(match.group(1))
        match = re.search(r"rerank top n(?:\s+\w+)*\s+(?:to|=)\s*(\d+)", lowered)
        if match:
            arguments["rerank_top_n"] = int(match.group(1))
        for pattern, key in (
            (r"cross encoder batch size(?:\s+\w+)*\s+(?:to|=)\s*(\d+)", "cross_encoder_batch_size"),
            (r"llm rerank batch size(?:\s+\w+)*\s+(?:to|=)\s*(\d+)", "llm_rerank_batch_size"),
            (r"llm rerank max chars(?:\s+\w+)*\s+(?:to|=)\s*(\d+)", "llm_rerank_max_chars"),
            (r"llm rerank timeout(?: seconds)?(?:\s+\w+)*\s+(?:to|=)\s*(\d+)", "llm_rerank_timeout_seconds"),
        ):
            match = re.search(pattern, lowered)
            if match:
                arguments[key] = int(match.group(1))
        match = re.search(r"llm rerank temperature(?:\s+\w+)*\s+(?:to|=)\s*([0-9]*\.?[0-9]+)", lowered)
        if match:
            arguments["llm_rerank_temperature"] = float(match.group(1))
        return arguments

    def _extract_boolean_phrase(self, lowered: str, phrase: str) -> bool | None:
        if f"{phrase} to true" in lowered or f"{phrase} to yes" in lowered or f"{phrase} to on" in lowered:
            return True
        if f"{phrase} to false" in lowered or f"{phrase} to no" in lowered or f"{phrase} to off" in lowered:
            return False
        return None

    def _stringify_env_value(self, value: Any) -> str:
        if isinstance(value, bool):
            return "true" if value else "false"
        return str(value)

    def _parse_env_value(self, value: str) -> Any:
        lowered = value.lower()
        if lowered in {"true", "false"}:
            return lowered == "true"
        try:
            if "." in value:
                return float(value)
            return int(value)
        except ValueError:
            return value

    def _coerce_positive_int(self, value: Any, _name: str) -> int | None:
        try:
            parsed = int(value)
        except (TypeError, ValueError):
            return None
        return parsed if parsed > 0 else None

    def _coerce_non_negative_int(self, value: Any, _name: str) -> int | None:
        try:
            parsed = int(value)
        except (TypeError, ValueError):
            return None
        return parsed if parsed >= 0 else None

    def _coerce_bool(self, value: Any) -> bool | None:
        if isinstance(value, bool):
            return value
        lowered = str(value).strip().lower()
        if lowered in {"true", "1", "yes", "on"}:
            return True
        if lowered in {"false", "0", "no", "off"}:
            return False
        return None

    def _parse_optional_int(self, value: str | None) -> int | None:
        if value is None or value.strip() == "":
            return None
        try:
            return int(value)
        except ValueError:
            return None

    def _parse_optional_float(self, value: str | None) -> float | None:
        if value is None or value.strip() == "":
            return None
        try:
            return float(value)
        except ValueError:
            return None

    def _normalize_ranker_type(self, value: Any) -> str:
        return str(value).strip().lower().replace("-", "_").replace(" ", "_")

    def _load_module(self, path: Path, module_name: str):
        spec = importlib.util.spec_from_file_location(module_name, path)
        if spec is None or spec.loader is None:
            raise ImportError(f"Could not load module from '{path}'.")
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        return module
