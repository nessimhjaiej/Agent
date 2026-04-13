from pathlib import Path
import sys

from fastapi.testclient import TestClient

SERVICE_ROOT = Path(__file__).resolve().parents[1]
if str(SERVICE_ROOT) not in sys.path:
    sys.path.insert(0, str(SERVICE_ROOT))

from app.config import Settings  # noqa: E402
from app.main import create_app  # noqa: E402


def test_health_endpoint() -> None:
    app = create_app()
    client = TestClient(app)

    response = client.get("/health")

    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "ok"
    assert "service" in payload
    assert "version" in payload


def test_process_source_txt_endpoint(tmp_path: Path) -> None:
    source = tmp_path / "sample.txt"
    source.write_text("One two three four five six seven", encoding="utf-8")
    app = create_app()
    client = TestClient(app)

    response = client.post(
        "/preprocessing/process-source",
        json={
            "source_path": str(source),
            "chunk_strategy": "overlap",
            "chunk_size": 10,
            "chunk_overlap": 2,
            "late_size_multiplier": 2.0,
            "late_overlap_multiplier": 2.0,
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "ok"
    assert payload["chunk_count"] >= 1
    assert payload["chunks"][0]["metadata"]["chunking_strategy"] == "overlap"


def test_get_config_returns_runtime_chunk_settings() -> None:
    app = create_app(
        Settings(
            chunk_strategy="semantic",
            chunk_size=640,
            chunk_overlap=80,
            pipeline_version="v2",
        )
    )
    client = TestClient(app)

    response = client.get("/preprocessing/config")

    assert response.status_code == 200
    payload = response.json()
    assert payload["config"]["chunk_strategy"] == "semantic"
    assert payload["config"]["chunk_size"] == 640
    assert payload["config"]["chunk_overlap"] == 80
    assert payload["config"]["pipeline_version"] == "v2"


def test_update_config_updates_runtime_and_process_source(tmp_path: Path) -> None:
    source = tmp_path / "sample.txt"
    source.write_text("One two three four five six seven", encoding="utf-8")
    app = create_app(Settings(chunk_strategy="late", chunk_size=800, chunk_overlap=120, pipeline_version="v1"))
    app.state.env_local_path = tmp_path / ".env.local"
    client = TestClient(app)

    update_response = client.put(
        "/preprocessing/config",
        json={"chunk_strategy": "overlap", "chunk_size": 32, "chunk_overlap": 4},
    )

    assert update_response.status_code == 200
    updated = update_response.json()
    assert updated["updated"]["chunk_strategy"] == "overlap"
    assert updated["updated"]["chunk_size"] == 32
    assert updated["updated"]["chunk_overlap"] == 4

    config_response = client.get("/preprocessing/config")
    assert config_response.status_code == 200
    config_payload = config_response.json()
    assert config_payload["config"]["chunk_strategy"] == "overlap"
    assert config_payload["config"]["chunk_size"] == 32
    assert config_payload["config"]["chunk_overlap"] == 4

    process_response = client.post("/preprocessing/process-source", json={"source_path": str(source)})
    assert process_response.status_code == 200
    process_payload = process_response.json()
    assert process_payload["chunks"][0]["metadata"]["chunking_strategy"] == "overlap"


def test_process_source_accepts_document_id_override(tmp_path: Path) -> None:
    source = tmp_path / "sample.txt"
    source.write_text("One two three four five six seven", encoding="utf-8")
    app = create_app()
    client = TestClient(app)

    response = client.post(
        "/preprocessing/process-source",
        json={
            "source_path": str(source),
            "document_id": "supabase-doc-uuid",
            "chunk_strategy": "overlap",
            "chunk_size": 10,
            "chunk_overlap": 2,
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["chunks"][0]["document_id"] == "supabase-doc-uuid"
    assert payload["chunks"][0]["chunk_id"].startswith("supabase-doc-uuid:")


def test_process_source_returns_400_when_file_missing() -> None:
    app = create_app()
    client = TestClient(app)

    response = client.post(
        "/preprocessing/process-source",
        json={"source_path": "not/found/file.txt"},
    )

    assert response.status_code == 400


def test_rate_limit_returns_429(tmp_path: Path) -> None:
    source = tmp_path / "sample.txt"
    source.write_text("One two three four five six seven", encoding="utf-8")
    app = create_app(
        Settings(
            rate_limit_requests=2,
            rate_limit_window_seconds=60,
            max_request_size_bytes=1_048_576,
        )
    )
    client = TestClient(app)
    payload = {"source_path": str(source), "chunk_strategy": "overlap"}

    r1 = client.post("/preprocessing/process-source", json=payload)
    r2 = client.post("/preprocessing/process-source", json=payload)
    r3 = client.post("/preprocessing/process-source", json=payload)

    assert r1.status_code == 200
    assert r2.status_code == 200
    assert r3.status_code == 429


def test_request_size_limit_returns_413() -> None:
    app = create_app(
        Settings(
            max_request_size_bytes=80,
            rate_limit_requests=100,
            rate_limit_window_seconds=60,
        )
    )
    client = TestClient(app)
    long_path = "x" * 500

    response = client.post(
        "/preprocessing/process-source",
        json={"source_path": long_path},
    )

    assert response.status_code == 413
