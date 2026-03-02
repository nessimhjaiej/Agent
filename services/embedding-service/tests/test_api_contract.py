from pathlib import Path
import os
import sys

from fastapi.testclient import TestClient

SERVICE_ROOT = Path(__file__).resolve().parents[1]
if str(SERVICE_ROOT) not in sys.path:
    sys.path.insert(0, str(SERVICE_ROOT))

os.environ.setdefault("OPENAI_KEY", "test-key")

from app.config import Settings  # noqa: E402
from app.main import create_app  # noqa: E402


def test_index_chunks_rejects_empty_chunk_list() -> None:
    app = create_app(Settings(openai_key="test-key"))
    client = TestClient(app)

    response = client.post("/embedding/index-chunks", json={"chunks": []})

    assert response.status_code == 422


def test_index_chunks_rejects_missing_required_chunk_field() -> None:
    app = create_app(Settings(openai_key="test-key"))
    client = TestClient(app)

    response = client.post(
        "/embedding/index-chunks",
        json={
            "chunks": [
                {
                    "chunk_id": "doc-1:0",
                    "document_id": "doc-1",
                    # chunk_text intentionally missing
                    "metadata": {
                        "source_type": "txt",
                        "source_uri": "c:/tmp/doc.txt",
                        "language": "en",
                        "chunk_index": 0,
                        "start_char": 0,
                        "end_char": 11,
                        "char_count": 11,
                        "token_count_estimate": 2,
                        "chunking_strategy": "overlap",
                        "source_filename": "doc.txt",
                        "document_checksum": "abc",
                        "normalization_version": "basic-v1",
                        "pipeline_version": "v1",
                        "created_at": "2026-03-02T00:00:00Z",
                    },
                }
            ]
        },
    )

    assert response.status_code == 422


def test_index_chunks_rejects_blank_chunk_text() -> None:
    app = create_app(Settings(openai_key="test-key"))
    client = TestClient(app)

    response = client.post(
        "/embedding/index-chunks",
        json={
            "chunks": [
                {
                    "chunk_id": "doc-1:0",
                    "document_id": "doc-1",
                    "chunk_text": "",
                    "metadata": {
                        "source_type": "txt",
                        "source_uri": "c:/tmp/doc.txt",
                        "language": "en",
                        "chunk_index": 0,
                        "start_char": 0,
                        "end_char": 11,
                        "char_count": 11,
                        "token_count_estimate": 2,
                        "chunking_strategy": "overlap",
                        "source_filename": "doc.txt",
                        "document_checksum": "abc",
                        "normalization_version": "basic-v1",
                        "pipeline_version": "v1",
                        "created_at": "2026-03-02T00:00:00Z",
                    },
                }
            ]
        },
    )

    assert response.status_code == 422
