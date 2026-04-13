from pydantic import BaseModel, Field


class HealthResponse(BaseModel):
    status: str = Field(default="ok", pattern="^(ok)$")
    service: str
    version: str


class RetrievedChunkInput(BaseModel):
    chunk_id: str = Field(..., min_length=1)
    document_id: str = Field(..., min_length=1)
    document_name: str = Field(..., min_length=1)
    chunk_text: str = Field(..., min_length=1)
    metadata: dict = Field(default_factory=dict)
    bm25_score: float | None = None
    vector_score: float | None = None
    fusion_score: float | None = None
    rerank_score: float | None = None


class ChatTurnInput(BaseModel):
    role: str = Field(..., pattern="^(user|assistant)$")
    content: str = Field(..., min_length=1)


class ChatRequest(BaseModel):
    query: str = Field(..., min_length=1)
    retrieved_chunks: list[RetrievedChunkInput] = Field(..., min_length=1)
    chat_history: list[ChatTurnInput] = Field(default_factory=list)
    session_id: str | None = None


class CitationResponse(BaseModel):
    chunk_id: str
    document_id: str
    document_name: str
    chunk_text: str
    storage_path: str | None = None


class ChatResponse(BaseModel):
    status: str = Field(default="ok", pattern="^(ok|degraded)$")
    session_id: str | None = None
    query: str
    answer: str
    citations: list[CitationResponse]
    used_chunk_ids: list[str]
    model: str


class RetrievalFusionOptions(BaseModel):
    type: str | None = Field(default=None, pattern="^(alpha|rrf)$")
    alpha: float | None = Field(default=None, ge=0.0, le=1.0)
    rrf_k: int | None = Field(default=None, ge=1)


class RetrievalRerankOptions(BaseModel):
    enabled: bool | None = None
    type: str | None = Field(default=None, pattern="^(none|cross_encoder|llm_batch)$")
    top_n: int | None = Field(default=None, ge=1)
    batch_size: int | None = Field(default=None, ge=1)


class AskRequest(BaseModel):
    query: str = Field(..., min_length=1)
    mode: str = Field(default="hybrid", pattern="^(bm25|vector|hybrid)$")
    top_k_retrieve: int | None = Field(default=None, ge=1)
    top_k_return: int | None = Field(default=None, ge=1)
    filters: dict = Field(default_factory=dict)
    fusion: RetrievalFusionOptions | None = None
    rerank: RetrievalRerankOptions | None = None
    chat_history: list[ChatTurnInput] = Field(default_factory=list)
    session_id: str | None = None


class AskResponse(ChatResponse):
    retrieval_count: int
    returned_count: int
    retrieval_mode: str
    fusion_type: str
    rerank_type: str


class TranscriptionResponse(BaseModel):
    status: str = Field(default="ok", pattern="^(ok)$")
    text: str = Field(..., min_length=1)
    model: str = Field(..., min_length=1)
    filename: str = Field(..., min_length=1)


class EvaluationRunRequest(BaseModel):
    dataset_path: str = Field(default="evals/sample_eval_dataset.json", min_length=1)


class EvaluationReportSummaryResponse(BaseModel):
    report_id: str = Field(..., min_length=1)
    filename: str = Field(..., min_length=1)
    generated_at_utc: str
    sample_count: int = Field(..., ge=0)
    dataset_path: str
    summary: dict[str, float] = Field(default_factory=dict)


class EvaluationRunResponse(BaseModel):
    status: str = Field(default="ok", pattern="^(ok)$")
    report: EvaluationReportSummaryResponse


class EvaluationListResponse(BaseModel):
    status: str = Field(default="ok", pattern="^(ok)$")
    reports: list[EvaluationReportSummaryResponse] = Field(default_factory=list)


class EvaluationCompareRequest(BaseModel):
    baseline_report_id: str = Field(..., min_length=1)
    candidate_report_id: str = Field(..., min_length=1)


class EvaluationMetricDelta(BaseModel):
    baseline: float | None = None
    candidate: float | None = None
    delta: float | None = None


class EvaluationCompareResponse(BaseModel):
    status: str = Field(default="ok", pattern="^(ok)$")
    baseline_report_id: str = Field(..., min_length=1)
    candidate_report_id: str = Field(..., min_length=1)
    metrics: dict[str, EvaluationMetricDelta] = Field(default_factory=dict)
