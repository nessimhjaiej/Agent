from __future__ import annotations

from pathlib import Path
import re

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
        supabase_documents_client: SupabaseDocumentsClient | None = None,
    ) -> None:
        self._ingestion_client = ingestion_client
        self._supabase_documents_client = supabase_documents_client

    def execute(self, arguments: dict) -> ToolExecutionResult:
        target_relative_path = str(arguments.get("target_relative_path", "")).strip()
        storage_path = target_relative_path.removeprefix("supabase/") if target_relative_path else ""
        if not storage_path or storage_path == "UNKNOWN_DOCUMENT":
            return ToolExecutionResult(
                status="error",
                answer="I could not determine which Supabase document to delete. Specify the exact document path or name.",
                result={},
            )

        cleanup_index = bool(arguments.get("cleanup_index", False))
        chunk_result: dict = {"cleanup_index": cleanup_index, "deleted_count": 0}
        if cleanup_index:
            chunk_result = self._ingestion_client.remove_document_chunks([f"supabase/{storage_path}"])
        if self._supabase_documents_client is None:
            raise ValueError("Supabase documents client is required for delete_document")
        supabase_result = self._supabase_documents_client.delete_document(storage_path)
        return ToolExecutionResult(
            status="ok",
            answer=f"Supabase document '{storage_path}' deletion request completed.",
            result={**chunk_result, **supabase_result, "target_relative_path": f"supabase/{storage_path}"},
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
        supabase_documents_client: SupabaseDocumentsClient | None = None,
    ) -> None:
        self._ingestion_client = ingestion_client
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

        storage_paths = [path.removeprefix("supabase/").lstrip("/") for path in target_relative_paths]
        cleanup_index = bool(arguments.get("cleanup_index", False))
        result: dict = {"cleanup_index": cleanup_index, "deleted_count": 0}
        if cleanup_index:
            result = self._ingestion_client.remove_document_chunks([f"supabase/{path}" for path in storage_paths])
        if self._supabase_documents_client is None:
            raise ValueError("Supabase documents client is required for delete_documents_batch")
        deleted_documents = [
            self._supabase_documents_client.delete_document(storage_path)
            for storage_path in storage_paths
        ]
        return ToolExecutionResult(
            status="ok",
            answer=(
                f"Batch deletion request completed for {len(target_relative_paths)} documents. "
                f"Deleted {result.get('deleted_count', 0)} indexed objects."
            ),
            result={
                **result,
                "target_relative_paths": [f"supabase/{path}" for path in storage_paths],
                "documents_deleted": len(deleted_documents),
                "deleted_documents": deleted_documents,
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

    def __init__(self, ingestion_client: IngestionClient) -> None:
        self._ingestion_client = ingestion_client

    def execute(self, arguments: dict) -> ToolExecutionResult:
        raw_dir = str(arguments.get("raw_dir", "shared/raw_data/supabase/validated")).strip()
        local_root = str(arguments.get("local_root", "shared/raw_data")).strip()
        patterns_raw = arguments.get("patterns")
        patterns = patterns_raw if isinstance(patterns_raw, list) else None

        target_relative_paths = _discover_target_relative_paths(
            raw_dir=raw_dir,
            local_root=local_root,
            patterns=patterns,
        )
        if not target_relative_paths:
            return ToolExecutionResult(
                status="ok",
                answer="No validated documents were found to delete from the index.",
                result={"target_relative_paths": [], "requested_count": 0, "deleted_count": 0},
            )

        result = self._ingestion_client.remove_document_chunks(target_relative_paths)
        return ToolExecutionResult(
            status="ok",
            answer=(
                f"Cleaned indexed chunks for {len(target_relative_paths)} validated documents. "
                f"Deleted {result.get('deleted_count', 0)} objects."
            ),
            result={**result, "target_relative_paths": target_relative_paths},
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
        output_description="Returns indexing status, source path, and indexed chunk counts.",
        requires_confirmation=True,
    )

    def __init__(self, ingestion_client: IngestionClient) -> None:
        self._ingestion_client = ingestion_client

    def execute(self, arguments: dict) -> ToolExecutionResult:
        target_relative_path = str(arguments.get("target_relative_path", "")).strip()
        skip_if_exists = bool(arguments.get("skip_if_exists", True))
        if not target_relative_path or target_relative_path == "UNKNOWN_DOCUMENT":
            resolution = resolve_document_reference(
                str(arguments.get("document_query", target_relative_path)),
                raw_root=str(arguments.get("raw_root", "shared/raw_data")),
                local_root=str(arguments.get("local_root", "shared/raw_data")),
            )
            if resolution["status"] == "resolved":
                target_relative_path = str(resolution["target_relative_path"])
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

        result = self._ingestion_client.index_document(
            target_relative_path=target_relative_path,
            skip_if_exists=skip_if_exists,
        )
        status = str(result.get("status", "ok"))
        if status == "already_exists":
            answer = f"Document '{target_relative_path}' is already indexed."
        else:
            answer = f"Document '{target_relative_path}' embedding request completed."
        return ToolExecutionResult(status="ok", answer=answer, result=result)


class EmbedValidatedDocumentsTool:
    name = "embed_validated_documents"
    metadata = ToolMetadata(
        name=name,
        description="Run ingestion for the validated document corpus.",
        arguments_schema={
            "raw_dir": {
                "type": "string",
                "required": False,
                "description": "Directory containing validated documents to ingest.",
            },
            "source_root_in_preprocessing": {
                "type": "string",
                "required": False,
                "description": "Source root path that preprocessing should treat as the raw document root.",
            },
            "recursive": {
                "type": "boolean",
                "required": False,
                "description": "Whether to recurse into subdirectories.",
            },
            "patterns": {
                "type": "array",
                "required": False,
                "items": {"type": "string"},
                "description": "Optional glob patterns to restrict the ingestion set.",
            },
            "dry_run": {
                "type": "boolean",
                "required": False,
                "description": "Whether to simulate ingestion without indexing.",
            },
        },
        output_description="Returns ingestion counts for processed documents, failures, and indexed chunks.",
        requires_confirmation=True,
    )

    def __init__(self, ingestion_client: IngestionClient) -> None:
        self._ingestion_client = ingestion_client

    def execute(self, arguments: dict) -> ToolExecutionResult:
        raw_dir = str(arguments.get("raw_dir", "shared/raw_data/supabase/validated")).strip()
        source_root = str(
            arguments.get("source_root_in_preprocessing", "/shared/raw_data/supabase/validated")
        ).strip()
        recursive = bool(arguments.get("recursive", True))
        patterns_raw = arguments.get("patterns")
        patterns = patterns_raw if isinstance(patterns_raw, list) else None

        result = self._ingestion_client.run_ingestion(
            raw_dir=raw_dir,
            source_root_in_preprocessing=source_root,
            recursive=recursive,
            patterns=patterns,
            dry_run=bool(arguments.get("dry_run", False)),
        )
        return ToolExecutionResult(
            status="ok",
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
        description="Run a clean corpus rebuild workflow for the validated document corpus.",
        arguments_schema={
            "raw_dir": {
                "type": "string",
                "required": False,
                "description": "Directory containing validated documents to ingest.",
            },
            "source_root_in_preprocessing": {
                "type": "string",
                "required": False,
                "description": "Source root path used by preprocessing.",
            },
            "recursive": {
                "type": "boolean",
                "required": False,
                "description": "Whether to recurse into subdirectories.",
            },
            "patterns": {
                "type": "array",
                "required": False,
                "items": {"type": "string"},
                "description": "Optional glob patterns to restrict the corpus selection.",
            },
            "dry_run": {
                "type": "boolean",
                "required": False,
                "description": "Whether to simulate the workflow without indexing.",
            },
        },
        output_description="Returns ingestion counts for the rebuild run.",
        requires_confirmation=True,
    )

    def __init__(self, ingestion_client: IngestionClient) -> None:
        self._ingestion_client = ingestion_client

    def execute(self, arguments: dict) -> ToolExecutionResult:
        raw_dir = str(arguments.get("raw_dir", "shared/raw_data/supabase/validated")).strip()
        source_root = str(
            arguments.get("source_root_in_preprocessing", "/shared/raw_data/supabase/validated")
        ).strip()
        recursive = bool(arguments.get("recursive", True))
        patterns_raw = arguments.get("patterns")
        patterns = patterns_raw if isinstance(patterns_raw, list) else None

        result = self._ingestion_client.run_ingestion(
            raw_dir=raw_dir,
            source_root_in_preprocessing=source_root,
            recursive=recursive,
            patterns=patterns,
            dry_run=bool(arguments.get("dry_run", False)),
        )
        return ToolExecutionResult(
            status="ok",
            answer=(
                f"Corpus indexing completed: {result.get('documents_processed', 0)} processed, "
                f"{result.get('documents_failed', 0)} failed, {result.get('chunks_indexed', 0)} chunks indexed."
            ),
            result=result,
        )
