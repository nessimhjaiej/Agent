from abc import ABC, abstractmethod

from app.models import NormalizedDocument, RawDocument


class BaseNormalizer(ABC):
    @property
    @abstractmethod
    def name(self) -> str:
        raise NotImplementedError

    @abstractmethod
    def normalize(self, raw_document: RawDocument) -> NormalizedDocument:
        raise NotImplementedError

