from __future__ import annotations

from pathlib import Path

from app.clients.ingestion_client import IngestionClient
from app.models import ToolExecutionResult


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


class DeleteDocumentTool:
    name = "delete_document"

    def __init__(self, ingestion_client: IngestionClient) -> None:
        self._ingestion_client = ingestion_client

    def execute(self, arguments: dict) -> ToolExecutionResult:
        target_relative_path = str(arguments.get("target_relative_path", "")).strip()
        if not target_relative_path or target_relative_path == "UNKNOWN_DOCUMENT":
            return ToolExecutionResult(
                status="error",
                answer="I could not determine which document to delete. Specify the exact document path or name.",
                result={},
            )

        result = self._ingestion_client.remove_document_chunks([target_relative_path])
        return ToolExecutionResult(
            status="ok",
            answer=f"Document '{target_relative_path}' deletion request completed.",
            result=result,
        )


class DeleteDocumentsBatchTool:
    name = "delete_documents_batch"

    def __init__(self, ingestion_client: IngestionClient) -> None:
        self._ingestion_client = ingestion_client

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

        result = self._ingestion_client.remove_document_chunks(target_relative_paths)
        return ToolExecutionResult(
            status="ok",
            answer=(
                f"Batch deletion request completed for {len(target_relative_paths)} documents. "
                f"Deleted {result.get('deleted_count', 0)} indexed objects."
            ),
            result={**result, "target_relative_paths": target_relative_paths},
        )


class DeleteValidatedDocumentsTool:
    name = "delete_validated_documents"

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

    def __init__(self, ingestion_client: IngestionClient) -> None:
        self._ingestion_client = ingestion_client

    def execute(self, arguments: dict) -> ToolExecutionResult:
        target_relative_path = str(arguments.get("target_relative_path", "")).strip()
        skip_if_exists = bool(arguments.get("skip_if_exists", True))
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
