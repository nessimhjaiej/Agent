import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv


_PROJECT_ROOT = Path(__file__).resolve().parents[3]
load_dotenv(_PROJECT_ROOT / ".env", override=True)
load_dotenv(_PROJECT_ROOT / ".env.local", override=True)


@dataclass(slots=True)
class Settings:
    app_name: str = "preprocessing-service"
    app_version: str = "0.1.0"
    chunk_strategy: str = "late"
    chunk_size: int = 800
    chunk_overlap: int = 120
    pipeline_version: str = "v1"
    rate_limit_requests: int = 60
    rate_limit_window_seconds: int = 60
    max_request_size_bytes: int = 1_048_576
    security_base_url: str = ""

    @classmethod
    def from_env(cls) -> "Settings":
        defaults = cls()
        return cls(
            app_name=os.getenv("PREPROCESSING_APP_NAME", "preprocessing-service"),
            app_version=os.getenv("PREPROCESSING_APP_VERSION", "0.1.0"),
            chunk_strategy=defaults.chunk_strategy,
            chunk_size=defaults.chunk_size,
            chunk_overlap=defaults.chunk_overlap,
            pipeline_version=os.getenv("PREPROCESSING_PIPELINE_VERSION", defaults.pipeline_version),
            rate_limit_requests=int(os.getenv("PREPROCESSING_RATE_LIMIT_REQUESTS", "60")),
            rate_limit_window_seconds=int(os.getenv("PREPROCESSING_RATE_LIMIT_WINDOW_SECONDS", "60")),
            max_request_size_bytes=int(os.getenv("PREPROCESSING_MAX_REQUEST_SIZE_BYTES", "1048576")),
            security_base_url=os.getenv("SECURITY_BASE_URL", defaults.security_base_url),
        )
