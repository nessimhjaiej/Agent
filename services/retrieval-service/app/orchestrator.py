from app.models import CandidateChunk, QueryContext
from fusion.factory import FusionFactory
from rankers.factory import RankerFactory
from retrievers.hybrid import HybridRetriever


class RetrievalOrchestrator:
    def __init__(
        self,
        retriever: HybridRetriever | None = None,
        fusion_factory: type[FusionFactory] = FusionFactory,
        ranker_factory: type[RankerFactory] = RankerFactory,
    ) -> None:
        self._retriever = retriever or HybridRetriever()
        self._fusion_factory = fusion_factory
        self._ranker_factory = ranker_factory

    def search(self, ctx: QueryContext) -> list[CandidateChunk]:
        bm25_candidates, vector_candidates = self._retriever.retrieve(ctx)

        fusion = self._fusion_factory.create(ctx.fusion_type)
        fused = fusion.combine(bm25_candidates, vector_candidates, ctx)

        ranker = self._ranker_factory.create(ctx.rerank_type, enabled=ctx.rerank_enabled)
        return ranker.rank(ctx.query, fused, top_n=ctx.rerank_top_n)
