class ModelFallbackPlan:
    def __init__(
        self,
        primary_provider: str,
        primary_model: str,
        fallback_enabled: bool,
        fallback_provider: str,
        fallback_model: str,
    ) -> None:
        self._primary_provider = primary_provider
        self._primary_model = primary_model
        self._fallback_enabled = fallback_enabled
        self._fallback_provider = fallback_provider
        self._fallback_model = fallback_model

    def sequence(self) -> list[tuple[str, str]]:
        attempts = [(self._primary_provider, self._primary_model)]
        fallback_provider = self._fallback_provider.strip().lower()
        fallback = self._fallback_model.strip()
        same_target = (
            fallback_provider == self._primary_provider.strip().lower()
            and fallback == self._primary_model
        )
        if self._fallback_enabled and fallback and fallback_provider and not same_target:
            attempts.append((fallback_provider, fallback))
        return attempts
