from pydantic import BaseModel, Field


class HealthResponse(BaseModel):
    status: str = "ok"
    service: str
    version: str


class FusionOptions(BaseModel):
    type: str = Field(default="alpha", description="alpha or rrf")
    alpha: float = Field(default=0.7, ge=0.0, le=1.0)
    rrf_k: int = Field(default=60, ge=1)


class RerankOptions(BaseModel):
    enabled: bool = False
    type: str = Field(default="none", description="none, cross_encoder, llm_batch")
    top_n: int = Field(default=20, ge=1)
    batch_size: int = Field(default=16, ge=1)


class SearchRequest(BaseModel):
    query: str = Field(..., min_length=1)
    mode: str = Field(default="hybrid", pattern="^(bm25|vector|hybrid)$")
    top_k_retrieve: int = Field(default=5, ge=1)
    top_k_return: int = Field(default=3, ge=1)
    filters: dict = Field(default_factory=dict)
    fusion: FusionOptions = Field(default_factory=FusionOptions)
    rerank: RerankOptions = Field(default_factory=RerankOptions)


class SearchChunkResult(BaseModel):
    chunk_id: str
    document_id: str
    chunk_text: str
    metadata: dict
    bm25_score: float | None = None
    vector_score: float | None = None
    fusion_score: float | None = None
    rerank_score: float | None = None


class SearchDocumentResult(BaseModel):
    document_id: str
    chunk_ids: list[str]
    hit_count: int


class SearchResponse(BaseModel):
    status: str = "ok"
    query: str
    mode: str
    retrieval_count: int
    returned_count: int
    fusion_type: str
    rerank_type: str
    chunks: list[SearchChunkResult]
    documents: list[SearchDocumentResult]
