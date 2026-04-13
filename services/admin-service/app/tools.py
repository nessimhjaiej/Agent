from __future__ import annotations

import re
from pathlib import Path
from typing import Any

import httpx
from langchain_core.tools import tool

from app.config import Settings


CONFIG_SCOPES: dict[str, dict[str, Any]] = {
    "preprocessing": {
        "keys": {
            "chunk_strategy": ("PREPROCESSING_CHUNK_STRATEGY", str),
            "chunk_size": ("PREPROCESSING_CHUNK_SIZE", int),
            "chunk_overlap": ("PREPROCESSING_CHUNK_OVERLAP", int),
            "pipeline_version": ("PREPROCESSING_PIPELINE_VERSION", str),
        },
        "aliases": {"chunking", "chunk", "chunks", "preprocessing"},
    },
    "retrieval": {
        "keys": {
            "top_k_retrieve": ("RETRIEVAL_DEFAULT_TOP_K_RETRIEVE", int),
            "top_k_return": ("RETRIEVAL_DEFAULT_TOP_K_RETURN", int),
            "fusion": ("RETRIEVAL_DEFAULT_FUSION", str),
            "alpha": ("RETRIEVAL_DEFAULT_ALPHA", float),
            "rrf_k": ("RETRIEVAL_DEFAULT_RRF_K", int),
            "ranker": ("RETRIEVAL_DEFAULT_RANKER", str),
            "rerank_top_n": ("RETRIEVAL_DEFAULT_RERANK_TOP_N", int),
        },
        "aliases": {"retrieval", "reranking", "reranker", "ranker"},
    },
    "embedding": {
        "keys": {
            "embedding_model": ("EMBEDDING_MODEL", str),
            "embedding_dimensions": ("EMBEDDING_DIMENSIONS", int),
            "embedding_batch_size": ("EMBEDDING_BATCH_SIZE", int),
        },
        "aliases": {"embedding", "embeddings"},
    },
    "generation": {
        "keys": {
            "generation_model": ("GENERATION_MODEL", str),
            "temperature": ("GENERATION_TEMPERATURE", float),
            "max_context_chunks": ("GENERATION_MAX_CONTEXT_CHUNKS", int),
            "require_citations": ("GENERATION_REQUIRE_CITATIONS", str),
        },
        "aliases": {"generation", "answering"},
    },
}

CHUNKING_METHODS: tuple[tuple[str, bool], ...] = (
    ("late", True),
    ("overlap", True),
    ("semantic", True),
    ("sentence", False),
)


class AdminToolbox:
    def __init__(self, settings: Settings, access_token: str | None = None) -> None:
        self._settings = settings
        self._access_token = access_token

    def with_access_token(self, access_token: str | None) -> "AdminToolbox":
        return AdminToolbox(self._settings, access_token=access_token)

    def _client(self) -> httpx.Client:
        return httpx.Client(timeout=60.0)

    def _env_files(self) -> list[Path]:
        root = self._settings.project_root
        return [root / ".env", root / ".env.local"]

    def _read_env_map(self) -> tuple[dict[str, str], dict[str, str]]:
        values: dict[str, str] = {}
        sources: dict[str, str] = {}
        for path in self._env_files():
            if not path.exists():
                continue
            for raw_line in path.read_text(encoding="utf-8").splitlines():
                line = raw_line.strip()
                if not line or line.startswith("#") or "=" not in line:
                    continue
                key, value = line.split("=", 1)
                key = key.strip()
                values[key] = value.strip()
                sources[key] = path.name
        return values, sources

    def _coerce(self, raw: str, caster: type) -> Any:
        if caster is int:
            return int(raw) if raw.strip() else None
        if caster is float:
            return float(raw) if raw.strip() else None
        return raw

    def _get_preprocessing_config(self) -> dict[str, Any]:
        with self._client() as client:
            response = client.get(f"{self._settings.preprocessing_base_url.rstrip('/')}/preprocessing/config")
            response.raise_for_status()
            return response.json()

    def _update_preprocessing_config(self, changes: dict[str, Any]) -> dict[str, Any]:
        with self._client() as client:
            response = client.put(
                f"{self._settings.preprocessing_base_url.rstrip('/')}/preprocessing/config",
                json=changes,
            )
            response.raise_for_status()
            return response.json()

    def get_repo_config(self, service_name: str) -> dict[str, Any]:
        normalized = self.resolve_config_scope(service_name)
        scope = CONFIG_SCOPES.get(normalized)
        if scope is None:
            raise ValueError(f"Unsupported config scope: {service_name}")

        if normalized == "preprocessing":
            return self._get_preprocessing_config()

        values, sources = self._read_env_map()
        config: dict[str, Any] = {}
        source_map: dict[str, str] = {}
        for field_name, (env_name, caster) in scope["keys"].items():
            raw = values.get(env_name, "")
            config[field_name] = self._coerce(raw, caster) if raw != "" else None
            source_map[field_name] = sources.get(env_name, "unset")
        return {"status": "ok", "scope": normalized, "config": config, "sources": source_map}

    def get_chunking_methods(self) -> dict[str, Any]:
        config_payload = self.get_repo_config("preprocessing")
        return {
            "status": "ok",
            "scope": "preprocessing",
            "current_strategy": config_payload["config"].get("chunk_strategy"),
            "current_chunk_size": config_payload["config"].get("chunk_size"),
            "current_chunk_overlap": config_payload["config"].get("chunk_overlap"),
            "methods": [
                {"name": name, "implemented": implemented}
                for name, implemented in CHUNKING_METHODS
            ],
        }

    def update_repo_config(self, service_name: str, changes: dict[str, Any]) -> dict[str, Any]:
        normalized = self.resolve_config_scope(service_name)
        scope = CONFIG_SCOPES.get(normalized)
        if scope is None:
            raise ValueError(f"Unsupported config scope: {service_name}")
        if not isinstance(changes, dict) or not changes:
            raise ValueError("changes must contain at least one supported field")

        if normalized == "preprocessing":
            return self._update_preprocessing_config(changes)

        lines: list[str] = []
        env_local = self._settings.project_root / ".env.local"
        if env_local.exists():
            lines = env_local.read_text(encoding="utf-8").splitlines()

        updated_fields: dict[str, Any] = {}
        mapping = scope["keys"]
        for field_name, value in changes.items():
            if field_name not in mapping:
                raise ValueError(f"Unsupported field for {normalized}: {field_name}")
            env_name, caster = mapping[field_name]
            coerced = self._coerce(str(value), caster)
            rendered = "" if coerced is None else str(value)
            pattern = re.compile(rf"^\s*{re.escape(env_name)}=")
            replaced = False
            for index, line in enumerate(lines):
                if pattern.match(line):
                    lines[index] = f"{env_name}={rendered}"
                    replaced = True
                    break
            if not replaced:
                lines.append(f"{env_name}={rendered}")
            updated_fields[field_name] = coerced

        env_local.parent.mkdir(parents=True, exist_ok=True)
        env_local.write_text("\n".join(lines) + ("\n" if lines else ""), encoding="utf-8")
        return {
            "status": "ok",
            "scope": normalized,
            "updated": updated_fields,
            "applied_via": "local_runtime_config_override",
        }

    def resolve_config_scope(self, message: str) -> str:
        lowered = message.lower()
        for scope_name, meta in CONFIG_SCOPES.items():
            if scope_name in lowered or any(alias in lowered for alias in meta["aliases"]):
                return scope_name
        raise ValueError("Could not determine which config domain to use.")

    def _headers(self, require_admin_token: bool = False) -> dict[str, str]:
        headers: dict[str, str] = {}
        if self._access_token:
            headers["Authorization"] = f"Bearer {self._access_token}"
        if require_admin_token and "Authorization" not in headers:
            raise ValueError("Admin access token is required for document inspection workflows.")
        return headers

    def _fetch_documents(self) -> list[dict[str, Any]]:
        with self._client() as client:
            response = client.get(
                f"{self._settings.ingestion_base_url.rstrip('/')}/ingestion/documents",
                headers=self._headers(require_admin_token=True),
            )
            response.raise_for_status()
            payload = response.json()
        return payload.get("documents", []) if isinstance(payload, dict) else []

    def get_ingestion_status(self) -> dict[str, Any]:
        documents = self._fetch_documents()
        by_status: dict[str, int] = {}
        embedded_count = 0
        validated_not_embedded = 0
        for item in documents:
            if not isinstance(item, dict):
                continue
            status = str(item.get("status") or "unknown")
            by_status[status] = by_status.get(status, 0) + 1
            if item.get("embedded") is True:
                embedded_count += 1
            if status == "validated" and item.get("embedded") is not True:
                validated_not_embedded += 1

        return {
            "status": "ok",
            "total_documents": len(documents),
            "embedded_documents": embedded_count,
            "validated_not_embedded": validated_not_embedded,
            "status_counts": by_status,
        }

    def list_loaded_documents(self) -> dict[str, Any]:
        documents = self._fetch_documents()
        return {"status": "ok", "documents": documents}

    def list_evaluation_reports(self) -> dict[str, Any]:
        with self._client() as client:
            response = client.get(f"{self._settings.generation_base_url.rstrip('/')}/generation/evaluations")
            response.raise_for_status()
            return response.json()

    def run_evaluation(self, dataset_path: str = "evals/sample_eval_dataset.json") -> dict[str, Any]:
        with self._client() as client:
            response = client.post(
                f"{self._settings.generation_base_url.rstrip('/')}/generation/evaluations/run",
                json={"dataset_path": dataset_path},
            )
            response.raise_for_status()
            return response.json()

    def compare_evaluation_reports(self, baseline_report_id: str, candidate_report_id: str) -> dict[str, Any]:
        with self._client() as client:
            response = client.post(
                f"{self._settings.generation_base_url.rstrip('/')}/generation/evaluations/compare",
                json={
                    "baseline_report_id": baseline_report_id,
                    "candidate_report_id": candidate_report_id,
                },
            )
            response.raise_for_status()
            return response.json()

    def remove_document_chunks(self, document_id: str) -> dict[str, Any]:
        with self._client() as client:
            response = client.post(
                f"{self._settings.embedding_base_url.rstrip('/')}/embedding/remove-document",
                json={"document_id": document_id},
            )
            if response.status_code not in {200, 400, 404}:
                response.raise_for_status()
            return response.json() if response.headers.get("content-type", "").startswith("application/json") else {"status": "ok"}

    def delete_document_record(self, document_id: str) -> dict[str, Any]:
        with self._client() as client:
            response = client.delete(
                f"{self._settings.ingestion_base_url.rstrip('/')}/ingestion/documents/{document_id}",
                headers=self._headers(require_admin_token=True),
            )
            response.raise_for_status()
            return response.json()

    def delete_document_completely(self, document_id: str) -> dict[str, Any]:
        remove_result = self.remove_document_chunks(document_id)
        delete_result = self.delete_document_record(document_id)
        return {
            "status": "ok",
            "remove_result": remove_result,
            "delete_result": delete_result,
        }

    def reindex_document(self, document_id: str) -> dict[str, Any]:
        with self._client() as client:
            remove_response = client.post(
                f"{self._settings.embedding_base_url.rstrip('/')}/embedding/remove-document",
                json={"document_id": document_id},
            )
            if remove_response.status_code not in {200, 400, 404}:
                remove_response.raise_for_status()

            index_response = client.post(
                f"{self._settings.embedding_base_url.rstrip('/')}/embedding/index-document",
                json={"document_id": document_id, "skip_if_embedded": False},
            )
            index_response.raise_for_status()

        remove_payload = (
            remove_response.json() if remove_response.headers.get("content-type", "").startswith("application/json") else None
        )
        return {
            "status": "ok",
            "remove_result": remove_payload,
            "index_result": index_response.json(),
        }

    def reindex_validated_documents(self) -> dict[str, Any]:
        documents_payload = self.list_loaded_documents()
        documents = documents_payload.get("documents", []) if isinstance(documents_payload, dict) else []
        candidates = [
            item for item in documents
            if isinstance(item, dict) and str(item.get("status") or "") == "validated"
        ]

        results = []
        for item in candidates:
            document_id = str(item.get("id") or "")
            if not document_id:
                continue
            results.append(self.reindex_document(document_id))

        return {
            "status": "ok",
            "validated_count": len(candidates),
            "reindexed_count": len(results),
            "results": results,
        }

    def find_document(self, query: str) -> dict[str, Any] | None:
        normalized = query.strip().lower()
        if not normalized:
            return None
        documents = self._fetch_documents()

        def score(item: dict[str, Any]) -> tuple[int, int]:
            fields = [
                str(item.get("id") or ""),
                str(item.get("original_name") or ""),
                str(item.get("storage_path") or ""),
            ]
            best = 0
            for field in fields:
                lowered = field.lower()
                if lowered == normalized:
                    best = max(best, 100)
                elif normalized and normalized in lowered:
                    best = max(best, 50)
            embedded = 1 if item.get("embedded") else 0
            return (best, embedded)

        ranked = sorted(
            (item for item in documents if isinstance(item, dict)),
            key=score,
            reverse=True,
        )
        if not ranked or score(ranked[0])[0] == 0:
            return None
        return ranked[0]

    def resolve_report_pair(self, message: str) -> tuple[str, str] | None:
        reports_payload = self.list_evaluation_reports()
        reports = reports_payload.get("reports", []) if isinstance(reports_payload, dict) else []
        report_ids = [str(item.get("report_id") or "") for item in reports if isinstance(item, dict)]
        normalized_message = message.lower()

        explicit = [report_id for report_id in report_ids if report_id and report_id.lower() in normalized_message]
        if len(explicit) >= 2:
            return explicit[0], explicit[1]

        if any(token in normalized_message for token in ["latest", "recent", "newest"]) and len(report_ids) >= 2:
            return report_ids[1], report_ids[0]

        if len(report_ids) >= 2 and ("compare" in normalized_message and "evaluation" in normalized_message):
            return report_ids[1], report_ids[0]

        return None

    def execute_pending_action(self, pending_action: dict) -> dict[str, Any]:
        tool_name = str(pending_action.get("tool") or "").strip()
        arguments = pending_action.get("arguments", {})
        if not isinstance(arguments, dict):
            arguments = {}

        if tool_name == "run_evaluation":
            return self.run_evaluation(str(arguments.get("dataset_path") or "evals/sample_eval_dataset.json"))
        if tool_name == "compare_evaluation_reports":
            return self.compare_evaluation_reports(
                str(arguments.get("baseline_report_id") or ""),
                str(arguments.get("candidate_report_id") or ""),
            )
        if tool_name == "reindex_document":
            return self.reindex_document(str(arguments.get("document_id") or ""))
        if tool_name == "reindex_validated_documents":
            return self.reindex_validated_documents()
        if tool_name == "delete_document_completely":
            return self.delete_document_completely(str(arguments.get("document_id") or ""))
        if tool_name == "update_repo_config":
            return self.update_repo_config(
                str(arguments.get("service_name") or ""),
                arguments.get("changes", {}),
            )
        raise ValueError(f"Unsupported pending action tool: {tool_name}")


def build_tools(toolbox: AdminToolbox, include_mutations: bool = True) -> list:
    @tool
    def get_ingestion_status() -> dict[str, Any]:
        """Return the current document ingestion summary, including counts by status and embedded totals."""
        return toolbox.get_ingestion_status()

    @tool
    def list_loaded_documents() -> dict[str, Any]:
        """Return the current documents known to ingestion, including status and embedded flags."""
        return toolbox.list_loaded_documents()

    @tool
    def list_evaluation_reports() -> dict[str, Any]:
        """Return saved evaluation reports that the admin can review or compare."""
        return toolbox.list_evaluation_reports()

    @tool
    def run_evaluation(dataset_path: str = "evals/sample_eval_dataset.json") -> dict[str, Any]:
        """Run a Ragas evaluation using the provided dataset path and return the saved report summary."""
        return toolbox.run_evaluation(dataset_path)

    @tool
    def compare_evaluation_reports(baseline_report_id: str, candidate_report_id: str) -> dict[str, Any]:
        """Compare two saved evaluation reports and return metric deltas."""
        return toolbox.compare_evaluation_reports(baseline_report_id, candidate_report_id)

    @tool
    def reindex_document(document_id: str) -> dict[str, Any]:
        """Remove existing vectors for a document and rebuild its embeddings from the latest source file."""
        return toolbox.reindex_document(document_id)

    @tool
    def reindex_validated_documents() -> dict[str, Any]:
        """Rebuild embeddings for every validated document currently tracked by ingestion."""
        return toolbox.reindex_validated_documents()

    @tool
    def get_repo_config(service_name: str) -> dict[str, Any]:
        """Return repo-backed config values for a supported service domain such as preprocessing, retrieval, embedding, or generation."""
        return toolbox.get_repo_config(service_name)

    @tool
    def update_repo_config(service_name: str, changes: dict[str, Any]) -> dict[str, Any]:
        """Update supported repo config values by writing overrides into .env.local. Use only for confirmed admin changes."""
        return toolbox.update_repo_config(service_name, changes)

    tools = [
        get_ingestion_status,
        list_loaded_documents,
        list_evaluation_reports,
        run_evaluation,
        compare_evaluation_reports,
        reindex_document,
        reindex_validated_documents,
        get_repo_config,
    ]

    if include_mutations:
        @tool
        def delete_document_completely(document_id: str) -> dict[str, Any]:
            """Delete a document record and best-effort remove its indexed vectors."""
            return toolbox.delete_document_completely(document_id)

        tools.append(delete_document_completely)
        tools.append(update_repo_config)

    return tools


FOLLOW_UP_PATTERNS = {
    "continue",
    "go on",
    "tell me more",
    "explain more",
    "give me the information",
    "give me the info",
    "more details",
    "continuez",
    "explique davantage",
    "donne-moi l'information",
    "donne moi l'information",
    "plus de détails",
    "continue en arabe",
    "واصل",
    "زيد",
    "اعطني المعلومات",
}


def is_generic_follow_up(message: str) -> bool:
    lowered = re.sub(r"\s+", " ", message.strip().lower())
    return lowered in FOLLOW_UP_PATTERNS
