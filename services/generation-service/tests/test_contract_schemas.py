from pathlib import Path
import importlib
import sys

import pytest
from pydantic import ValidationError

SERVICE_ROOT = Path(__file__).resolve().parents[1]
if str(SERVICE_ROOT) not in sys.path:
    sys.path.insert(0, str(SERVICE_ROOT))


def _load_chat_request():  # noqa: ANN201
    for name in list(sys.modules):
        if name == "app" or name.startswith("app."):
            del sys.modules[name]
    if str(SERVICE_ROOT) in sys.path:
        sys.path.remove(str(SERVICE_ROOT))
    sys.path.insert(0, str(SERVICE_ROOT))
    module = importlib.import_module("app.schemas")
    return module.ChatRequest


def _load_ask_request():  # noqa: ANN201
    for name in list(sys.modules):
        if name == "app" or name.startswith("app."):
            del sys.modules[name]
    if str(SERVICE_ROOT) in sys.path:
        sys.path.remove(str(SERVICE_ROOT))
    sys.path.insert(0, str(SERVICE_ROOT))
    module = importlib.import_module("app.schemas")
    return module.AskRequest


def _chunk() -> dict:
    return {
        "chunk_id": "doc-1:0",
        "document_id": "doc-1",
        "document_name": "doc-1.pdf",
        "chunk_text": "This is the chunk text.",
        "metadata": {"source_filename": "doc-1.pdf"},
        "fusion_score": 0.8,
        "rerank_score": 0.9,
    }


def test_chat_request_accepts_expected_contract() -> None:
    ChatRequest = _load_chat_request()
    payload = ChatRequest(
        query="Explain PSD2 obligations.",
        retrieved_chunks=[_chunk()],
        chat_history=[
            {"role": "user", "content": "What is PSD2?"},
            {"role": "assistant", "content": "PSD2 is an EU payments directive."},
        ],
        session_id="session-123",
    )

    assert payload.query == "Explain PSD2 obligations."
    assert payload.retrieved_chunks[0].document_name == "doc-1.pdf"
    assert payload.chat_history[0].role == "user"


def test_chat_request_requires_at_least_one_chunk() -> None:
    ChatRequest = _load_chat_request()
    with pytest.raises(ValidationError):
        _ = ChatRequest(query="q", retrieved_chunks=[])


def test_chat_request_rejects_invalid_chat_role() -> None:
    ChatRequest = _load_chat_request()
    with pytest.raises(ValidationError):
        _ = ChatRequest(
            query="q",
            retrieved_chunks=[_chunk()],
            chat_history=[{"role": "system", "content": "bad role"}],
        )


def test_ask_request_accepts_retrieval_controls() -> None:
    AskRequest = _load_ask_request()
    payload = AskRequest(
        query="Explain obligations.",
        mode="hybrid",
        top_k_retrieve=5,
        top_k_return=3,
        filters={"language": "en"},
        fusion={"type": "rrf", "rrf_k": 60},
        rerank={"enabled": True, "type": "cross_encoder", "top_n": 5},
    )

    assert payload.mode == "hybrid"
    assert payload.fusion.type == "rrf"
    assert payload.rerank.type == "cross_encoder"
