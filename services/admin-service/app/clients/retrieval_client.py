from app.clients.base_client import BaseHttpClient
from app.config import Settings


class RetrievalClient(BaseHttpClient):
    def __init__(self, settings: Settings) -> None:
        super().__init__(
            base_url=settings.retrieval_base_url,
            timeout_seconds=settings.http_timeout_seconds,
        )

    def health(self) -> dict:
        return self._get_json("/health")

