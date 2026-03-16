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

    def delete_document(self, document_id: str) -> dict:
        return self._delete_json(f"/ingestion/documents/{document_id}")
