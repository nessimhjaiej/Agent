import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv


_PROJECT_ROOT = Path(__file__).resolve().parents[3]
load_dotenv(_PROJECT_ROOT / ".env", override=True)
load_dotenv(_PROJECT_ROOT / ".env.local", override=True)


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


def _parse_bool(name: str, default: bool) -> bool:
    raw = os.getenv(name)
    if raw is None or raw.strip() == "":
        return default

    value = raw.strip().lower()
    if value in {"1", "true", "yes", "on"}:
        return True
    if value in {"0", "false", "no", "off"}:
        return False
    raise ValueError(f"{name} must be a boolean (true/false)")


@dataclass(slots=True)
class Settings:
    app_name: str = "embedding-service"
    app_version: str = "0.1.0"
    openai_key: str = ""
    embedding_model: str = "text-embedding-3-small"
    embedding_dimensions: int | None = None
    embedding_batch_size: int = 64
    embedding_timeout_seconds: float = 30.0
    openai_max_retries: int = 5
    openai_retry_base_seconds: float = 1.0
    weaviate_http_url: str = "http://localhost:8080"
    weaviate_grpc_host: str = "localhost"
    weaviate_grpc_port: int = 50051
    weaviate_collection: str = "Chunk"
    weaviate_batch_size: int = 100
    weaviate_startup_timeout_seconds: float = 20.0
    fail_if_collection_missing: bool = True
    preprocessing_base_url: str = "http://localhost:8000"
    http_timeout_seconds: float = 120.0
    shared_raw_dir: str = "/shared/raw_data"
    supabase_url: str = ""
    supabase_key: str = ""
    supabase_docs_bucket: str = "documents"
    supabase_docs_table: str = "documents"

    @classmethod
    def from_env(cls) -> "Settings":
        raw_dimensions = os.getenv("EMBEDDING_DIMENSIONS")
        dimensions: int | None = None
        if raw_dimensions and raw_dimensions.strip() != "":
            try:
                dimensions = int(raw_dimensions)
            except ValueError as exc:
                raise ValueError("EMBEDDING_DIMENSIONS must be an integer") from exc

        settings = cls(
            app_name=os.getenv("EMBEDDING_APP_NAME", "embedding-service"),
            app_version=os.getenv("EMBEDDING_APP_VERSION", "0.1.0"),
            openai_key=os.getenv("OPENAI_KEY", "").strip(),
            embedding_model=os.getenv("EMBEDDING_MODEL", "text-embedding-3-small").strip(),
            embedding_dimensions=dimensions,
            embedding_batch_size=_parse_int("EMBEDDING_BATCH_SIZE", 64),
            embedding_timeout_seconds=_parse_float("EMBEDDING_TIMEOUT_SECONDS", 30.0),
            openai_max_retries=_parse_int("OPENAI_MAX_RETRIES", 5),
            openai_retry_base_seconds=_parse_float("OPENAI_RETRY_BASE_SECONDS", 1.0),
            weaviate_http_url=os.getenv("WEAVIATE_HTTP_URL", "http://localhost:8080").strip(),
            weaviate_grpc_host=os.getenv("WEAVIATE_GRPC_HOST", "localhost").strip(),
            weaviate_grpc_port=_parse_int("WEAVIATE_GRPC_PORT", 50051),
            weaviate_collection=os.getenv("WEAVIATE_COLLECTION", "Chunk").strip(),
            weaviate_batch_size=_parse_int("WEAVIATE_BATCH_SIZE", 100),
            weaviate_startup_timeout_seconds=_parse_float("WEAVIATE_STARTUP_TIMEOUT_SECONDS", 20.0),
            fail_if_collection_missing=_parse_bool("WEAVIATE_FAIL_IF_COLLECTION_MISSING", True),
            preprocessing_base_url=os.getenv(
                "EMBEDDING_PREPROCESSING_BASE_URL",
                os.getenv("PREPROCESSING_BASE_URL", "http://localhost:8000"),
            ).strip(),
            http_timeout_seconds=_parse_float("EMBEDDING_HTTP_TIMEOUT_SECONDS", 120.0),
            shared_raw_dir=os.getenv("EMBEDDING_SHARED_RAW_DIR", "/shared/raw_data").strip(),
            supabase_url=os.getenv("EMBEDDING_SUPABASE_URL", os.getenv("AUTH_SUPABASE_URL", "")).strip(),
            supabase_key=os.getenv("EMBEDDING_SUPABASE_KEY", os.getenv("AUTH_SUPABASE_KEY", "")).strip(),
            supabase_docs_bucket=os.getenv("EMBEDDING_SUPABASE_DOCS_BUCKET", os.getenv("VITE_SUPABASE_DOCS_BUCKET", "documents")).strip(),
            supabase_docs_table=os.getenv("EMBEDDING_SUPABASE_DOCS_TABLE", os.getenv("VITE_SUPABASE_DOCS_TABLE", "documents")).strip(),
        )
        settings.validate()
        return settings

    def validate(self) -> None:
        if not self.openai_key:
            raise ValueError("OPENAI_KEY is required")
        if not self.embedding_model:
            raise ValueError("EMBEDDING_MODEL is required")
        if self.embedding_dimensions is not None and self.embedding_dimensions <= 0:
            raise ValueError("EMBEDDING_DIMENSIONS must be > 0 when provided")
        if self.embedding_batch_size <= 0:
            raise ValueError("EMBEDDING_BATCH_SIZE must be > 0")
        if self.embedding_timeout_seconds <= 0:
            raise ValueError("EMBEDDING_TIMEOUT_SECONDS must be > 0")
        if self.openai_max_retries < 0:
            raise ValueError("OPENAI_MAX_RETRIES must be >= 0")
        if self.openai_retry_base_seconds <= 0:
            raise ValueError("OPENAI_RETRY_BASE_SECONDS must be > 0")
        if not self.weaviate_http_url:
            raise ValueError("WEAVIATE_HTTP_URL is required")
        if not self.weaviate_grpc_host:
            raise ValueError("WEAVIATE_GRPC_HOST is required")
        if self.weaviate_grpc_port <= 0:
            raise ValueError("WEAVIATE_GRPC_PORT must be > 0")
        if not self.weaviate_collection:
            raise ValueError("WEAVIATE_COLLECTION is required")
        if self.weaviate_batch_size <= 0:
            raise ValueError("WEAVIATE_BATCH_SIZE must be > 0")
        if self.weaviate_startup_timeout_seconds <= 0:
            raise ValueError("WEAVIATE_STARTUP_TIMEOUT_SECONDS must be > 0")
        if not self.preprocessing_base_url:
            raise ValueError("EMBEDDING_PREPROCESSING_BASE_URL is required")
        if self.http_timeout_seconds <= 0:
            raise ValueError("EMBEDDING_HTTP_TIMEOUT_SECONDS must be > 0")
        if not self.shared_raw_dir:
            raise ValueError("EMBEDDING_SHARED_RAW_DIR is required")
        if not self.supabase_url:
            raise ValueError("EMBEDDING_SUPABASE_URL or AUTH_SUPABASE_URL is required")
        if not self.supabase_key:
            raise ValueError("EMBEDDING_SUPABASE_KEY or AUTH_SUPABASE_KEY is required")
        if not self.supabase_docs_bucket:
            raise ValueError("EMBEDDING_SUPABASE_DOCS_BUCKET is required")
        if not self.supabase_docs_table:
            raise ValueError("EMBEDDING_SUPABASE_DOCS_TABLE is required")
