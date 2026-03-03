from rankers.base import BaseRanker
from rankers.cross_encoder import CrossEncoderRanker
from rankers.identity import IdentityRanker
from rankers.llm_batch import LLMBatchRanker


class RankerFactory:
    _registry: dict[str, type[BaseRanker]] = {
        "none": IdentityRanker,
        "cross_encoder": CrossEncoderRanker,
        "llm_batch": LLMBatchRanker,
    }

    @classmethod
    def create(cls, ranker_type: str, enabled: bool) -> BaseRanker:
        if not enabled:
            return IdentityRanker()

        key = ranker_type.strip().lower()
        ranker_cls = cls._registry.get(key)
        if not ranker_cls:
            supported = ", ".join(sorted(cls._registry))
            raise ValueError(f"Unknown ranker type '{ranker_type}'. Supported: {supported}")
        return ranker_cls()
