class IngestionServiceError(Exception):
    pass


class ConfigurationError(IngestionServiceError):
    pass


class UpstreamServiceError(IngestionServiceError):
    pass

