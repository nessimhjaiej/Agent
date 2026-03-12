from dataclasses import dataclass


@dataclass(slots=True)
class ChunkMetadata:
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


@dataclass(slots=True)
class Chunk:
    chunk_id: str
    document_id: str
    chunk_text: str
    metadata: ChunkMetadata


@dataclass(slots=True)
class IndexChunkResult:
    chunk_id: str
    indexed: bool
    reason: str | None = None


@dataclass(slots=True)
class IndexDocumentResult:
    status: str
    document_id: str
    storage_path: str
    chunks_count: int
    indexed_count: int
    embedded: bool
    message: str | None = None


@dataclass(slots=True)
class RemoveDocumentResult:
    status: str
    document_id: str
    storage_path: str
    matched_objects_count: int
    deleted_count: int
