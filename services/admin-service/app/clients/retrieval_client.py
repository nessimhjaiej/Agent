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

    def search(
        self,
        query: str,
        mode: str = "hybrid",
        top_k_retrieve: int = 12,
        top_k_return: int = 12,
        filters: dict | None = None,
    ) -> dict:
        return self._post_json(
            "/retrieval/search",
            {
                "query": query,
                "mode": mode,
                "top_k_retrieve": top_k_retrieve,
                "top_k_return": top_k_return,
                "filters": filters or {},
            },
        )
