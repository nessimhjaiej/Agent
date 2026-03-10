from app.clients.base_client import BaseHttpClient
from app.config import Settings


class IngestionClient(BaseHttpClient):
    def __init__(self, settings: Settings) -> None:
        super().__init__(
            base_url=settings.ingestion_base_url,
            timeout_seconds=settings.http_timeout_seconds,
        )

    def health(self) -> dict:
        return self._get_json("/health")

    def remove_document_chunks(self, target_relative_paths: list[str]) -> dict:
        return self._post_json(
            "/ingestion/remove-document-chunks",
            {"target_relative_paths": target_relative_paths},
        )

    def index_document(self, target_relative_path: str, skip_if_exists: bool = True) -> dict:
        return self._post_json(
            "/ingestion/index-document",
            {
                "target_relative_path": target_relative_path,
                "skip_if_exists": skip_if_exists,
            },
        )

    def run_ingestion(
        self,
        raw_dir: str,
        source_root_in_preprocessing: str,
        recursive: bool = True,
        patterns: list[str] | None = None,
        dry_run: bool = False,
    ) -> dict:
        payload = {
            "raw_dir": raw_dir,
            "source_root_in_preprocessing": source_root_in_preprocessing,
            "recursive": recursive,
            "dry_run": dry_run,
        }
        if patterns:
            payload["patterns"] = patterns
        return self._post_json("/ingestion/run", payload)
