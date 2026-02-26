from abc import ABC, abstractmethod

from app.models import RawDocument


class BaseInputAdapter(ABC):
    @property
    @abstractmethod
    def name(self) -> str:
        raise NotImplementedError

    @abstractmethod
    def load(self, source_path: str) -> RawDocument:
        raise NotImplementedError

