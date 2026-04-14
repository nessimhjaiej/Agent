from pydantic import BaseModel, Field


class HealthResponse(BaseModel):
    status: str = "ok"
    service: str
    version: str


class FusionOptions(BaseModel):
    type: str | None = Field(default=None, pattern="^(alpha|rrf)$", description="alpha or rrf")
    alpha: float | None = Field(default=None, ge=0.0, le=1.0)
    rrf_k: int | None = Field(default=None, ge=1)


class RerankOptions(BaseModel):
    enabled: bool | None = None
    type: str | None = Field(
        default=None, pattern="^(none|cross_encoder|llm_batch)$", description="none, cross_encoder, llm_batch"
    )
    top_n: int | None = Field(default=None, ge=1)
    batch_size: int | None = Field(default=None, ge=1)


class SearchRequest(BaseModel):
    query: str = Field(..., min_length=1)
    mode: str = Field(default="hybrid", pattern="^(bm25|vector|hybrid)$")
    top_k_retrieve: int | None = Field(default=None, ge=1)
    top_k_return: int | None = Field(default=None, ge=1)
    filters: dict = Field(default_factory=dict)
    fusion: FusionOptions | None = None
    rerank: RerankOptions | None = None


class SearchChunkResult(BaseModel):
    chunk_id: str
    document_id: str
    document_name: str
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


class RetrievalConfigResponse(BaseModel):
    status: str = "ok"
    scope: str = "retrieval"
    config: dict[str, str | int]
    sources: dict[str, str]


class UpdateRetrievalConfigRequest(BaseModel):
    default_ranker_type: str | None = Field(default=None, pattern="^(none|cross_encoder|llm_batch)$")
    top_k_retrieve: int | None = Field(default=None, ge=1)
    top_k_return: int | None = Field(default=None, ge=1)


class UpdateRetrievalConfigResponse(BaseModel):
    status: str = "ok"
    scope: str = "retrieval"
    updated: dict[str, str | int]
    applied_via: str
    restart_required: bool = False


class RerankerMethodItem(BaseModel):
    name: str
    exists: bool = True
    implemented: bool


class RetrievalRerankersResponse(BaseModel):
    status: str = "ok"
    scope: str = "retrieval"
    current_default_ranker_type: str
    methods: list[RerankerMethodItem]
