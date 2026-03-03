class RetrievalServiceError(Exception):
    pass


class RetrievalValidationError(RetrievalServiceError):
    pass


class RetrievalProviderError(RetrievalServiceError):
    pass
