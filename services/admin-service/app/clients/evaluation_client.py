from app.config import Settings


class EvaluationClient:
    def __init__(self, settings: Settings) -> None:
        self._settings = settings

