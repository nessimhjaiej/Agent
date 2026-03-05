import os
from dataclasses import dataclass


def _parse_int(name: str, default: int) -> int:
    raw = os.getenv(name)
    if raw is None or raw.strip() == "":
        return default
    try:
        return int(raw)
    except ValueError as exc:
        raise ValueError(f"{name} must be an integer") from exc


def _parse_float(name: str, default: float) -> float:
    raw = os.getenv(name)
    if raw is None or raw.strip() == "":
        return default
    try:
        return float(raw)
    except ValueError as exc:
        raise ValueError(f"{name} must be a number") from exc


@dataclass(slots=True)
class Settings:
    app_name: str = "ingestion-service"
    app_version: str = "0.1.0"
    raw_dir: str = "shared/raw_data"
    source_root_in_preprocessing: str = "/shared/raw_data"
    preprocessing_base_url: str = "http://localhost:8000"
    embedding_base_url: str = "http://localhost:8002"
    embedding_batch_size: int = 100
    default_recursive: bool = True
    http_timeout_seconds: float = 120.0
    file_patterns: tuple[str, ...] = ("*.pdf", "*.txt", "*.md")
    weaviate_http_url: str = "http://localhost:8080"
    weaviate_collection: str = "Chunk"
    supabase_sync_subdir: str = "supabase"

    @classmethod
    def from_env(cls) -> "Settings":
        file_patterns_raw = os.getenv("INGESTION_FILE_PATTERNS", "*.pdf,*.txt,*.md")
        file_patterns = tuple(
            pattern.strip() for pattern in file_patterns_raw.split(",") if pattern.strip()
        )
        if not file_patterns:
            file_patterns = ("*.pdf", "*.txt", "*.md")

        recursive_raw = os.getenv("INGESTION_RECURSIVE")
        if recursive_raw is None or recursive_raw.strip() == "":
            recursive = True
        else:
            recursive = recursive_raw.strip().lower() in {"1", "true", "yes", "on"}

        return cls(
            app_name=os.getenv("INGESTION_APP_NAME", "ingestion-service"),
            app_version=os.getenv("INGESTION_APP_VERSION", "0.1.0"),
            raw_dir=os.getenv("INGESTION_RAW_DIR", os.getenv("INGEST_RAW_DIR", "shared/raw_data")),
            source_root_in_preprocessing=os.getenv(
                "INGESTION_SOURCE_ROOT_IN_PREPROCESSING",
                os.getenv("INGEST_SOURCE_ROOT_IN_PREPROCESSING", "/shared/raw_data"),
            ),
            preprocessing_base_url=os.getenv(
                "INGESTION_PREPROCESSING_BASE_URL",
                os.getenv("PREPROCESSING_BASE_URL", "http://localhost:8000"),
            ),
            embedding_base_url=os.getenv(
                "INGESTION_EMBEDDING_BASE_URL",
                os.getenv("EMBEDDING_BASE_URL", "http://localhost:8002"),
            ),
            embedding_batch_size=_parse_int(
                "INGESTION_EMBEDDING_BATCH_SIZE",
                _parse_int("INGEST_EMBEDDING_BATCH_SIZE", 100),
            ),
            default_recursive=recursive,
            http_timeout_seconds=_parse_float("INGESTION_HTTP_TIMEOUT_SECONDS", 120.0),
            file_patterns=file_patterns,
            weaviate_http_url=os.getenv("WEAVIATE_HTTP_URL", "http://localhost:8080"),
            weaviate_collection=os.getenv("WEAVIATE_COLLECTION", "Chunk"),
            supabase_sync_subdir=os.getenv("INGESTION_SUPABASE_SYNC_SUBDIR", "supabase"),
        )

    def validate(self) -> None:
        if not self.app_name:
            raise ValueError("INGESTION_APP_NAME is required")
        if not self.app_version:
            raise ValueError("INGESTION_APP_VERSION is required")
        if not self.raw_dir:
            raise ValueError("INGESTION_RAW_DIR is required")
        if not self.source_root_in_preprocessing:
            raise ValueError("INGESTION_SOURCE_ROOT_IN_PREPROCESSING is required")
        if not self.preprocessing_base_url:
            raise ValueError("INGESTION_PREPROCESSING_BASE_URL is required")
        if not self.embedding_base_url:
            raise ValueError("INGESTION_EMBEDDING_BASE_URL is required")
        if self.embedding_batch_size <= 0:
            raise ValueError("INGESTION_EMBEDDING_BATCH_SIZE must be > 0")
        if self.http_timeout_seconds <= 0:
            raise ValueError("INGESTION_HTTP_TIMEOUT_SECONDS must be > 0")
        if not self.weaviate_http_url:
            raise ValueError("WEAVIATE_HTTP_URL is required")
        if not self.weaviate_collection:
            raise ValueError("WEAVIATE_COLLECTION is required")
        if not self.supabase_sync_subdir:
            raise ValueError("INGESTION_SUPABASE_SYNC_SUBDIR is required")
