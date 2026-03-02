class EmbeddingServiceError(Exception):
    pass


class ConfigurationError(EmbeddingServiceError):
    pass


class EmbeddingProviderError(EmbeddingServiceError):
    pass


class EmbeddingProviderRateLimitError(EmbeddingProviderError):
    pass


class VectorStoreError(EmbeddingServiceError):
    pass
