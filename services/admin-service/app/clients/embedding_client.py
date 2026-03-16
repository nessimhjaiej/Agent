from app.clients.base_client import BaseHttpClient
from app.config import Settings


class EmbeddingClient(BaseHttpClient):
    def __init__(self, settings: Settings) -> None:
        super().__init__(
            base_url=settings.embedding_base_url,
            timeout_seconds=settings.http_timeout_seconds,
        )

    def health(self) -> dict:
        return self._get_json("/health")

    def index_document(self, document_id: str, skip_if_embedded: bool = True) -> dict:
        return self._post_json(
            "/embedding/index-document",
            {
                "document_id": document_id,
                "skip_if_embedded": skip_if_embedded,
            },
        )

    def remove_document(self, document_id: str) -> dict:
        return self._post_json(
            "/embedding/remove-document",
            {
                "document_id": document_id,
            },
        )

