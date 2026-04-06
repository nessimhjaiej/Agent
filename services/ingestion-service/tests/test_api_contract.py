from pathlib import Path
import sys

from fastapi.testclient import TestClient

SERVICE_ROOT = Path(__file__).resolve().parents[1]
if str(SERVICE_ROOT) not in sys.path:
    sys.path.insert(0, str(SERVICE_ROOT))

from app.main import create_app  # noqa: E402
from app.models import DeleteDocumentResult, DocumentRecord, SignedUrlResult  # noqa: E402
from app.routers import ingestion as ingestion_router  # noqa: E402


def _settings():
    from app.config import Settings  # noqa: E402

    return Settings(supabase_url="https://example.supabase.co", supabase_key="test-key")


def test_list_documents_requires_user_id(monkeypatch) -> None:
    monkeypatch.setattr(ingestion_router, "_service", lambda: type("_Stub", (), {"list_documents": lambda self, user_id: []})())
    app = create_app(_settings())
    client = TestClient(app)

    response = client.get("/ingestion/documents")

    assert response.status_code == 422


def test_upload_document_requires_file(monkeypatch) -> None:
    app = create_app(_settings())
    client = TestClient(app)

    response = client.post("/ingestion/documents/upload", data={"user_id": "user-1"})

    assert response.status_code == 422


def test_update_document_status_rejects_invalid_status() -> None:
    app = create_app(_settings())
    client = TestClient(app)

    response = client.post("/ingestion/documents/doc-1/status", json={"target_status": "archived"})

    assert response.status_code == 422


def test_get_signed_url_returns_payload(monkeypatch) -> None:
    monkeypatch.setattr(ingestion_router, "_service", lambda: type("_Stub", (), {
        "get_document_signed_url": lambda self, document_id, expires_in=None: SignedUrlResult(
            document_id=document_id,
            storage_path="validated/u/doc.pdf",
            signed_url="https://example.supabase.co/storage/v1/object/sign/doc",
            expires_in=expires_in or 3600,
        )
    })())
    app = create_app(_settings())
    client = TestClient(app)

    response = client.get("/ingestion/documents/doc-1/signed-url")

    assert response.status_code == 200
    assert response.json()["document_id"] == "doc-1"


def test_get_signed_url_by_storage_path_returns_payload(monkeypatch) -> None:
    monkeypatch.setattr(ingestion_router, "_service", lambda: type("_Stub", (), {
        "get_document_signed_url_by_storage_path": lambda self, storage_path, expires_in=None: SignedUrlResult(
            document_id="doc-1",
            storage_path=storage_path,
            signed_url="https://example.supabase.co/storage/v1/object/sign/doc",
            expires_in=expires_in or 3600,
        )
    })())
    app = create_app(_settings())
    client = TestClient(app)

    response = client.get("/ingestion/documents/signed-url/by-storage-path?storage_path=validated/u/doc.pdf")

    assert response.status_code == 200
    assert response.json()["storage_path"] == "validated/u/doc.pdf"


def test_delete_document_returns_payload(monkeypatch) -> None:
    monkeypatch.setattr(ingestion_router, "_service", lambda: type("_Stub", (), {
        "delete_document": lambda self, document_id: DeleteDocumentResult(
            status="ok",
            document_id=document_id,
            storage_path="validated/u/doc.pdf",
        )
    })())
    app = create_app(_settings())
    client = TestClient(app)

    response = client.delete("/ingestion/documents/doc-1")

    assert response.status_code == 200
    assert response.json()["status"] == "ok"


def test_list_documents_returns_rows(monkeypatch) -> None:
    monkeypatch.setattr(ingestion_router, "_service", lambda: type("_Stub", (), {
        "list_documents": lambda self, user_id: [
            DocumentRecord(
                id="doc-1",
                user_id=user_id,
                original_name="sample.pdf",
                storage_path="pending/user-1/sample.pdf",
                status="pending",
                embedded=False,
                size_bytes=123,
                created_at="2026-03-12T00:00:00Z",
            )
        ]
    })())
    app = create_app(_settings())
    client = TestClient(app)

    response = client.get("/ingestion/documents?user_id=user-1")

    assert response.status_code == 200
    body = response.json()
    assert len(body["documents"]) == 1
    assert body["documents"][0]["original_name"] == "sample.pdf"
