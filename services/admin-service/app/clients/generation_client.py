from app.clients.base_client import BaseHttpClient
from app.config import Settings


class GenerationClient(BaseHttpClient):
    def __init__(self, settings: Settings) -> None:
        super().__init__(
            base_url=settings.generation_base_url,
            timeout_seconds=settings.http_timeout_seconds,
        )

    def health(self) -> dict:
        return self._get_json("/health")

    def ask(self, query: str, chat_history: list[dict]) -> dict:
        return self._post_json(
            "/generation/ask",
            {
                "query": query,
                "chat_history": chat_history,
            },
        )
