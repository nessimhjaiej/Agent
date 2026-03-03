from app.models import CandidateChunk, QueryContext
from retrievers.bm25 import BM25Retriever
from retrievers.vector import VectorRetriever


class HybridRetriever:
    def __init__(
        self,
        bm25_retriever: BM25Retriever | None = None,
        vector_retriever: VectorRetriever | None = None,
    ) -> None:
        self._bm25 = bm25_retriever or BM25Retriever()
        self._vector = vector_retriever or VectorRetriever()

    def retrieve_bm25(self, ctx: QueryContext) -> list[CandidateChunk]:
        return self._bm25.retrieve(ctx)

    def retrieve_vector(self, ctx: QueryContext) -> list[CandidateChunk]:
        return self._vector.retrieve(ctx)

    def retrieve(self, ctx: QueryContext) -> tuple[list[CandidateChunk], list[CandidateChunk]]:
        mode = ctx.mode.strip().lower()
        if mode == "bm25":
            return self.retrieve_bm25(ctx), []
        if mode == "vector":
            return [], self.retrieve_vector(ctx)
        if mode == "hybrid":
            return self.retrieve_bm25(ctx), self.retrieve_vector(ctx)
        raise ValueError("Invalid retrieval mode. Supported: bm25, vector, hybrid")
