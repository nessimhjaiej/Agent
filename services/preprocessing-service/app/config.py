import os
from dataclasses import dataclass


@dataclass(slots=True)
class Settings:
    app_name: str = "preprocessing-service"
    app_version: str = "0.1.0"
    chunk_strategy: str = "overlap"
    chunk_size: int = 800
    chunk_overlap: int = 120
    pipeline_version: str = "v1"

    @classmethod
    def from_env(cls) -> "Settings":
        return cls(
            app_name=os.getenv("PREPROCESSING_APP_NAME", "preprocessing-service"),
            app_version=os.getenv("PREPROCESSING_APP_VERSION", "0.1.0"),
            chunk_strategy=os.getenv("PREPROCESSING_CHUNK_STRATEGY", "overlap"),
            chunk_size=int(os.getenv("PREPROCESSING_CHUNK_SIZE", "800")),
            chunk_overlap=int(os.getenv("PREPROCESSING_CHUNK_OVERLAP", "120")),
            pipeline_version=os.getenv("PREPROCESSING_PIPELINE_VERSION", "v1"),
        )

