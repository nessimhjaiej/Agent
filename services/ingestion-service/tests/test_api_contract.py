from pathlib import Path
import sys

from fastapi.testclient import TestClient

SERVICE_ROOT = Path(__file__).resolve().parents[1]
if str(SERVICE_ROOT) not in sys.path:
    sys.path.insert(0, str(SERVICE_ROOT))

from app.config import Settings  # noqa: E402
from app.main import create_app  # noqa: E402


def test_run_ingestion_rejects_invalid_embedding_batch_size() -> None:
    app = create_app(Settings())
    client = TestClient(app)

    response = client.post("/ingestion/run", json={"embedding_batch_size": 0})

    assert response.status_code == 422


def test_run_ingestion_rejects_blank_raw_dir() -> None:
    app = create_app(Settings())
    client = TestClient(app)

    response = client.post("/ingestion/run", json={"raw_dir": ""})

    assert response.status_code == 422


def test_index_document_requires_target_relative_path() -> None:
    app = create_app(Settings())
    client = TestClient(app)

    response = client.post("/ingestion/index-document", json={"source_url": "https://example.com/doc.pdf"})

    assert response.status_code == 422
