from chunking.base import BaseChunker
from chunking.late import LateChunker
from chunking.overlap import OverlapChunker
from chunking.semantic import SemanticChunker
from chunking.sentence import SentenceChunker


class ChunkerFactory:
    _registry: dict[str, type[BaseChunker]] = {
        "overlap": OverlapChunker,
        "semantic": SemanticChunker,
        "late": LateChunker,
        "sentence": SentenceChunker,
    }

    @classmethod
    def create(cls, strategy: str) -> BaseChunker:
        key = strategy.strip().lower()
        chunker_cls = cls._registry.get(key)
        if not chunker_cls:
            supported = ", ".join(sorted(cls._registry))
            raise ValueError(f"Unknown chunking strategy '{strategy}'. Supported: {supported}")
        return chunker_cls()

