from dataclasses import dataclass, field
from typing import Any


@dataclass(slots=True)
class RetrievedChunk:
    chunk_id: str
    document_id: str
    document_name: str
    chunk_text: str
    metadata: dict[str, Any]
    bm25_score: float | None = None
    vector_score: float | None = None
    fusion_score: float | None = None
    rerank_score: float | None = None


@dataclass(slots=True)
class ChatTurn:
    role: str
    content: str


@dataclass(slots=True)
class ChatContext:
    query: str
    retrieved_chunks: list[RetrievedChunk]
    chat_history: list[ChatTurn] = field(default_factory=list)
    session_id: str | None = None


@dataclass(slots=True)
class Citation:
    chunk_id: str
    document_id: str
    document_name: str
    chunk_text: str


@dataclass(slots=True)
class GenerationResult:
    status: str
    answer: str
    citations: list[Citation]
    used_chunk_ids: list[str]
    model: str
