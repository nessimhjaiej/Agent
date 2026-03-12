import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv


_PROJECT_ROOT = Path(__file__).resolve().parents[3]
load_dotenv(_PROJECT_ROOT / ".env", override=True)
load_dotenv(_PROJECT_ROOT / ".env.local", override=True)


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
    app_name: str = "admin-service"
    app_version: str = "0.1.0"
    openai_key: str = ""
    auth_base_url: str = "http://localhost:8001"
    auth_supabase_url: str = ""
    auth_supabase_key: str = ""
    supabase_url: str = ""
    supabase_key: str = ""
    supabase_docs_bucket: str = "documents"
    supabase_docs_table: str = "documents"
    embedding_base_url: str = "http://localhost:8002"
    retrieval_base_url: str = "http://localhost:8003"
    generation_base_url: str = "http://localhost:8004"
    ingestion_base_url: str = "http://localhost:8005"
    security_base_url: str = "http://localhost:8007"
    evaluation_base_url: str = "http://localhost:8004"
    http_timeout_seconds: float = 20.0
    embedding_model: str = "text-embedding-3-small"
    planner_model: str = "gpt-5-mini"
    planner_enabled: bool = True
    planner_temperature: float = 0.0
    planner_http_max_retries: int = 2
    planner_retry_base_seconds: float = 0.5
    require_confirmation_for_mutations: bool = True
    security_fail_closed: bool = False

    @classmethod
    def from_env(cls) -> "Settings":
        return cls(
            app_name=os.getenv("ADMIN_APP_NAME", "admin-service").strip(),
            app_version=os.getenv("ADMIN_APP_VERSION", "0.1.0").strip(),
            openai_key=os.getenv("OPENAI_KEY", "").strip(),
            auth_base_url=os.getenv("ADMIN_AUTH_BASE_URL", "http://localhost:8001").strip(),
            auth_supabase_url=os.getenv("AUTH_SUPABASE_URL", "").strip(),
            auth_supabase_key=os.getenv("AUTH_SUPABASE_KEY", "").strip(),
            supabase_url=os.getenv("ADMIN_SUPABASE_URL", os.getenv("AUTH_SUPABASE_URL", "")).strip(),
            supabase_key=os.getenv(
                "ADMIN_SUPABASE_KEY",
                os.getenv("SUPABASE_SERVICE_ROLE_KEY", os.getenv("AUTH_SUPABASE_KEY", "")),
            ).strip(),
            supabase_docs_bucket=os.getenv(
                "ADMIN_SUPABASE_DOCS_BUCKET",
                os.getenv("VITE_SUPABASE_DOCS_BUCKET", "documents"),
            ).strip(),
            supabase_docs_table=os.getenv(
                "ADMIN_SUPABASE_DOCS_TABLE",
                os.getenv("VITE_SUPABASE_DOCS_TABLE", "documents"),
            ).strip(),
            embedding_base_url=os.getenv("ADMIN_EMBEDDING_BASE_URL", "http://localhost:8002").strip(),
            retrieval_base_url=os.getenv("ADMIN_RETRIEVAL_BASE_URL", "http://localhost:8003").strip(),
            generation_base_url=os.getenv("ADMIN_GENERATION_BASE_URL", "http://localhost:8004").strip(),
            ingestion_base_url=os.getenv("ADMIN_INGESTION_BASE_URL", "http://localhost:8005").strip(),
            security_base_url=os.getenv("ADMIN_SECURITY_BASE_URL", "http://localhost:8007").strip(),
            evaluation_base_url=os.getenv("ADMIN_EVALUATION_BASE_URL", "http://localhost:8004").strip(),
            http_timeout_seconds=_parse_float("ADMIN_HTTP_TIMEOUT_SECONDS", 20.0),
            embedding_model=os.getenv("EMBEDDING_MODEL", "text-embedding-3-small").strip(),
            planner_model=os.getenv("ADMIN_PLANNER_MODEL", "gpt-5-mini").strip(),
            planner_enabled=_parse_bool("ADMIN_PLANNER_ENABLED", True),
            planner_temperature=_parse_float("ADMIN_PLANNER_TEMPERATURE", 0.0),
            planner_http_max_retries=int(os.getenv("ADMIN_PLANNER_HTTP_MAX_RETRIES", "2")),
            planner_retry_base_seconds=_parse_float("ADMIN_PLANNER_RETRY_BASE_SECONDS", 0.5),
            require_confirmation_for_mutations=_parse_bool(
                "ADMIN_REQUIRE_CONFIRMATION_FOR_MUTATIONS", True
            ),
            security_fail_closed=_parse_bool("ADMIN_SECURITY_FAIL_CLOSED", False),
        )

    def validate(self) -> None:
        if not self.app_name:
            raise ValueError("ADMIN_APP_NAME is required")
        if not self.app_version:
            raise ValueError("ADMIN_APP_VERSION is required")
        if not self.auth_base_url:
            raise ValueError("ADMIN_AUTH_BASE_URL is required")
        if not self.embedding_base_url:
            raise ValueError("ADMIN_EMBEDDING_BASE_URL is required")
        if not self.retrieval_base_url:
            raise ValueError("ADMIN_RETRIEVAL_BASE_URL is required")
        if not self.generation_base_url:
            raise ValueError("ADMIN_GENERATION_BASE_URL is required")
        if not self.ingestion_base_url:
            raise ValueError("ADMIN_INGESTION_BASE_URL is required")
        if self.http_timeout_seconds <= 0:
            raise ValueError("ADMIN_HTTP_TIMEOUT_SECONDS must be > 0")
        if not self.embedding_model:
            raise ValueError("EMBEDDING_MODEL is required")
        if not self.planner_model:
            raise ValueError("ADMIN_PLANNER_MODEL is required")
