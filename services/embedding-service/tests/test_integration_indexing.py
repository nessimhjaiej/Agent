from pathlib import Path
import sys
from uuid import NAMESPACE_URL, uuid4, uuid5

import httpx
import pytest
from dotenv import load_dotenv
from fastapi.testclient import TestClient

SERVICE_ROOT = Path(__file__).resolve().parents[1]
REPO_ROOT = Path(__file__).resolve().parents[3]
if str(SERVICE_ROOT) not in sys.path:
    sys.path.insert(0, str(SERVICE_ROOT))

load_dotenv(REPO_ROOT / ".env", override=True)

from app.main import create_app  # noqa: E402
from app.config import Settings  # noqa: E402


def _weaviate_ready(base_url: str) -> bool:
    try:
        response = httpx.get(f"{base_url.rstrip('/')}/v1/.well-known/ready", timeout=5.0)
    except httpx.HTTPError:
        return False
    return response.status_code == 200


@pytest.mark.integration
def test_index_chunks_e2e_openai_weaviate() -> None:
    settings = Settings.from_env()
    if not settings.openai_key:
        pytest.skip("OPENAI_KEY is required for integration test")
    if not _weaviate_ready(settings.weaviate_http_url):
        pytest.skip("Weaviate is not ready at configured WEAVIATE_HTTP_URL")

    unique_chunk_id = f"it-doc:{uuid4()}"
    checksum = "it-checksum-v1"
    dim_marker = settings.embedding_dimensions or 0
    seed = f"{unique_chunk_id}|{checksum}|{settings.embedding_model}|{dim_marker}"
    object_id = str(uuid5(NAMESPACE_URL, seed))

    payload = {
        "chunks": [
            {
                "chunk_id": unique_chunk_id,
                "document_id": "it-doc",
                "chunk_text": "Integration test chunk for embedding and vector insert validation.",
                "metadata": {
                    "source_type": "txt",
                    "source_uri": "c:/tmp/it-doc.txt",
                    "language": "en",
                    "chunk_index": 0,
                    "start_char": 0,
                    "end_char": 67,
                    "char_count": 67,
                    "token_count_estimate": 10,
                    "chunking_strategy": "overlap",
                    "source_filename": "it-doc.txt",
                    "document_checksum": checksum,
                    "normalization_version": "basic-v1",
                    "pipeline_version": "v1",
                    "created_at": "2026-03-02T00:00:00Z",
                },
            }
        ]
    }

    app = create_app()
    client = TestClient(app)
    response = client.post("/embedding/index-chunks", json=payload)
    assert response.status_code == 200, response.text

    response_body = response.json()
    assert response_body["indexed_count"] == 1
    assert response_body["results"][0]["chunk_id"] == unique_chunk_id
    assert response_body["results"][0]["indexed"] is True

    verify = httpx.get(
        f"{settings.weaviate_http_url.rstrip('/')}/v1/objects/{object_id}",
        timeout=10.0,
    )
    assert verify.status_code == 200, verify.text
    inserted = verify.json()
    assert inserted["class"] == settings.weaviate_collection
    assert inserted["properties"]["chunk_id"] == unique_chunk_id
