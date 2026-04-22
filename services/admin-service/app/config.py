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


@dataclass(slots=True)
class Settings:
    app_name: str = "admin-service"
    app_version: str = "0.1.0"
    project_root: Path = _PROJECT_ROOT
    openai_key: str = ""
    admin_model: str = "gpt-4o"
    session_store_path: str = str(_PROJECT_ROOT / "services" / "admin-service" / "data" / "sessions.json")
    max_iterations: int = 8
    max_tool_calls: int = 8
    auth_base_url: str = "http://localhost:8001"
    auth_validation_timeout_seconds: float = 5.0
    security_base_url: str = ""
    ingestion_base_url: str = "http://localhost:8005"
    preprocessing_base_url: str = "http://localhost:8000"
    embedding_base_url: str = "http://localhost:8002"
    generation_base_url: str = "http://localhost:8004"
    retrieval_base_url: str = "http://localhost:8003"

    @classmethod
    def from_env(cls) -> "Settings":
        return cls(
            app_name=os.getenv("ADMIN_APP_NAME", "admin-service"),
            app_version=os.getenv("ADMIN_APP_VERSION", "0.1.0"),
            project_root=_PROJECT_ROOT,
            openai_key=os.getenv("OPENAI_KEY", ""),
            admin_model=os.getenv("ADMIN_MODEL", os.getenv("GENERATION_MODEL", "gpt-4o")),
            session_store_path=os.getenv(
                "ADMIN_SESSION_STORE_PATH",
                str(_PROJECT_ROOT / "services" / "admin-service" / "data" / "sessions.json"),
            ),
            max_iterations=_parse_int("ADMIN_MAX_ITERATIONS", 8),
            max_tool_calls=_parse_int("ADMIN_MAX_TOOL_CALLS", 8),
            auth_base_url=os.getenv("AUTH_BASE_URL", "http://localhost:8001"),
            auth_validation_timeout_seconds=_parse_float("ADMIN_AUTH_VALIDATION_TIMEOUT_SECONDS", 5.0),
            security_base_url=os.getenv("SECURITY_BASE_URL", ""),
            ingestion_base_url=os.getenv("INGESTION_BASE_URL", "http://localhost:8005"),
            preprocessing_base_url=os.getenv("PREPROCESSING_BASE_URL", "http://localhost:8000"),
            embedding_base_url=os.getenv("EMBEDDING_BASE_URL", "http://localhost:8002"),
            generation_base_url=os.getenv("GENERATION_BASE_URL", "http://localhost:8004"),
            retrieval_base_url=os.getenv("RETRIEVAL_BASE_URL", "http://localhost:8003"),
        )
