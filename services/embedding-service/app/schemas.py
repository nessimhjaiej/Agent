from pydantic import BaseModel, Field


class HealthResponse(BaseModel):
    status: str = "ok"
    service: str
    version: str


class ChunkMetadataInput(BaseModel):
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


class ChunkInput(BaseModel):
    chunk_id: str = Field(..., min_length=1)
    document_id: str = Field(..., min_length=1)
    chunk_text: str = Field(..., min_length=1)
    metadata: ChunkMetadataInput


class IndexChunksRequest(BaseModel):
    chunks: list[ChunkInput] = Field(..., min_length=1)


class IndexedChunkResponse(BaseModel):
    chunk_id: str
    indexed: bool
    reason: str | None = None


class IndexChunksResponse(BaseModel):
    status: str = "ok"
    collection: str
    total_count: int
    indexed_count: int
    results: list[IndexedChunkResponse]
