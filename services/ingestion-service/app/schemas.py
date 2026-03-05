from pydantic import BaseModel, Field


class HealthResponse(BaseModel):
    status: str = Field(default="ok")
    service: str
    version: str


class RunIngestionRequest(BaseModel):
    raw_dir: str | None = Field(default=None, min_length=1)
    source_root_in_preprocessing: str | None = Field(default=None, min_length=1)
    preprocessing_base_url: str | None = Field(default=None, min_length=1)
    embedding_base_url: str | None = Field(default=None, min_length=1)
    embedding_batch_size: int | None = Field(default=None, gt=0)
    recursive: bool | None = None
    patterns: list[str] | None = None
    dry_run: bool = False


class IngestionDocumentResponse(BaseModel):
    file_path: str
    source_path: str
    chunks_count: int
    indexed_count: int
    status: str
    error: str | None = None


class RunIngestionResponse(BaseModel):
    status: str = "ok"
    documents_processed: int
    documents_failed: int
    chunks_total: int
    chunks_indexed: int
    failed_files: list[str]
    results: list[IngestionDocumentResponse]


class IndexDocumentRequest(BaseModel):
    source_url: str | None = Field(default=None, min_length=1)
    source_path: str | None = Field(default=None, min_length=1)
    target_relative_path: str = Field(..., min_length=1)
    source_root_in_preprocessing: str | None = Field(default=None, min_length=1)
    preprocessing_base_url: str | None = Field(default=None, min_length=1)
    embedding_base_url: str | None = Field(default=None, min_length=1)
    embedding_batch_size: int | None = Field(default=None, gt=0)
    skip_if_exists: bool = True


class IndexDocumentResponse(BaseModel):
    status: str
    source_path: str
    exists_in_weaviate: bool
    indexed: bool
    chunks_count: int
    indexed_count: int
    message: str | None = None


class CheckDocumentsRequest(BaseModel):
    target_relative_paths: list[str] = Field(..., min_length=1)


class CheckDocumentResult(BaseModel):
    target_relative_path: str
    source_path: str
    exists_in_weaviate: bool


class CheckDocumentsResponse(BaseModel):
    status: str = "ok"
    total_count: int
    exists_count: int
    results: list[CheckDocumentResult]
