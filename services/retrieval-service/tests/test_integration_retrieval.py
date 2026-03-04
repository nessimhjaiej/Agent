from pathlib import Path
import os
import sys
from uuid import uuid4

import httpx
import pytest
from dotenv import load_dotenv
from fastapi.testclient import TestClient

SERVICE_ROOT = Path(__file__).resolve().parents[1]
REPO_ROOT = Path(__file__).resolve().parents[3]
if str(SERVICE_ROOT) not in sys.path:
    sys.path.insert(0, str(SERVICE_ROOT))

load_dotenv(REPO_ROOT / ".env", override=True)

from app.config import Settings  # noqa: E402
from app.main import create_app  # noqa: E402


def _weaviate_ready(base_url: str) -> bool:
    try:
        response = httpx.get(f"{base_url.rstrip('/')}/v1/.well-known/ready", timeout=5.0)
    except httpx.HTTPError:
        return False
    return response.status_code == 200


def _schema_has_chunk(base_url: str, collection: str) -> bool:
    try:
        response = httpx.get(f"{base_url.rstrip('/')}/v1/schema", timeout=10.0)
    except httpx.HTTPError:
        return False
    if response.status_code != 200:
        return False
    classes = response.json().get("classes", [])
    names = {item.get("class") for item in classes if isinstance(item, dict)}
    return collection in names


def _insert_seed_chunk(
    base_url: str,
    collection: str,
    doc_id: str,
    chunk_id: str,
    token: str,
    embedding_model: str,
) -> None:
    body = {
        "class": collection,
        "id": str(uuid4()),
        "properties": {
            "chunk_id": chunk_id,
            "document_id": doc_id,
            "chunk_text": f"{token} retrieval integration seed text",
            "source_type": "txt",
            "source_uri": "c:/tmp/retrieval-seed.txt",
            "source_filename": "retrieval-seed.txt",
            "language": "en",
            "chunk_index": 0,
            "start_char": 0,
            "end_char": 48,
            "char_count": 48,
            "token_count_estimate": 6,
            "chunking_strategy": "late",
            "embedding_model": embedding_model,
            "document_checksum": "retrieval-it-checksum",
            "normalization_version": "basic-v1",
            "pipeline_version": "v1",
            "created_at": "2026-03-03T00:00:00Z",
        },
        # text-embedding-3-small default dimension
        "vector": [0.001] * 1536,
    }
    response = httpx.post(f"{base_url.rstrip('/')}/v1/objects", json=body, timeout=20.0)
    assert response.status_code in {200, 201}, response.text


def _insert_seed_chunks(
    base_url: str,
    collection: str,
    doc_id: str,
    token: str,
    embedding_model: str,
    count: int = 2,
) -> list[str]:
    chunk_ids: list[str] = []
    for idx in range(count):
        chunk_id = f"{doc_id}:{idx}"
        body = {
            "class": collection,
            "id": str(uuid4()),
            "properties": {
                "chunk_id": chunk_id,
                "document_id": doc_id,
                "chunk_text": f"{token} retrieval rerank seed text variant {idx}",
                "source_type": "txt",
                "source_uri": "c:/tmp/retrieval-seed.txt",
                "source_filename": "retrieval-seed.txt",
                "language": "en",
                "chunk_index": idx,
                "start_char": idx * 50,
                "end_char": (idx + 1) * 50,
                "char_count": 50,
                "token_count_estimate": 8,
                "chunking_strategy": "late",
                "embedding_model": embedding_model,
                "document_checksum": "retrieval-it-checksum",
                "normalization_version": "basic-v1",
                "pipeline_version": "v1",
                "created_at": "2026-03-03T00:00:00Z",
            },
            "vector": [0.001 + idx * 0.0001] * 1536,
        }
        response = httpx.post(f"{base_url.rstrip('/')}/v1/objects", json=body, timeout=20.0)
        assert response.status_code in {200, 201}, response.text
        chunk_ids.append(chunk_id)
    return chunk_ids


@pytest.mark.integration
def test_retrieval_api_modes_end_to_end() -> None:
    settings = Settings.from_env()
    if not settings.openai_key:
        pytest.skip("OPENAI_KEY is required for retrieval integration test")
    if not _weaviate_ready(settings.weaviate_http_url):
        pytest.skip("Weaviate is not ready at configured WEAVIATE_HTTP_URL")
    if not _schema_has_chunk(settings.weaviate_http_url, settings.weaviate_collection):
        pytest.skip("Chunk collection is missing in Weaviate")

    token = f"retrieval-token-{uuid4().hex[:8]}"
    doc_id = f"retrieval-doc-{uuid4().hex[:8]}"
    chunk_id = f"{doc_id}:0"
    _insert_seed_chunk(
        settings.weaviate_http_url,
        settings.weaviate_collection,
        doc_id,
        chunk_id,
        token,
        settings.embedding_model,
    )

    app = create_app()
    client = TestClient(app)

    bm25_response = client.post(
        "/retrieval/search",
        json={
            "query": token,
            "mode": "bm25",
            "top_k_retrieve": 5,
            "top_k_return": 3,
            "filters": {"document_id": doc_id},
        },
    )
    assert bm25_response.status_code == 200, bm25_response.text
    bm25_body = bm25_response.json()
    assert bm25_body["mode"] == "bm25"
    assert bm25_body["returned_count"] >= 1
    assert any(item["chunk_id"] == chunk_id for item in bm25_body["chunks"])

    vector_response = client.post(
        "/retrieval/search",
        json={
            "query": "integration retrieval query",
            "mode": "vector",
            "top_k_retrieve": 5,
            "top_k_return": 3,
            "filters": {"document_id": doc_id},
        },
    )
    assert vector_response.status_code == 200, vector_response.text
    vector_body = vector_response.json()
    assert vector_body["mode"] == "vector"
    assert vector_body["returned_count"] >= 1
    assert any(item["chunk_id"] == chunk_id for item in vector_body["chunks"])

    hybrid_response = client.post(
        "/retrieval/search",
        json={
            "query": token,
            "mode": "hybrid",
            "top_k_retrieve": 5,
            "top_k_return": 3,
            "filters": {"document_id": doc_id},
            "fusion": {"type": "alpha", "alpha": 0.7},
        },
    )
    assert hybrid_response.status_code == 200, hybrid_response.text
    hybrid_body = hybrid_response.json()
    assert hybrid_body["mode"] == "hybrid"
    assert hybrid_body["returned_count"] >= 1
    assert any(item["chunk_id"] == chunk_id for item in hybrid_body["chunks"])


@pytest.mark.integration
def test_retrieval_api_llm_batch_rerank_end_to_end() -> None:
    settings = Settings.from_env()
    if not settings.openai_key:
        pytest.skip("OPENAI_KEY is required for llm_batch rerank integration test")
    if not _weaviate_ready(settings.weaviate_http_url):
        pytest.skip("Weaviate is not ready at configured WEAVIATE_HTTP_URL")
    if not _schema_has_chunk(settings.weaviate_http_url, settings.weaviate_collection):
        pytest.skip("Chunk collection is missing in Weaviate")

    token = f"rerank-token-{uuid4().hex[:8]}"
    doc_id = f"rerank-doc-{uuid4().hex[:8]}"
    chunk_ids = _insert_seed_chunks(
        settings.weaviate_http_url,
        settings.weaviate_collection,
        doc_id,
        token,
        settings.embedding_model,
        count=2,
    )

    app = create_app()
    client = TestClient(app)
    response = client.post(
        "/retrieval/search",
        json={
            "query": token,
            "mode": "hybrid",
            "top_k_retrieve": 5,
            "top_k_return": 3,
            "filters": {"document_id": doc_id},
            "fusion": {"type": "alpha", "alpha": 0.7},
            "rerank": {
                "enabled": True,
                "type": "llm_batch",
                "top_n": 2,
                "batch_size": 2,
            },
        },
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["mode"] == "hybrid"
    assert body["rerank_type"] == "llm_batch"
    assert body["returned_count"] >= 1
    returned_ids = {item["chunk_id"] for item in body["chunks"]}
    assert any(cid in returned_ids for cid in chunk_ids)
    assert any(item.get("rerank_score") is not None for item in body["chunks"])


@pytest.mark.integration
def test_retrieval_api_cross_encoder_rerank_end_to_end_optional() -> None:
    if os.getenv("RETRIEVAL_RUN_CROSS_ENCODER_IT", "").strip().lower() not in {"1", "true", "yes"}:
        pytest.skip("Set RETRIEVAL_RUN_CROSS_ENCODER_IT=true to run cross-encoder integration test")

    settings = Settings.from_env()
    if not _weaviate_ready(settings.weaviate_http_url):
        pytest.skip("Weaviate is not ready at configured WEAVIATE_HTTP_URL")
    if not _schema_has_chunk(settings.weaviate_http_url, settings.weaviate_collection):
        pytest.skip("Chunk collection is missing in Weaviate")

    token = f"ce-token-{uuid4().hex[:8]}"
    doc_id = f"ce-doc-{uuid4().hex[:8]}"
    chunk_ids = _insert_seed_chunks(
        settings.weaviate_http_url,
        settings.weaviate_collection,
        doc_id,
        token,
        settings.embedding_model,
        count=2,
    )

    app = create_app()
    client = TestClient(app)
    response = client.post(
        "/retrieval/search",
        json={
            "query": token,
            "mode": "hybrid",
            "top_k_retrieve": 5,
            "top_k_return": 3,
            "filters": {"document_id": doc_id},
            "rerank": {
                "enabled": True,
                "type": "cross_encoder",
                "top_n": 2,
            },
        },
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["rerank_type"] == "cross_encoder"
    returned_ids = {item["chunk_id"] for item in body["chunks"]}
    assert any(cid in returned_ids for cid in chunk_ids)
    assert any(item.get("rerank_score") is not None for item in body["chunks"])
