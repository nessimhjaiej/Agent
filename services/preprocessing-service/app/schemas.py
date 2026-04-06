from pydantic import BaseModel, Field


class ProcessSourceRequest(BaseModel):
    source_path: str = Field(..., min_length=1)
    document_id: str | None = Field(default=None, min_length=1)
    source_type: str | None = None
    chunk_strategy: str | None = None
    chunk_size: int | None = Field(default=None, gt=0)
    chunk_overlap: int | None = Field(default=None, ge=0)
    late_size_multiplier: float | None = Field(default=None, gt=0)
    late_overlap_multiplier: float | None = Field(default=None, gt=0)


class ChunkMetadataResponse(BaseModel):
    source_type: str
    source_uri: str
    language: str
    chunk_index: int
    start_char: int
    end_char: int
    char_count: int
    token_count_estimate: int
    chunking_strategy: str
    source_filename: str
    document_checksum: str
    normalization_version: str
    pipeline_version: str
    created_at: str


class ChunkResponse(BaseModel):
    chunk_id: str
    document_id: str
    chunk_text: str
    metadata: ChunkMetadataResponse


class ProcessSourceResponse(BaseModel):
    status: str = "ok"
    chunk_count: int
    chunks: list[ChunkResponse]


class HealthResponse(BaseModel):
    status: str = "ok"
    service: str
    version: str
