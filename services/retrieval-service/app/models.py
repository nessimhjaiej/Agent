from dataclasses import dataclass, field
from typing import Any


@dataclass(slots=True)
class CandidateChunk:
    chunk_id: str
    document_id: str
    chunk_text: str
    metadata: dict[str, Any]
    bm25_score: float | None = None
    vector_score: float | None = None
    fusion_score: float | None = None
    rerank_score: float | None = None
    rank_bm25: int | None = None
    rank_vector: int | None = None


@dataclass(slots=True)
class QueryContext:
    query: str
    top_k_retrieve: int
    top_k_return: int
    mode: str = "hybrid"
    filters: dict[str, Any] = field(default_factory=dict)
    fusion_type: str = "alpha"
    alpha: float = 0.7
    rrf_k: int = 60
    rerank_type: str = "none"
    rerank_enabled: bool = False
    rerank_top_n: int = 20
