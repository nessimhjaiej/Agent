from app.config import Settings
from pathlib import PurePosixPath

from app.models import (
    IndexDocumentParams,
    IndexDocumentResult,
    IngestionRunParams,
    IngestionRunResult,
)
from app.orchestrator import IngestionOrchestrator
from app.schemas import IndexDocumentRequest, RunIngestionRequest


class IngestionService:
    def __init__(self, settings: Settings) -> None:
        self._settings = settings
        self._settings.validate()
        self._orchestrator = IngestionOrchestrator(timeout_seconds=settings.http_timeout_seconds)

    def run_ingestion(self, payload: RunIngestionRequest) -> IngestionRunResult:
        params = IngestionRunParams(
            raw_dir=payload.raw_dir or self._settings.raw_dir,
            source_root_in_preprocessing=(
                payload.source_root_in_preprocessing or self._settings.source_root_in_preprocessing
            ),
            preprocessing_base_url=payload.preprocessing_base_url or self._settings.preprocessing_base_url,
            embedding_base_url=payload.embedding_base_url or self._settings.embedding_base_url,
            embedding_batch_size=payload.embedding_batch_size or self._settings.embedding_batch_size,
            recursive=payload.recursive if payload.recursive is not None else self._settings.default_recursive,
            patterns=payload.patterns or list(self._settings.file_patterns),
            dry_run=payload.dry_run,
        )
        return self._orchestrator.run(params)

    def index_document(self, payload: IndexDocumentRequest) -> IndexDocumentResult:
        relative_target = self._normalize_target_path(payload.target_relative_path)
        source_path_for_preprocessing = self._to_preprocessing_source_path(relative_target)

        params = IndexDocumentParams(
            source_url=payload.source_url,
            source_path=payload.source_path,
            target_relative_path=source_path_for_preprocessing,
            source_root_in_preprocessing=(
                payload.source_root_in_preprocessing or self._settings.source_root_in_preprocessing
            ),
            preprocessing_base_url=payload.preprocessing_base_url or self._settings.preprocessing_base_url,
            embedding_base_url=payload.embedding_base_url or self._settings.embedding_base_url,
            embedding_batch_size=payload.embedding_batch_size or self._settings.embedding_batch_size,
            weaviate_http_url=self._settings.weaviate_http_url,
            weaviate_collection=self._settings.weaviate_collection,
            skip_if_exists=payload.skip_if_exists,
        )
        return self._orchestrator.index_document(params)

    def check_documents_exist(self, target_relative_paths: list[str]) -> dict[str, bool]:
        source_paths = [
            self._to_preprocessing_source_path(self._normalize_target_path(path))
            for path in target_relative_paths
        ]
        return self._orchestrator.check_documents_exist(
            weaviate_base_url=self._settings.weaviate_http_url,
            collection=self._settings.weaviate_collection,
            source_paths=source_paths,
        )

    def _normalize_target_path(self, value: str) -> PurePosixPath:
        normalized = value.strip().replace("\\", "/").lstrip("/")
        path = PurePosixPath(normalized)
        if not path.parts:
            raise ValueError("target_relative_path must not be empty")
        if any(part in {"..", "."} for part in path.parts):
            raise ValueError("target_relative_path cannot contain '.' or '..'")
        return path

    def _to_preprocessing_source_path(self, relative_target: PurePosixPath) -> str:
        root = PurePosixPath(self._settings.source_root_in_preprocessing)
        return str(root.joinpath(relative_target))
