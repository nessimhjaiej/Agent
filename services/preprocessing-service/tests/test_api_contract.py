from pathlib import Path
import sys

from fastapi.testclient import TestClient

SERVICE_ROOT = Path(__file__).resolve().parents[1]
if str(SERVICE_ROOT) not in sys.path:
    sys.path.insert(0, str(SERVICE_ROOT))

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


def test_process_source_returns_400_when_file_missing() -> None:
    app = create_app()
    client = TestClient(app)

    response = client.post(
        "/preprocessing/process-source",
        json={"source_path": "not/found/file.txt"},
    )

    assert response.status_code == 400
