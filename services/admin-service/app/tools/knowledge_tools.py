from __future__ import annotations

import fnmatch
from pathlib import Path
import re

from app.clients.embedding_client import EmbeddingClient
from app.clients.ingestion_client import IngestionClient
from app.clients.supabase_documents_client import SupabaseDocumentsClient
from app.models import ToolExecutionResult
from app.tools.base import ToolMetadata


def _discover_target_relative_paths(
    raw_dir: str,
    local_root: str,
    patterns: list[str] | None = None,
) -> list[str]:
    base_dir = Path(raw_dir)
    root_dir = Path(local_root)
    if not base_dir.exists():
        raise ValueError(f"Raw directory not found: {base_dir}")
    if not root_dir.exists():
        raise ValueError(f"Local root directory not found: {root_dir}")

    candidates: set[Path] = set()
    for pattern in patterns or ["*.pdf", "*.txt", "*.md"]:
        candidates.update(path for path in base_dir.rglob(pattern) if path.is_file())

    relative_paths: list[str] = []
    for path in sorted(candidates):
        relative_paths.append(path.resolve().relative_to(root_dir.resolve()).as_posix())
    return relative_paths


_REFERENCE_STOP_WORDS = {
    "a",
    "an",
    "delete",
    "document",
    "file",
    "i",
    "index",
    "me",
    "please",
    "remove",
    "the",
    "to",
    "want",
}


def _tokenize_reference(text: str) -> list[str]:
    return [
        token
        for token in re.findall(r"[a-z0-9]+", text.lower())
        if token and token not in _REFERENCE_STOP_WORDS
    ]


def resolve_document_reference(
    reference: str,
    raw_root: str = "shared/raw_data",
    local_root: str = "shared/raw_data",
) -> dict:
    normalized_reference = str(reference).strip()
    if not normalized_reference or normalized_reference == "UNKNOWN_DOCUMENT":
        return {"status": "unresolved", "target_relative_path": None, "candidates": []}

    raw_root_path = Path(raw_root)
    local_root_path = Path(local_root)
    if not raw_root_path.exists() or not local_root_path.exists():
        return {"status": "unresolved", "target_relative_path": None, "candidates": []}

    direct_candidate = local_root_path / normalized_reference
    if direct_candidate.exists() and direct_candidate.is_file():
        return {
            "status": "resolved",
            "target_relative_path": direct_candidate.resolve().relative_to(local_root_path.resolve()).as_posix(),
            "candidates": [],
        }

    query_tokens = _tokenize_reference(normalized_reference)
    if not query_tokens:
        return {"status": "unresolved", "target_relative_path": None, "candidates": []}

    scored_candidates: list[tuple[int, str]] = []
    for candidate in raw_root_path.rglob("*"):
        if not candidate.is_file():
            continue
        if "supabase" in candidate.parts:
            continue
        relative_path = candidate.resolve().relative_to(local_root_path.resolve()).as_posix()
        candidate_text = relative_path.lower()
        score = 0
        for token in query_tokens:
            if token in candidate_text:
                score += 3
            if any(part.startswith(token) for part in re.findall(r"[a-z0-9]+", candidate_text)):
                score += 1
        if score > 0:
            scored_candidates.append((score, relative_path))

    scored_candidates.sort(key=lambda item: (-item[0], item[1]))
    if not scored_candidates:
        return {"status": "unresolved", "target_relative_path": None, "candidates": []}

    if len(scored_candidates) == 1 or scored_candidates[0][0] > scored_candidates[1][0]:
        return {
            "status": "resolved",
            "target_relative_path": scored_candidates[0][1],
            "candidates": [path for _, path in scored_candidates[:3]],
        }

    return {
        "status": "ambiguous",
        "target_relative_path": None,
        "candidates": [path for _, path in scored_candidates[:5]],
    }


def resolve_synced_supabase_reference(
    reference: str,
    raw_root: str = "shared/raw_data/supabase",
    local_root: str = "shared/raw_data",
) -> dict:
    normalized_reference = str(reference).strip()
    if not normalized_reference or normalized_reference == "UNKNOWN_DOCUMENT":
        return {"status": "unresolved", "target_relative_path": None, "candidates": []}

    raw_root_path = Path(raw_root)
    local_root_path = Path(local_root)
    if not raw_root_path.exists() or not local_root_path.exists():
        return {"status": "unresolved", "target_relative_path": None, "candidates": []}

    query_tokens = _tokenize_reference(normalized_reference)
    if not query_tokens:
        return {"status": "unresolved", "target_relative_path": None, "candidates": []}

    scored_candidates: list[tuple[int, str]] = []
    for candidate in raw_root_path.rglob("*"):
        if not candidate.is_file():
            continue
        relative_path = candidate.resolve().relative_to(local_root_path.resolve()).as_posix()
        candidate_text = relative_path.lower()
        score = 0
        for token in query_tokens:
            if token in candidate_text:
                score += 3
            if any(part.startswith(token) for part in re.findall(r"[a-z0-9]+", candidate_text)):
                score += 1
        if score > 0:
            scored_candidates.append((score, relative_path))

    scored_candidates.sort(key=lambda item: (-item[0], item[1]))
    if not scored_candidates:
        return {"status": "unresolved", "target_relative_path": None, "candidates": []}
    if len(scored_candidates) == 1 or scored_candidates[0][0] > scored_candidates[1][0]:
        return {
            "status": "resolved",
            "target_relative_path": scored_candidates[0][1],
            "candidates": [path for _, path in scored_candidates[:3]],
        }
    return {
        "status": "ambiguous",
        "target_relative_path": None,
        "candidates": [path for _, path in scored_candidates[:5]],
    }


def resolve_supabase_document_reference(reference: str, documents: list[dict]) -> dict:
    normalized_reference = str(reference).strip()
    if not normalized_reference or normalized_reference == "UNKNOWN_DOCUMENT":
        return {"status": "unresolved", "storage_path": None, "candidates": []}

    query_tokens = _tokenize_reference(normalized_reference)
    if not query_tokens:
        return {"status": "unresolved", "storage_path": None, "candidates": []}

    scored_candidates: list[tuple[int, str]] = []
    for document in documents:
        if not isinstance(document, dict):
            continue
        storage_path = str(document.get("storage_path", "")).strip()
        original_name = str(document.get("original_name", "")).strip()
        if not storage_path:
            continue
        candidate_text = f"{storage_path} {original_name}".lower()
        score = 0
        for token in query_tokens:
            if token in candidate_text:
                score += 3
            if any(part.startswith(token) for part in re.findall(r"[a-z0-9]+", candidate_text)):
                score += 1
        if score > 0:
            scored_candidates.append((score, storage_path))

    scored_candidates.sort(key=lambda item: (-item[0], item[1]))
    if not scored_candidates:
        return {"status": "unresolved", "storage_path": None, "candidates": []}
    if len(scored_candidates) == 1 or scored_candidates[0][0] > scored_candidates[1][0]:
        return {
            "status": "resolved",
            "storage_path": scored_candidates[0][1],
            "candidates": [path for _, path in scored_candidates[:3]],
        }
    return {
        "status": "ambiguous",
        "storage_path": None,
        "candidates": [path for _, path in scored_candidates[:5]],
    }


def _normalize_storage_path(target_relative_path: str) -> str:
    return str(target_relative_path).strip().removeprefix("supabase/").lstrip("/")


def _supabase_target_relative_path(storage_path: str) -> str:
    return f"supabase/{str(storage_path).strip().lstrip('/')}"


def _document_matches_patterns(document: dict, patterns: list[str] | None) -> bool:
    if not patterns:
        return True
    storage_path = str(document.get("storage_path", "")).strip()
    original_name = str(document.get("original_name", "")).strip()
    for pattern in patterns:
        if fnmatch.fnmatch(storage_path, pattern) or fnmatch.fnmatch(original_name, pattern):
            return True
    return False


def _validated_documents(
    documents: list[dict],
    patterns: list[str] | None = None,
) -> list[dict]:
    return [
        document
        for document in documents
        if isinstance(document, dict)
        and str(document.get("status", "")).strip() == "validated"
        and _document_matches_patterns(document, patterns)
    ]


def _find_document_by_storage_path(documents: list[dict], target_relative_path: str) -> dict | None:
    storage_path = _normalize_storage_path(target_relative_path)
    for document in documents:
        if not isinstance(document, dict):
            continue
        if str(document.get("storage_path", "")).strip() == storage_path:
            return document
    return None


class DeleteDocumentTool:
    name = "delete_document"
    metadata = ToolMetadata(
        name=name,
        description="Delete a single Supabase-backed document and optionally remove its indexed chunks.",
        arguments_schema={
            "target_relative_path": {
                "type": "string",
                "required": True,
                "description": "Document path relative to shared/raw_data, usually prefixed with supabase/.",
            },
            "cleanup_index": {
                "type": "boolean",
                "required": False,
                "description": "Whether to remove indexed chunks from the vector store before deleting metadata and storage.",
            },
            "document_query": {
                "type": "string",
                "required": False,
                "description": "Original user phrasing when the exact document path still needs resolution.",
            },
        },
        output_description="Returns deletion details for the Supabase document and any indexed chunk cleanup.",
        requires_confirmation=True,
    )

    def __init__(
        self,
        ingestion_client: IngestionClient,
        embedding_client: EmbeddingClient,
        supabase_documents_client: SupabaseDocumentsClient | None = None,
    ) -> None:
        self._ingestion_client = ingestion_client
        self._embedding_client = embedding_client
        self._supabase_documents_client = supabase_documents_client

    def execute(self, arguments: dict) -> ToolExecutionResult:
        target_relative_path = str(arguments.get("target_relative_path", "")).strip()
        storage_path = _normalize_storage_path(target_relative_path) if target_relative_path else ""
        if not storage_path or storage_path == "UNKNOWN_DOCUMENT":
            return ToolExecutionResult(
                status="error",
                answer="I could not determine which Supabase document to delete. Specify the exact document path or name.",
                result={},
            )

        if self._supabase_documents_client is None:
            raise ValueError("Supabase documents client is required for delete_document")
        document = _find_document_by_storage_path(self._supabase_documents_client.list_documents(), storage_path)
        if document is None:
            return ToolExecutionResult(
                status="error",
                answer=f"I could not find a Supabase document matching '{storage_path}'.",
                result={},
            )

        cleanup_index = bool(arguments.get("cleanup_index", False))
        chunk_result: dict = {"cleanup_index": cleanup_index, "deleted_count": 0, "matched_objects_count": 0}
        if cleanup_index:
            chunk_result = self._embedding_client.remove_document(str(document["id"]))
        deletion_result = self._ingestion_client.delete_document(str(document["id"]))
        return ToolExecutionResult(
            status="ok",
            answer=f"Supabase document '{storage_path}' deletion request completed.",
            result={
                **chunk_result,
                **deletion_result,
                "document_id": str(document["id"]),
                "target_relative_path": _supabase_target_relative_path(storage_path),
            },
        )


class DeleteDocumentsBatchTool:
    name = "delete_documents_batch"
    metadata = ToolMetadata(
        name=name,
        description="Delete multiple Supabase-backed documents in one operation and optionally clear indexed chunks.",
        arguments_schema={
            "target_relative_paths": {
                "type": "array",
                "required": True,
                "items": {"type": "string"},
                "description": "Document paths to delete.",
            },
            "cleanup_index": {
                "type": "boolean",
                "required": False,
                "description": "Whether to remove indexed chunks before deleting document storage and rows.",
            },
            "document_query": {
                "type": "string",
                "required": False,
                "description": "Original user phrasing that led to the batch selection.",
            },
        },
        output_description="Returns deleted paths, indexed cleanup counts, and per-document deletion results.",
        requires_confirmation=True,
    )

    def __init__(
        self,
        ingestion_client: IngestionClient,
        embedding_client: EmbeddingClient,
        supabase_documents_client: SupabaseDocumentsClient | None = None,
    ) -> None:
        self._ingestion_client = ingestion_client
        self._embedding_client = embedding_client
        self._supabase_documents_client = supabase_documents_client

    def execute(self, arguments: dict) -> ToolExecutionResult:
        target_relative_paths_raw = arguments.get("target_relative_paths", [])
        target_relative_paths = [
            str(path).strip()
            for path in target_relative_paths_raw
            if isinstance(path, str) and str(path).strip()
        ]
        if not target_relative_paths:
            return ToolExecutionResult(
                status="error",
                answer="No target documents were provided for batch deletion.",
                result={},
            )

        if self._supabase_documents_client is None:
            raise ValueError("Supabase documents client is required for delete_documents_batch")
        all_documents = self._supabase_documents_client.list_documents()
        target_documents = []
        for path in target_relative_paths:
            document = _find_document_by_storage_path(all_documents, path)
            if document is not None:
                target_documents.append(document)
        if not target_documents:
            return ToolExecutionResult(
                status="error",
                answer="None of the requested documents could be resolved to current Supabase records.",
                result={},
            )

        cleanup_index = bool(arguments.get("cleanup_index", False))
        deleted_count = 0
        matched_objects_count = 0
        deleted_documents = []
        failures: list[dict] = []
        for document in target_documents:
            document_id = str(document["id"])
            storage_path = str(document["storage_path"])
            try:
                if cleanup_index:
                    cleanup_result = self._embedding_client.remove_document(document_id)
                    deleted_count += int(cleanup_result.get("deleted_count", 0) or 0)
                    matched_objects_count += int(cleanup_result.get("matched_objects_count", 0) or 0)
                deleted_documents.append(self._ingestion_client.delete_document(document_id))
            except Exception as exc:
                failures.append({"document_id": document_id, "storage_path": storage_path, "error": str(exc)})
        return ToolExecutionResult(
            status="ok" if len(deleted_documents) > 0 else "error",
            answer=(
                f"Batch deletion request completed for {len(deleted_documents)} documents. "
                f"Deleted {deleted_count} indexed objects."
            ),
            result={
                "cleanup_index": cleanup_index,
                "deleted_count": deleted_count,
                "matched_objects_count": matched_objects_count,
                "target_relative_paths": [
                    _supabase_target_relative_path(str(document["storage_path"])) for document in target_documents
                ],
                "documents_deleted": len(deleted_documents),
                "deleted_documents": deleted_documents,
                "failures": failures,
            },
        )


class DeleteValidatedDocumentsTool:
    name = "delete_validated_documents"
    metadata = ToolMetadata(
        name=name,
        description="Remove indexed chunks for the validated document corpus without deleting the source files.",
        arguments_schema={
            "raw_dir": {
                "type": "string",
                "required": False,
                "description": "Directory containing validated source documents.",
            },
            "local_root": {
                "type": "string",
                "required": False,
                "description": "Local root used to derive relative document paths.",
            },
            "patterns": {
                "type": "array",
                "required": False,
                "items": {"type": "string"},
                "description": "Optional glob patterns to restrict discovered source files.",
            },
        },
        output_description="Returns discovered target paths and indexed object deletion counts.",
        requires_confirmation=True,
    )

    def __init__(
        self,
        embedding_client: EmbeddingClient,
        supabase_documents_client: SupabaseDocumentsClient,
    ) -> None:
        self._embedding_client = embedding_client
        self._supabase_documents_client = supabase_documents_client

    def execute(self, arguments: dict) -> ToolExecutionResult:
        patterns_raw = arguments.get("patterns")
        patterns = patterns_raw if isinstance(patterns_raw, list) else None
        documents = _validated_documents(self._supabase_documents_client.list_documents(), patterns=patterns)
        if not documents:
            return ToolExecutionResult(
                status="ok",
                answer="No validated documents were found to delete from the index.",
                result={"target_relative_paths": [], "requested_count": 0, "deleted_count": 0, "matched_objects_count": 0},
            )

        deleted_count = 0
        matched_objects_count = 0
        failures: list[dict] = []
        target_relative_paths = []
        for document in documents:
            document_id = str(document["id"])
            storage_path = str(document["storage_path"])
            target_relative_paths.append(_supabase_target_relative_path(storage_path))
            try:
                result = self._embedding_client.remove_document(document_id)
                deleted_count += int(result.get("deleted_count", 0) or 0)
                matched_objects_count += int(result.get("matched_objects_count", 0) or 0)
            except Exception as exc:
                failures.append({"document_id": document_id, "storage_path": storage_path, "error": str(exc)})
        return ToolExecutionResult(
            status="ok" if len(failures) < len(documents) else "error",
            answer=(
                f"Cleaned indexed chunks for {len(documents)} validated documents. "
                f"Deleted {deleted_count} objects."
            ),
            result={
                "requested_count": len(documents),
                "matched_objects_count": matched_objects_count,
                "deleted_count": deleted_count,
                "target_relative_paths": target_relative_paths,
                "failures": failures,
            },
        )


class EmbedDocumentTool:
    name = "embed_document"
    metadata = ToolMetadata(
        name=name,
        description="Index a single document into the knowledge base.",
        arguments_schema={
            "target_relative_path": {
                "type": "string",
                "required": False,
                "description": "Document path relative to shared/raw_data.",
            },
            "document_query": {
                "type": "string",
                "required": False,
                "description": "Original user phrasing when the exact path still needs resolution.",
            },
            "skip_if_exists": {
                "type": "boolean",
                "required": False,
                "description": "Whether to skip indexing when the document already exists in the index.",
            },
        },
        output_description="Returns indexing status, resolved document id, storage path, and indexed chunk counts.",
        requires_confirmation=True,
    )

    def __init__(
        self,
        embedding_client: EmbeddingClient,
        supabase_documents_client: SupabaseDocumentsClient,
    ) -> None:
        self._embedding_client = embedding_client
        self._supabase_documents_client = supabase_documents_client

    def execute(self, arguments: dict) -> ToolExecutionResult:
        target_relative_path = str(arguments.get("target_relative_path", "")).strip()
        skip_if_embedded = bool(arguments.get("skip_if_embedded", arguments.get("skip_if_exists", True)))
        documents = self._supabase_documents_client.list_documents()
        if not target_relative_path or target_relative_path == "UNKNOWN_DOCUMENT":
            resolution = resolve_supabase_document_reference(
                str(arguments.get("document_query", target_relative_path)),
                documents=documents,
            )
            if resolution["status"] == "resolved":
                target_relative_path = _supabase_target_relative_path(str(resolution["storage_path"]))
            elif resolution["status"] == "ambiguous":
                candidates = resolution["candidates"]
                return ToolExecutionResult(
                    status="error",
                    answer=(
                        "I found multiple possible documents to embed. "
                        f"Please specify one of these paths: {', '.join(candidates)}"
                    ),
                    result={"candidates": candidates},
                )
        if not target_relative_path:
            return ToolExecutionResult(
                status="error",
                answer="I could not determine which document to embed. Specify the exact document path or name.",
                result={},
            )

        document = _find_document_by_storage_path(documents, target_relative_path)
        if document is None:
            return ToolExecutionResult(
                status="error",
                answer=f"I could not find a Supabase document matching '{target_relative_path}'.",
                result={},
            )

        result = self._embedding_client.index_document(
            document_id=str(document["id"]),
            skip_if_embedded=skip_if_embedded,
        )
        status = str(result.get("status", "ok"))
        if status == "already_embedded":
            answer = f"Document '{target_relative_path}' is already indexed."
        else:
            answer = f"Document '{target_relative_path}' embedding request completed."
        return ToolExecutionResult(status="ok", answer=answer, result=result)


class EmbedValidatedDocumentsTool:
    name = "embed_validated_documents"
    metadata = ToolMetadata(
        name=name,
        description="Index all validated Supabase documents into the knowledge base.",
        arguments_schema={
            "patterns": {
                "type": "array",
                "required": False,
                "items": {"type": "string"},
                "description": "Optional glob patterns to restrict the validated document set by storage path or filename.",
            },
            "skip_if_embedded": {
                "type": "boolean",
                "required": False,
                "description": "Whether already-embedded validated documents should be skipped.",
            },
            "dry_run": {
                "type": "boolean",
                "required": False,
                "description": "Whether to simulate indexing without calling embedding-service.",
            },
        },
        output_description="Returns validated document indexing counts, failures, and indexed chunk totals.",
        requires_confirmation=True,
    )

    def __init__(
        self,
        embedding_client: EmbeddingClient,
        supabase_documents_client: SupabaseDocumentsClient,
    ) -> None:
        self._embedding_client = embedding_client
        self._supabase_documents_client = supabase_documents_client

    def execute(self, arguments: dict) -> ToolExecutionResult:
        patterns_raw = arguments.get("patterns")
        patterns = patterns_raw if isinstance(patterns_raw, list) else None
        skip_if_embedded = bool(arguments.get("skip_if_embedded", True))
        dry_run = bool(arguments.get("dry_run", False))
        documents = _validated_documents(self._supabase_documents_client.list_documents(), patterns=patterns)
        if not documents:
            return ToolExecutionResult(
                status="ok",
                answer="No validated documents were found to embed.",
                result={"documents_processed": 0, "documents_failed": 0, "chunks_indexed": 0, "documents": []},
            )

        indexed_documents = []
        failures = []
        chunks_indexed = 0
        for document in documents:
            document_id = str(document["id"])
            storage_path = str(document["storage_path"])
            if dry_run:
                indexed_documents.append(
                    {
                        "document_id": document_id,
                        "storage_path": storage_path,
                        "status": "dry_run",
                    }
                )
                continue
            try:
                result = self._embedding_client.index_document(
                    document_id=document_id,
                    skip_if_embedded=skip_if_embedded,
                )
                chunks_indexed += int(result.get("indexed_count", 0) or 0)
                indexed_documents.append(result)
            except Exception as exc:
                failures.append({"document_id": document_id, "storage_path": storage_path, "error": str(exc)})

        result = {
            "documents_processed": len(indexed_documents),
            "documents_failed": len(failures),
            "chunks_indexed": chunks_indexed,
            "documents": indexed_documents,
            "failures": failures,
            "dry_run": dry_run,
        }
        return ToolExecutionResult(
            status="ok" if len(indexed_documents) > 0 or not documents else "error",
            answer=(
                f"Validated document embedding completed: {result.get('documents_processed', 0)} processed, "
                f"{result.get('documents_failed', 0)} failed, {result.get('chunks_indexed', 0)} chunks indexed."
            ),
            result=result,
        )


class ReindexCorpusTool:
    name = "reindex_corpus"
    metadata = ToolMetadata(
        name=name,
        description="Remove indexed vectors and re-index the validated Supabase document corpus.",
        arguments_schema={
            "patterns": {
                "type": "array",
                "required": False,
                "items": {"type": "string"},
                "description": "Optional glob patterns to restrict the validated corpus selection.",
            },
            "dry_run": {
                "type": "boolean",
                "required": False,
                "description": "Whether to simulate the rebuild without mutating the index.",
            },
        },
        output_description="Returns delete and re-index counts for the validated corpus rebuild.",
        requires_confirmation=True,
    )

    def __init__(
        self,
        embedding_client: EmbeddingClient,
        supabase_documents_client: SupabaseDocumentsClient,
    ) -> None:
        self._embedding_client = embedding_client
        self._supabase_documents_client = supabase_documents_client

    def execute(self, arguments: dict) -> ToolExecutionResult:
        patterns_raw = arguments.get("patterns")
        patterns = patterns_raw if isinstance(patterns_raw, list) else None
        dry_run = bool(arguments.get("dry_run", False))
        documents = _validated_documents(self._supabase_documents_client.list_documents(), patterns=patterns)
        if not documents:
            return ToolExecutionResult(
                status="ok",
                answer="No validated documents were found to reindex.",
                result={"documents_processed": 0, "documents_failed": 0, "chunks_indexed": 0, "deleted_count": 0},
            )

        deleted_count = 0
        matched_objects_count = 0
        chunks_indexed = 0
        processed = []
        failures = []
        for document in documents:
            document_id = str(document["id"])
            storage_path = str(document["storage_path"])
            if dry_run:
                processed.append({"document_id": document_id, "storage_path": storage_path, "status": "dry_run"})
                continue
            try:
                remove_result = self._embedding_client.remove_document(document_id)
                deleted_count += int(remove_result.get("deleted_count", 0) or 0)
                matched_objects_count += int(remove_result.get("matched_objects_count", 0) or 0)
                index_result = self._embedding_client.index_document(document_id=document_id, skip_if_embedded=False)
                chunks_indexed += int(index_result.get("indexed_count", 0) or 0)
                processed.append(
                    {
                        "document_id": document_id,
                        "storage_path": storage_path,
                        "remove_result": remove_result,
                        "index_result": index_result,
                    }
                )
            except Exception as exc:
                failures.append({"document_id": document_id, "storage_path": storage_path, "error": str(exc)})

        result = {
            "documents_processed": len(processed),
            "documents_failed": len(failures),
            "chunks_indexed": chunks_indexed,
            "deleted_count": deleted_count,
            "matched_objects_count": matched_objects_count,
            "documents": processed,
            "failures": failures,
            "dry_run": dry_run,
        }
        return ToolExecutionResult(
            status="ok" if len(processed) > 0 or not documents else "error",
            answer=(
                f"Corpus indexing completed: {result.get('documents_processed', 0)} processed, "
                f"{result.get('documents_failed', 0)} failed, {result.get('chunks_indexed', 0)} chunks indexed, "
                f"{result.get('deleted_count', 0)} old vectors removed."
            ),
            result=result,
        )
