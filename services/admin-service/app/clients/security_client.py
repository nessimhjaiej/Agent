from app.config import Settings


class SecurityClient:
    def __init__(self, settings: Settings) -> None:
        self._settings = settings
        self.events: list[dict] = []

    def publish_event(self, event: dict) -> None:
        self.events.append(event)

