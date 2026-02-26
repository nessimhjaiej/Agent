from dataclasses import dataclass, field
from datetime import datetime, timezone
from hashlib import sha256
from pathlib import Path
from typing import Any


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def text_sha256(value: str) -> str:
    return sha256(value.encode("utf-8")).hexdigest()


@dataclass(slots=True)
class RawDocument:
    document_id: str
    source_type: str
    source_uri: str
    raw_text: str
    checksum: str
    created_at: str = field(default_factory=utc_now_iso)

    @property
    def source_filename(self) -> str:
        return Path(self.source_uri).name


@dataclass(slots=True)
class NormalizedDocument:
    document_id: str
    source_type: str
    source_uri: str
    normalized_text: str
    checksum: str
    language: str = "und"
    normalization_version: str = "v1"
    created_at: str = field(default_factory=utc_now_iso)


@dataclass(slots=True)
class ChunkingContext:
    chunk_size: int = 800
    chunk_overlap: int = 120
    tokenizer_name: str | None = None
    max_tokens_per_chunk: int | None = None
    strategy_params: dict[str, Any] = field(default_factory=dict)


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
    pipeline_version: str = "v1"
    created_at: str = field(default_factory=utc_now_iso)


@dataclass(slots=True)
class ChunkRecord:
    chunk_id: str
    document_id: str
    chunk_text: str
    metadata: ChunkMetadata
