from pydantic import BaseModel, Field


class HealthResponse(BaseModel):
    status: str = Field(default="ok", description="Health status.")
    service: str = Field(..., description="Service name.")
    version: str = Field(..., description="Service version.")

    model_config = {
        "json_schema_extra": {
            "example": {
                "status": "ok",
                "service": "embedding-service",
                "version": "0.1.0",
            }
        }
    }


class ChunkMetadataInput(BaseModel):
    source_type: str = Field(..., description="Original source type (pdf, txt, md, ...).")
    source_uri: str = Field(..., description="Original source URI/path.")
    language: str = Field(..., description="Detected language code.")
    chunk_index: int = Field(..., ge=0, description="Chunk index in the source document.")
    start_char: int = Field(..., ge=0, description="Start char offset in normalized text.")
    end_char: int = Field(..., ge=0, description="End char offset in normalized text.")
    char_count: int = Field(..., ge=0, description="Chunk length in characters.")
    token_count_estimate: int = Field(..., ge=0, description="Approximate token count.")
    chunking_strategy: str = Field(..., description="Chunking strategy used upstream.")
    source_filename: str = Field(..., description="Source filename.")
    document_checksum: str = Field(..., description="Document checksum from preprocessing pipeline.")
    normalization_version: str = Field(..., description="Normalization algorithm version.")
    pipeline_version: str = Field(..., description="Preprocessing pipeline version.")
    created_at: str = Field(..., description="ISO-8601 timestamp when metadata was created.")


class ChunkInput(BaseModel):
    chunk_id: str = Field(..., min_length=1, description="Unique chunk id, usually '{document_id}:{index}'.")
    document_id: str = Field(..., min_length=1, description="Document identifier.")
    chunk_text: str = Field(..., min_length=1, description="Text content to embed.")
    metadata: ChunkMetadataInput = Field(..., description="Chunk metadata produced by preprocessing.")


class IndexChunksRequest(BaseModel):
    chunks: list[ChunkInput] = Field(..., min_length=1, description="List of chunks to embed and index.")

    model_config = {
        "json_schema_extra": {
            "example": {
                "chunks": [
                    {
                        "chunk_id": "doc-123:0",
                        "document_id": "doc-123",
                        "chunk_text": "This is a sample chunk ready for embedding.",
                        "metadata": {
                            "source_type": "pdf",
                            "source_uri": "shared/raw_data/example.pdf",
                            "language": "en",
                            "chunk_index": 0,
                            "start_char": 0,
                            "end_char": 44,
                            "char_count": 44,
                            "token_count_estimate": 9,
                            "chunking_strategy": "late",
                            "source_filename": "example.pdf",
                            "document_checksum": "a5d2...f1",
                            "normalization_version": "basic-v1",
                            "pipeline_version": "v1",
                            "created_at": "2026-03-02T10:00:00Z",
                        },
                    }
                ]
            }
        }
    }


class IndexedChunkResponse(BaseModel):
    chunk_id: str = Field(..., description="Chunk id returned for this result row.")
    indexed: bool = Field(..., description="True if chunk was successfully indexed.")
    reason: str | None = Field(default=None, description="Optional reason for failure/skipped status.")


class IndexChunksResponse(BaseModel):
    status: str = Field(default="ok", description="Operation status.")
    collection: str = Field(..., description="Weaviate collection name.")
    total_count: int = Field(..., ge=0, description="Total chunks received in this request.")
    indexed_count: int = Field(..., ge=0, description="Number of chunks successfully indexed.")
    results: list[IndexedChunkResponse] = Field(..., description="Per-chunk result details.")

    model_config = {
        "json_schema_extra": {
            "example": {
                "status": "ok",
                "collection": "Chunk",
                "total_count": 2,
                "indexed_count": 1,
                "results": [
                    {"chunk_id": "doc-123:0", "indexed": True, "reason": "upsert_create"},
                    {
                        "chunk_id": "doc-123:0",
                        "indexed": False,
                        "reason": "duplicate_chunk_id_in_request",
                    },
                ],
            }
        }
    }


class IndexDocumentRequest(BaseModel):
    document_id: str = Field(..., min_length=1, description="Supabase document row id.")
    skip_if_embedded: bool = Field(default=True, description="Skip work if the document is already marked embedded.")


class IndexDocumentResponse(BaseModel):
    status: str
    document_id: str
    storage_path: str
    chunks_count: int
    indexed_count: int
    embedded: bool
    message: str | None = None


class RemoveDocumentRequest(BaseModel):
    document_id: str = Field(..., min_length=1, description="Supabase document row id.")


class RemoveDocumentResponse(BaseModel):
    status: str
    document_id: str
    storage_path: str
    matched_objects_count: int
    deleted_count: int
