from __future__ import annotations

import re
from pathlib import Path
from typing import Any

import httpx
from langchain_core.tools import tool

from app.config import Settings


def _normalize_name(text: str) -> str:
    """Lowercase and collapse separators (space/hyphen/underscore/dot) to spaces
    so document names match regardless of how the user types them."""
    return re.sub(r"[\s\-_.]+", " ", str(text or "").lower()).strip()


def _name_tokens(query: str) -> list[str]:
    return [tok for tok in _normalize_name(query).split() if tok]


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

class AdminToolbox:
    def __init__(self, settings: Settings, access_token: str | None = None) -> None:
        self._settings = settings
        self._access_token = access_token

    def with_access_token(self, access_token: str | None) -> "AdminToolbox":
        return AdminToolbox(self._settings, access_token=access_token)

    def _client(self, timeout_seconds: float | None = None) -> httpx.Client:
        return httpx.Client(
            timeout=timeout_seconds
            if timeout_seconds is not None
            else self._settings.admin_http_timeout_seconds
        )

    def _raise_generation_endpoint_not_found(self, action: str, endpoint: str, exc: httpx.HTTPStatusError) -> None:
        raise ValueError(
            f"Could not {action} because generation-service returned 404 for '{endpoint}'. "
            "This usually means the running generation-service is out of date and needs to be rebuilt/restarted "
            "with the evaluation routes enabled."
        ) from exc

    def _generation_base_url_candidates(self) -> list[str]:
        configured = self._settings.generation_base_url.rstrip("/")
        candidates = [configured]
        for candidate in ("http://localhost:8004", "http://host.docker.internal:8004"):
            if candidate not in candidates:
                candidates.append(candidate)
        return candidates

    def _generation_endpoint_exists(self, client: httpx.Client, base_url: str, endpoint: str) -> bool:
        try:
            response = client.get(f"{base_url}/openapi.json")
            response.raise_for_status()
            payload = response.json()
        except (httpx.HTTPError, ValueError):
            return False

        paths = payload.get("paths", {}) if isinstance(payload, dict) else {}
        return isinstance(paths, dict) and endpoint in paths

    @staticmethod
    def _http_error_detail(response: httpx.Response) -> str:
        detail = ""
        try:
            payload = response.json()
            if isinstance(payload, dict):
                raw = payload.get("detail")
                detail = raw if isinstance(raw, str) else (str(raw) if raw else "")
        except ValueError:
            detail = ""
        if not detail:
            text = (response.text or "").strip()
            detail = text[:300] if text else f"HTTP {response.status_code}"
        return detail

    def _request_generation_json(
        self,
        method: str,
        endpoint: str,
        *,
        action: str,
        json_body: dict[str, Any] | None = None,
        timeout_seconds: float | None = None,
    ) -> dict[str, Any]:
        last_missing_endpoint_error: httpx.HTTPStatusError | None = None

        for base_url in self._generation_base_url_candidates():
            with self._client(timeout_seconds=timeout_seconds) as client:
                response = client.request(method, f"{base_url}{endpoint}", json=json_body)
                try:
                    response.raise_for_status()
                    return response.json()
                except httpx.HTTPStatusError as exc:
                    # A 404 on a route the service does not expose means we should
                    # try the next base URL candidate (service may be out of date).
                    if response.status_code == 404 and not self._generation_endpoint_exists(
                        client, base_url, endpoint
                    ):
                        last_missing_endpoint_error = exc
                        continue
                    # Any other error (400/422/500, or a real 404 resource miss) is a
                    # genuine failure: surface the backend detail in plain language
                    # instead of letting a raw HTTPStatusError become an opaque 500.
                    raise ValueError(
                        f"Could not {action}: {self._http_error_detail(response)}"
                    ) from exc

        if last_missing_endpoint_error is not None:
            self._raise_generation_endpoint_not_found(action, endpoint, last_missing_endpoint_error)
        raise RuntimeError(f"Failed to call generation-service endpoint: {endpoint}")

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

    def _get_preprocessing_chunking_strategies(self) -> dict[str, Any]:
        with self._client() as client:
            response = client.get(
                f"{self._settings.preprocessing_base_url.rstrip('/')}/preprocessing/chunking-strategies"
            )
            response.raise_for_status()
            return response.json()

    def _get_retrieval_config(self) -> dict[str, Any]:
        with self._client() as client:
            response = client.get(f"{self._settings.retrieval_base_url.rstrip('/')}/retrieval/config")
            response.raise_for_status()
            return response.json()

    def _update_retrieval_config(self, changes: dict[str, Any]) -> dict[str, Any]:
        payload = dict(changes)
        if "ranker" in payload and "default_ranker_type" not in payload:
            payload["default_ranker_type"] = payload.pop("ranker")
        with self._client() as client:
            response = client.put(
                f"{self._settings.retrieval_base_url.rstrip('/')}/retrieval/config",
                json=payload,
            )
            response.raise_for_status()
            return response.json()

    def _get_retrieval_rerankers(self) -> dict[str, Any]:
        with self._client() as client:
            response = client.get(f"{self._settings.retrieval_base_url.rstrip('/')}/retrieval/rerankers")
            response.raise_for_status()
            return response.json()

    def get_capabilities(self) -> dict[str, Any]:
        return {
            "services": {
                scope_name: {
                    "config_keys": sorted(meta["keys"].keys()),
                    "aliases": sorted(meta["aliases"]),
                    "read_tool": "get_repo_config",
                    "update_tool": "update_repo_config",
                }
                for scope_name, meta in CONFIG_SCOPES.items()
            },
            "subjects": {
                "chunking": {
                    "service_name": "preprocessing",
                    "read_tool": "get_chunking_methods",
                    "explain_tool": "get_chunking_methods",
                    "enum_values": ["late", "overlap", "semantic"],
                },
                "reranking": {
                    "service_name": "retrieval",
                    "read_tool": "get_reranking_methods",
                    "explain_tool": "get_reranking_methods",
                    "enum_values": ["cross_encoder", "llm_batch", "none"],
                },
                "retrieval_config": {
                    "service_name": "retrieval",
                    "read_tool": "get_repo_config",
                    "update_tool": "update_repo_config",
                },
                "preprocessing_config": {
                    "service_name": "preprocessing",
                    "read_tool": "get_repo_config",
                    "update_tool": "update_repo_config",
                },
                "embedding_config": {
                    "service_name": "embedding",
                    "read_tool": "get_repo_config",
                    "update_tool": "update_repo_config",
                },
                "generation_config": {
                    "service_name": "generation",
                    "read_tool": "get_repo_config",
                    "update_tool": "update_repo_config",
                },
            },
            "workflow_tools": [
                "delete_document_completely",
                "reindex_document",
                "reindex_validated_documents",
                "bulk_delete_by_filter",
                "bulk_reindex_by_filter",
                "confirm_pending_documents",
                "refuse_pending_documents",
                "run_evaluation",
                "read_evaluation_report",
                "compare_evaluation_reports",
            ],
        }

    def get_repo_config(self, service_name: str) -> dict[str, Any]:
        normalized = self.resolve_config_scope(service_name)
        scope = CONFIG_SCOPES.get(normalized)
        if scope is None:
            raise ValueError(f"Unsupported config scope: {service_name}")

        if normalized == "preprocessing":
            return self._get_preprocessing_config()
        if normalized == "retrieval":
            return self._get_retrieval_config()

        values, sources = self._read_env_map()
        config: dict[str, Any] = {}
        source_map: dict[str, str] = {}
        for field_name, (env_name, caster) in scope["keys"].items():
            raw = values.get(env_name, "")
            config[field_name] = self._coerce(raw, caster) if raw != "" else None
            source_map[field_name] = sources.get(env_name, "unset")
        return {"status": "ok", "scope": normalized, "config": config, "sources": source_map}

    def get_chunking_methods(self) -> dict[str, Any]:
        return self._get_preprocessing_chunking_strategies()

    def get_reranking_methods(self) -> dict[str, Any]:
        return self._get_retrieval_rerankers()

    def update_repo_config(self, service_name: str, changes: dict[str, Any]) -> dict[str, Any]:
        normalized = self.resolve_config_scope(service_name)
        scope = CONFIG_SCOPES.get(normalized)
        if scope is None:
            raise ValueError(f"Unsupported config scope: {service_name}")
        if not isinstance(changes, dict) or not changes:
            raise ValueError("changes must contain at least one supported field")

        if normalized == "preprocessing":
            return self._update_preprocessing_config(changes)
        if normalized == "retrieval":
            return self._update_retrieval_config(changes)

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
        return self._request_generation_json(
            "GET",
            "/generation/evaluations",
            action="list evaluation reports",
        )

    def read_evaluation_report(self, report_id: str = "latest") -> dict[str, Any]:
        normalized = str(report_id or "latest").strip()
        if not normalized or normalized == "latest":
            reports_payload = self.list_evaluation_reports()
            reports = reports_payload.get("reports", []) if isinstance(reports_payload, dict) else []
            latest = reports[0] if reports and isinstance(reports[0], dict) else None
            if latest is None:
                return {"status": "ok", "report": None}
            normalized = str(latest.get("report_id") or "").strip()
            if not normalized:
                return {"status": "ok", "report": None}

        return self._request_generation_json(
            "GET",
            f"/generation/evaluations/{normalized}",
            action="read evaluation report",
        )

    def run_evaluation(self, dataset_path: str = "evals/sample_eval_dataset.json") -> dict[str, Any]:
        return self._request_generation_json(
            "POST",
            "/generation/evaluations/run",
            action="run the evaluation",
            json_body={"dataset_path": dataset_path},
            timeout_seconds=self._settings.admin_evaluation_timeout_seconds,
        )

    def compare_evaluation_reports(self, baseline_report_id: str, candidate_report_id: str) -> dict[str, Any]:
        return self._request_generation_json(
            "POST",
            "/generation/evaluations/compare",
            action="compare evaluation reports",
            json_body={
                "baseline_report_id": baseline_report_id,
                "candidate_report_id": candidate_report_id,
            },
        )

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
        if not document_id or not document_id.strip():
            return {
                "status": "error",
                "error": "document_id is required but was empty or missing. "
                         "Use find_document or list_loaded_documents to resolve a valid ID.",
            }
        remove_result = self.remove_document_chunks(document_id)
        delete_result = self.delete_document_record(document_id)
        return {
            "status": "ok",
            "remove_result": remove_result,
            "delete_result": delete_result,
        }

    def reindex_document(self, document_id: str) -> dict[str, Any]:
        if not document_id or not document_id.strip():
            return {
                "status": "error",
                "error": "document_id is required but was empty or missing. "
                         "Use find_document or list_loaded_documents to resolve a valid ID.",
            }
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

        results: list[dict[str, Any]] = []
        succeeded = 0
        failed = 0
        for item in candidates:
            document_id = str(item.get("id") or "")
            if not document_id:
                continue
            name = str(item.get("original_name") or document_id)
            # Isolate each document so a single slow/failed reindex (e.g. a large
            # PDF exceeding the HTTP timeout) does not abort the whole batch and
            # bubble up as an opaque 500. Partial progress is reported instead.
            try:
                result = self.reindex_document(document_id)
            except (httpx.HTTPError, ValueError, RuntimeError) as exc:
                result = {"status": "error", "error": str(exc)}
            is_error = isinstance(result, dict) and str(result.get("status") or "") == "error"
            if is_error:
                failed += 1
            else:
                succeeded += 1
            results.append(
                {"document_id": document_id, "original_name": name, "result": result}
            )

        if failed == 0:
            status = "ok"
        elif succeeded == 0:
            status = "error"
        else:
            status = "partial"
        return {
            "status": status,
            "validated_count": len(candidates),
            "reindexed_count": succeeded,
            "failed_count": failed,
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

    def find_documents_by_filter(
        self,
        *,
        name_contains: str | None = None,
        status: str | None = None,
        embedded: bool | None = None,
    ) -> list[dict[str, Any]]:
        """Return all documents matching the given filters."""
        documents = self._fetch_documents()
        query_tokens = _name_tokens(name_contains) if name_contains else []
        results: list[dict[str, Any]] = []
        for item in documents:
            if not isinstance(item, dict):
                continue
            if query_tokens:
                # Token-based, separator-insensitive match so a non-technical user
                # can type a partial name with spaces and no extension (e.g.
                # "icc policy primer") and still match "icc-policy-primer-....pdf".
                haystack = _normalize_name(
                    f"{item.get('original_name') or ''} {item.get('storage_path') or ''}"
                )
                if not all(tok in haystack for tok in query_tokens):
                    continue
            if status is not None:
                if str(item.get("status") or "").lower() != status.strip().lower():
                    continue
            if embedded is not None:
                if bool(item.get("embedded")) != embedded:
                    continue
            results.append(item)
        return results

    def smart_delete(self, query: str) -> dict[str, Any]:
        """Resolve a document by name/query and delete it.

        Returns a status dict indicating whether the document was found,
        whether multiple matches require disambiguation, or the delete result.
        """
        if not query or not query.strip():
            return {"status": "error", "error": "A document name or query is required."}

        candidates = self.find_documents_by_filter(name_contains=query)
        if not candidates:
            single = self.find_document(query)
            if single is not None:
                candidates = [single]

        if not candidates:
            return {
                "status": "not_found",
                "error": f"No documents found matching '{query}'.",
                "query": query,
            }

        if len(candidates) == 1:
            doc = candidates[0]
            doc_id = str(doc.get("id") or "")
            result = self.delete_document_completely(doc_id)
            return {
                "status": "ok",
                "resolved_document": {
                    "id": doc_id,
                    "original_name": str(doc.get("original_name") or ""),
                },
                "delete_result": result,
            }

        return {
            "status": "multiple_matches",
            "error": f"Found {len(candidates)} documents matching '{query}'. Please refine your query or specify a document ID.",
            "query": query,
            "candidates": [
                {
                    "id": str(c.get("id") or ""),
                    "original_name": str(c.get("original_name") or ""),
                    "status": str(c.get("status") or ""),
                }
                for c in candidates
            ],
        }

    def smart_reindex(self, query: str) -> dict[str, Any]:
        """Resolve a document by name/query and reindex it."""
        if not query or not query.strip():
            return {"status": "error", "error": "A document name or query is required."}

        candidates = self.find_documents_by_filter(name_contains=query)
        if not candidates:
            single = self.find_document(query)
            if single is not None:
                candidates = [single]

        if not candidates:
            return {
                "status": "not_found",
                "error": f"No documents found matching '{query}'.",
                "query": query,
            }

        if len(candidates) == 1:
            doc = candidates[0]
            doc_id = str(doc.get("id") or "")
            result = self.reindex_document(doc_id)
            return {
                "status": "ok",
                "resolved_document": {
                    "id": doc_id,
                    "original_name": str(doc.get("original_name") or ""),
                },
                "reindex_result": result,
            }

        return {
            "status": "multiple_matches",
            "error": f"Found {len(candidates)} documents matching '{query}'. Please refine your query or specify a document ID.",
            "query": query,
            "candidates": [
                {
                    "id": str(c.get("id") or ""),
                    "original_name": str(c.get("original_name") or ""),
                    "status": str(c.get("status") or ""),
                }
                for c in candidates
            ],
        }

    def _bulk_candidates(
        self,
        document_ids: list[str] | None,
        name_contains: str | None,
        status: str | None,
        embedded: bool | None,
    ) -> list[dict[str, Any]]:
        if document_ids:
            documents = self._fetch_documents()
            by_id = {str(d.get("id") or ""): d for d in documents if isinstance(d, dict)}
            resolved: list[dict[str, Any]] = []
            for raw in document_ids:
                doc_id = str(raw or "").strip()
                if doc_id in by_id:
                    resolved.append(by_id[doc_id])
                elif doc_id:
                    resolved.append({"id": doc_id})
            return resolved
        return self.find_documents_by_filter(
            name_contains=name_contains, status=status, embedded=embedded,
        )

    def bulk_delete_by_filter(
        self,
        *,
        document_ids: list[str] | None = None,
        name_contains: str | None = None,
        status: str | None = None,
        embedded: bool | None = None,
    ) -> dict[str, Any]:
        """Delete all documents matching the given ids or filters."""
        candidates = self._bulk_candidates(document_ids, name_contains, status, embedded)
        if not candidates:
            return {"status": "not_found", "deleted_count": 0, "error": "No documents matched the criteria."}

        results = []
        deleted = 0
        failed = 0
        for doc in candidates:
            doc_id = str(doc.get("id") or "")
            if not doc_id:
                continue
            try:
                result = self.delete_document_completely(doc_id)
            except (httpx.HTTPError, ValueError, RuntimeError) as exc:
                result = {"status": "error", "error": str(exc)}
            if isinstance(result, dict) and str(result.get("status") or "") == "error":
                failed += 1
            else:
                deleted += 1
            results.append({
                "document_id": doc_id,
                "original_name": str(doc.get("original_name") or ""),
                "result": result,
            })
        status_label = "ok" if failed == 0 else ("partial" if deleted else "error")
        return {"status": status_label, "deleted_count": deleted, "failed_count": failed, "results": results}

    def bulk_reindex_by_filter(
        self,
        *,
        document_ids: list[str] | None = None,
        name_contains: str | None = None,
        status: str | None = None,
        embedded: bool | None = None,
    ) -> dict[str, Any]:
        """Reindex all documents matching the given ids or filters."""
        candidates = self._bulk_candidates(document_ids, name_contains, status, embedded)
        if not candidates:
            return {"status": "not_found", "reindexed_count": 0, "error": "No documents matched the criteria."}

        results = []
        reindexed = 0
        failed = 0
        for doc in candidates:
            doc_id = str(doc.get("id") or "")
            if not doc_id:
                continue
            try:
                result = self.reindex_document(doc_id)
            except (httpx.HTTPError, ValueError, RuntimeError) as exc:
                result = {"status": "error", "error": str(exc)}
            if isinstance(result, dict) and str(result.get("status") or "") == "error":
                failed += 1
            else:
                reindexed += 1
            results.append({
                "document_id": doc_id,
                "original_name": str(doc.get("original_name") or ""),
                "result": result,
            })
        status_label = "ok" if failed == 0 else ("partial" if reindexed else "error")
        return {"status": status_label, "reindexed_count": reindexed, "failed_count": failed, "results": results}

    # ------------------------------------------------------------------
    # Pending-document review: confirm (validate + preprocess + embed) or
    # refuse (status change only). Mirrors what the admin UI does on the
    # documents page.
    # ------------------------------------------------------------------
    def _update_document_status(self, document_id: str, target_status: str) -> dict[str, Any]:
        with self._client() as client:
            response = client.post(
                f"{self._settings.ingestion_base_url.rstrip('/')}/ingestion/documents/{document_id}/status",
                json={"target_status": target_status},
                headers=self._headers(require_admin_token=True),
            )
            response.raise_for_status()
            return response.json()

    def _index_document(self, document_id: str, skip_if_embedded: bool = True) -> dict[str, Any]:
        with self._client() as client:
            response = client.post(
                f"{self._settings.embedding_base_url.rstrip('/')}/embedding/index-document",
                json={"document_id": document_id, "skip_if_embedded": skip_if_embedded},
            )
            response.raise_for_status()
            return response.json()

    def list_pending_documents(self) -> dict[str, Any]:
        pending = self.find_documents_by_filter(status="pending")
        return {"status": "ok", "count": len(pending), "documents": pending}

    def confirm_document(self, document_id: str) -> dict[str, Any]:
        """Validate a document then run its preprocessing + embedding."""
        if not document_id or not document_id.strip():
            return {
                "status": "error",
                "error": "document_id is required but was empty or missing.",
            }
        status_result = self._update_document_status(document_id, "validated")
        index_result = self._index_document(document_id, skip_if_embedded=True)
        return {
            "status": "ok",
            "document_id": document_id,
            "status_result": status_result,
            "index_result": index_result,
        }

    def refuse_document(self, document_id: str) -> dict[str, Any]:
        """Mark a document as rejected without embedding it."""
        if not document_id or not document_id.strip():
            return {
                "status": "error",
                "error": "document_id is required but was empty or missing.",
            }
        status_result = self._update_document_status(document_id, "rejected")
        return {"status": "ok", "document_id": document_id, "status_result": status_result}

    def _resolve_document_targets(
        self,
        document_ids: list[str] | None,
        query: str | None,
        default_status: str | None,
    ) -> list[dict[str, Any]]:
        """Resolve which documents an action applies to.

        Priority: explicit ids -> name/category query -> all documents in
        `default_status` (e.g. every pending document when nothing else given).
        """
        documents = self._fetch_documents()
        by_id = {str(d.get("id") or ""): d for d in documents if isinstance(d, dict)}

        if document_ids:
            resolved: list[dict[str, Any]] = []
            for raw in document_ids:
                doc_id = str(raw or "").strip()
                if doc_id and doc_id in by_id:
                    resolved.append(by_id[doc_id])
                elif doc_id:
                    resolved.append({"id": doc_id})
            return resolved

        if query and query.strip():
            matches = self.find_documents_by_filter(name_contains=query.strip())
            if default_status:
                # Scope to the actionable status so e.g. confirming a pending file
                # never matches an already-validated copy with the same name.
                matches = [
                    d for d in matches
                    if isinstance(d, dict) and str(d.get("status") or "") == default_status
                ]
            return matches

        if default_status:
            return [d for d in documents if isinstance(d, dict) and str(d.get("status") or "") == default_status]
        return []

    def confirm_pending_documents(
        self,
        document_ids: list[str] | None = None,
        query: str | None = None,
    ) -> dict[str, Any]:
        targets = self._resolve_document_targets(document_ids, query, default_status="pending")
        if not targets:
            return {"status": "not_found", "confirmed_count": 0, "error": "No matching documents to confirm."}

        results: list[dict[str, Any]] = []
        confirmed = 0
        failed = 0
        for doc in targets:
            doc_id = str(doc.get("id") or "")
            if not doc_id:
                continue
            name = str(doc.get("original_name") or doc_id)
            try:
                result = self.confirm_document(doc_id)
            except (httpx.HTTPError, ValueError, RuntimeError) as exc:
                result = {"status": "error", "error": str(exc)}
            if isinstance(result, dict) and str(result.get("status") or "") == "error":
                failed += 1
            else:
                confirmed += 1
            results.append({"document_id": doc_id, "original_name": name, "result": result})

        status = "ok" if failed == 0 else ("partial" if confirmed else "error")
        return {
            "status": status,
            "confirmed_count": confirmed,
            "failed_count": failed,
            "results": results,
        }

    def refuse_pending_documents(
        self,
        document_ids: list[str] | None = None,
        query: str | None = None,
    ) -> dict[str, Any]:
        targets = self._resolve_document_targets(document_ids, query, default_status="pending")
        if not targets:
            return {"status": "not_found", "refused_count": 0, "error": "No matching documents to refuse."}

        results: list[dict[str, Any]] = []
        refused = 0
        failed = 0
        for doc in targets:
            doc_id = str(doc.get("id") or "")
            if not doc_id:
                continue
            name = str(doc.get("original_name") or doc_id)
            try:
                result = self.refuse_document(doc_id)
            except (httpx.HTTPError, ValueError, RuntimeError) as exc:
                result = {"status": "error", "error": str(exc)}
            if isinstance(result, dict) and str(result.get("status") or "") == "error":
                failed += 1
            else:
                refused += 1
            results.append({"document_id": doc_id, "original_name": name, "result": result})

        status = "ok" if failed == 0 else ("partial" if refused else "error")
        return {
            "status": status,
            "refused_count": refused,
            "failed_count": failed,
            "results": results,
        }

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

    def _recent_report_pair(self) -> tuple[str, str] | None:
        """Return (baseline, candidate) = (second-newest, newest) report ids."""
        reports_payload = self.list_evaluation_reports()
        reports = reports_payload.get("reports", []) if isinstance(reports_payload, dict) else []
        report_ids = [
            str(item.get("report_id") or "")
            for item in reports
            if isinstance(item, dict) and item.get("report_id")
        ]
        if len(report_ids) >= 2:
            return report_ids[1], report_ids[0]
        return None

    def _resolve_compare_ids(self, arguments: dict) -> tuple[str, str]:
        """Accept the many key spellings a planner/LLM may emit and resolve them.

        Falls back to the two most recent reports when ids are missing so a
        request like 'compare the two latest reports' works without explicit ids.
        """
        def pick(*keys: str) -> str:
            for key in keys:
                value = arguments.get(key)
                if isinstance(value, str) and value.strip():
                    return value.strip()
            return ""

        baseline = pick("baseline_report_id", "baseline", "report1", "first", "from", "report_a")
        candidate = pick("candidate_report_id", "candidate", "report2", "second", "to", "report_b")

        if not baseline or not candidate:
            reports = arguments.get("reports") or arguments.get("report_ids")
            if isinstance(reports, list) and len(reports) >= 2:
                baseline = baseline or str(reports[0])
                candidate = candidate or str(reports[1])

        if not baseline or not candidate:
            pair = self._recent_report_pair()
            if pair is not None:
                baseline = baseline or pair[0]
                candidate = candidate or pair[1]

        return baseline, candidate

    @staticmethod
    def _document_query_from_arguments(arguments: dict) -> str:
        """Extract a name/category query from whatever key a planner emitted."""
        for key in (
            "document_name",
            "document_query",
            "document_type",
            "name",
            "query",
            "file",
            "filename",
            "title",
            "document",
            "category",
            "keyword",
        ):
            value = arguments.get(key)
            if isinstance(value, str) and value.strip():
                return value.strip()
        return ""

    @staticmethod
    def _document_ids_from_arguments(arguments: dict) -> list[str] | None:
        """Collect explicit document ids from list or single-id arguments."""
        for key in ("document_ids", "ids", "documents"):
            value = arguments.get(key)
            if isinstance(value, list) and value:
                ids = [str(item).strip() for item in value if str(item).strip()]
                if ids:
                    return ids
        single = str(arguments.get("document_id") or "").strip()
        if single:
            return [single]
        return None

    def execute_pending_action(self, pending_action: dict) -> dict[str, Any]:
        tool_name = str(pending_action.get("tool") or "").strip()
        try:
            return self._dispatch_pending_action(tool_name, pending_action)
        except (ValueError, RuntimeError, httpx.HTTPError) as exc:
            # Never let a tool failure bubble out as an opaque HTTP 500. Return a
            # structured error the summarizer can relay to the admin in plain text.
            return {"status": "error", "tool": tool_name, "error": str(exc)}

    def _dispatch_pending_action(self, tool_name: str, pending_action: dict) -> dict[str, Any]:
        arguments = pending_action.get("arguments", {})
        if not isinstance(arguments, dict):
            arguments = {}

        if tool_name == "compound_action":
            steps = pending_action.get("steps", [])
            results = []
            if not isinstance(steps, list):
                steps = []
            for step in steps:
                if not isinstance(step, dict):
                    continue
                results.append(
                    {
                        "tool": str(step.get("tool") or ""),
                        "result": self.execute_pending_action(
                            {
                                "tool": str(step.get("tool") or ""),
                                "arguments": step.get("arguments", {}) if isinstance(step.get("arguments"), dict) else {},
                            }
                        ),
                    }
                )
            return {"status": "ok", "results": results}

        if tool_name == "run_evaluation":
            dataset = str(
                arguments.get("dataset_path") or arguments.get("dataset") or ""
            ).strip()
            if not dataset.endswith(".json"):
                dataset = "evals/sample_eval_dataset.json"
            return self.run_evaluation(dataset)
        if tool_name == "read_evaluation_report":
            return self.read_evaluation_report(str(arguments.get("report_id") or "latest"))
        if tool_name == "compare_evaluation_reports":
            baseline, candidate = self._resolve_compare_ids(arguments)
            if not baseline or not candidate:
                return {
                    "status": "error",
                    "tool": tool_name,
                    "error": "Two evaluation report ids are required to compare, and fewer than two reports are available.",
                }
            return self.compare_evaluation_reports(baseline, candidate)
        if tool_name == "reindex_document":
            doc_id = str(arguments.get("document_id") or "").strip()
            if doc_id:
                return self.reindex_document(doc_id)
            query = self._document_query_from_arguments(arguments)
            if query:
                # A name/category may match several documents; reindex is safe and
                # idempotent, so rebuild all matches rather than failing on ambiguity.
                matches = self.find_documents_by_filter(name_contains=query)
                if len(matches) > 1:
                    return self.bulk_reindex_by_filter(name_contains=query)
                return self.smart_reindex(query)
            return self.reindex_document("")
        if tool_name == "reindex_validated_documents":
            return self.reindex_validated_documents()
        if tool_name == "delete_document_completely":
            doc_id = str(arguments.get("document_id") or "").strip()
            if doc_id:
                return self.delete_document_completely(doc_id)
            query = self._document_query_from_arguments(arguments)
            if query:
                # Deletion stays conservative: smart_delete asks for disambiguation
                # when a query matches multiple documents instead of deleting them all.
                return self.smart_delete(query)
            return self.delete_document_completely("")
        if tool_name in {"confirm_pending_documents", "refuse_pending_documents"}:
            document_ids = self._document_ids_from_arguments(arguments)
            query = self._document_query_from_arguments(arguments) or None
            if tool_name == "confirm_pending_documents":
                return self.confirm_pending_documents(document_ids=document_ids, query=query)
            return self.refuse_pending_documents(document_ids=document_ids, query=query)
        if tool_name == "list_pending_documents":
            return self.list_pending_documents()
        if tool_name == "update_repo_config":
            return self.update_repo_config(
                str(arguments.get("service_name") or ""),
                arguments.get("changes", {}),
            )
        if tool_name == "get_repo_config":
            return self.get_repo_config(str(arguments.get("service_name") or ""))
        if tool_name == "get_chunking_methods":
            return self.get_chunking_methods()
        if tool_name == "get_reranking_methods":
            return self.get_reranking_methods()
        if tool_name == "get_ingestion_status":
            return self.get_ingestion_status()
        if tool_name == "list_loaded_documents":
            return self.list_loaded_documents()
        if tool_name == "list_evaluation_reports":
            return self.list_evaluation_reports()
        if tool_name == "find_document":
            return self.find_document(str(arguments.get("query") or "")) or {"status": "not_found"}
        if tool_name == "find_documents_by_filter":
            return {
                "status": "ok",
                "documents": self.find_documents_by_filter(
                    name_contains=arguments.get("name_contains"),
                    status=arguments.get("status"),
                    embedded=arguments.get("embedded"),
                ),
            }
        if tool_name == "smart_delete":
            return self.smart_delete(str(arguments.get("query") or ""))
        if tool_name == "smart_reindex":
            return self.smart_reindex(str(arguments.get("query") or ""))
        if tool_name == "bulk_delete_by_filter":
            return self.bulk_delete_by_filter(
                document_ids=arguments.get("document_ids"),
                name_contains=arguments.get("name_contains"),
                status=arguments.get("status"),
                embedded=arguments.get("embedded"),
            )
        if tool_name == "bulk_reindex_by_filter":
            return self.bulk_reindex_by_filter(
                document_ids=arguments.get("document_ids"),
                name_contains=arguments.get("name_contains"),
                status=arguments.get("status"),
                embedded=arguments.get("embedded"),
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
    def read_evaluation_report(report_id: str = "latest") -> dict[str, Any]:
        """Return one saved evaluation report, including summary metrics and row-level records. Use 'latest' for the newest report."""
        return toolbox.read_evaluation_report(report_id)

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
    def get_reranking_methods() -> dict[str, Any]:
        """Return the available retrieval reranking methods and the current default reranker."""
        return toolbox.get_reranking_methods()

    @tool
    def get_chunking_methods() -> dict[str, Any]:
        """Return the available preprocessing chunking strategies and the current default strategy."""
        return toolbox.get_chunking_methods()

    @tool
    def list_pending_documents() -> dict[str, Any]:
        """Return documents awaiting review (status 'pending') that can be confirmed or refused."""
        return toolbox.list_pending_documents()

    @tool
    def update_repo_config(service_name: str, changes: dict[str, Any]) -> dict[str, Any]:
        """Update supported repo config values by writing overrides into .env.local. Use only for confirmed admin changes."""
        return toolbox.update_repo_config(service_name, changes)

    @tool
    def find_document(query: str) -> dict[str, Any]:
        """Find a document by name, partial name, or ID. Returns the best matching document or None."""
        result = toolbox.find_document(query)
        return result if result is not None else {"status": "not_found", "query": query}

    @tool
    def find_documents_by_filter(
        name_contains: str = "",
        status: str = "",
        embedded: bool | None = None,
    ) -> dict[str, Any]:
        """Find all documents matching the given filters (name substring, status, embedded flag)."""
        docs = toolbox.find_documents_by_filter(
            name_contains=name_contains or None,
            status=status or None,
            embedded=embedded,
        )
        return {"status": "ok", "count": len(docs), "documents": docs}

    @tool
    def smart_delete(query: str) -> dict[str, Any]:
        """Find a document by name and delete it. Resolves name to ID automatically. Returns candidates if ambiguous."""
        return toolbox.smart_delete(query)

    @tool
    def smart_reindex(query: str) -> dict[str, Any]:
        """Find a document by name and reindex it. Resolves name to ID automatically. Returns candidates if ambiguous."""
        return toolbox.smart_reindex(query)

    tools = [
        get_ingestion_status,
        list_loaded_documents,
        list_evaluation_reports,
        read_evaluation_report,
        run_evaluation,
        compare_evaluation_reports,
        reindex_document,
        reindex_validated_documents,
        get_repo_config,
        get_reranking_methods,
        get_chunking_methods,
        list_pending_documents,
        find_document,
        find_documents_by_filter,
        smart_delete,
        smart_reindex,
    ]

    if include_mutations:
        @tool
        def delete_document_completely(document_id: str) -> dict[str, Any]:
            """Delete a document record and best-effort remove its indexed vectors."""
            return toolbox.delete_document_completely(document_id)

        @tool
        def bulk_delete_by_filter(
            name_contains: str = "",
            status: str = "",
            embedded: bool | None = None,
        ) -> dict[str, Any]:
            """Delete all documents matching the given filters (name substring, status, embedded flag)."""
            return toolbox.bulk_delete_by_filter(
                name_contains=name_contains or None,
                status=status or None,
                embedded=embedded,
            )

        @tool
        def bulk_reindex_by_filter(
            name_contains: str = "",
            status: str = "",
            embedded: bool | None = None,
        ) -> dict[str, Any]:
            """Reindex all documents matching the given filters (name substring, status, embedded flag)."""
            return toolbox.bulk_reindex_by_filter(
                name_contains=name_contains or None,
                status=status or None,
                embedded=embedded,
            )

        @tool
        def confirm_pending_documents(
            document_ids: list[str] = [],
            query: str = "",
        ) -> dict[str, Any]:
            """Confirm/validate pending documents and run their preprocessing + embedding.

            Provide document_ids for specific documents, a name/category query, or
            neither to confirm every pending document. Works for one or many."""
            return toolbox.confirm_pending_documents(
                document_ids=document_ids or None, query=query or None
            )

        @tool
        def refuse_pending_documents(
            document_ids: list[str] = [],
            query: str = "",
        ) -> dict[str, Any]:
            """Refuse/reject pending documents (status change only, no embedding).

            Provide document_ids for specific documents, a name/category query, or
            neither to refuse every pending document. Works for one or many."""
            return toolbox.refuse_pending_documents(
                document_ids=document_ids or None, query=query or None
            )

        tools.append(delete_document_completely)
        tools.append(update_repo_config)
        tools.append(bulk_delete_by_filter)
        tools.append(bulk_reindex_by_filter)
        tools.append(confirm_pending_documents)
        tools.append(refuse_pending_documents)

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
