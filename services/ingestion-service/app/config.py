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


@dataclass(slots=True)
class Settings:
    app_name: str = "ingestion-service"
    app_version: str = "0.1.0"
    supabase_url: str = ""
    supabase_key: str = ""
    supabase_docs_bucket: str = "documents"
    supabase_docs_table: str = "documents"
    signed_url_ttl_seconds: int = 3600
    http_timeout_seconds: float = 30.0
    security_base_url: str = ""

    @classmethod
    def from_env(cls) -> "Settings":
        defaults = cls()
        return cls(
            app_name=os.getenv("INGESTION_APP_NAME", defaults.app_name),
            app_version=os.getenv("INGESTION_APP_VERSION", defaults.app_version),
            supabase_url=os.getenv("INGESTION_SUPABASE_URL", os.getenv("AUTH_SUPABASE_URL", "")).strip(),
            supabase_key=os.getenv("INGESTION_SUPABASE_KEY", os.getenv("AUTH_SUPABASE_KEY", "")).strip(),
            supabase_docs_bucket=os.getenv("INGESTION_SUPABASE_DOCS_BUCKET", os.getenv("VITE_SUPABASE_DOCS_BUCKET", defaults.supabase_docs_bucket)).strip(),
            supabase_docs_table=os.getenv("INGESTION_SUPABASE_DOCS_TABLE", os.getenv("VITE_SUPABASE_DOCS_TABLE", defaults.supabase_docs_table)).strip(),
            signed_url_ttl_seconds=_parse_int("INGESTION_SIGNED_URL_TTL_SECONDS", defaults.signed_url_ttl_seconds),
            http_timeout_seconds=float(os.getenv("INGESTION_HTTP_TIMEOUT_SECONDS", str(defaults.http_timeout_seconds))),
            security_base_url=os.getenv("SECURITY_BASE_URL", defaults.security_base_url).strip(),
        )

    def validate(self) -> None:
        if not self.app_name:
            raise ValueError("INGESTION_APP_NAME is required")
        if not self.app_version:
            raise ValueError("INGESTION_APP_VERSION is required")
        if not self.supabase_url:
            raise ValueError("INGESTION_SUPABASE_URL or AUTH_SUPABASE_URL is required")
        if not self.supabase_key:
            raise ValueError("INGESTION_SUPABASE_KEY or AUTH_SUPABASE_KEY is required")
        if not self.supabase_docs_bucket:
            raise ValueError("INGESTION_SUPABASE_DOCS_BUCKET is required")
        if not self.supabase_docs_table:
            raise ValueError("INGESTION_SUPABASE_DOCS_TABLE is required")
        if self.signed_url_ttl_seconds <= 0:
            raise ValueError("INGESTION_SIGNED_URL_TTL_SECONDS must be > 0")
        if self.http_timeout_seconds <= 0:
            raise ValueError("INGESTION_HTTP_TIMEOUT_SECONDS must be > 0")
