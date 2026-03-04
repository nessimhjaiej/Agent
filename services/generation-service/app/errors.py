class GenerationServiceError(Exception):
    pass


class GenerationValidationError(GenerationServiceError):
    pass


class GenerationProviderError(GenerationServiceError):
    pass


class GenerationParseError(GenerationServiceError):
    pass
