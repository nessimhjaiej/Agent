from pathlib import Path
import json
import sys

import httpx

SERVICE_ROOT = Path(__file__).resolve().parents[1]
if str(SERVICE_ROOT) not in sys.path:
    sys.path.insert(0, str(SERVICE_ROOT))

from app.models import IngestionRunParams  # noqa: E402
from app.orchestrator import IngestionOrchestrator  # noqa: E402


def test_run_dry_run_returns_mapped_sources(tmp_path: Path) -> None:
    docs_dir = tmp_path / "raw"
    docs_dir.mkdir()
    (docs_dir / "a.txt").write_text("alpha", encoding="utf-8")
    (docs_dir / "b.txt").write_text("beta", encoding="utf-8")

    orchestrator = IngestionOrchestrator(timeout_seconds=5.0)
    result = orchestrator.run(
        IngestionRunParams(
            raw_dir=str(docs_dir),
            source_root_in_preprocessing="/shared/raw_data",
            preprocessing_base_url="http://localhost:8000",
            embedding_base_url="http://localhost:8002",
            embedding_batch_size=10,
            recursive=True,
            patterns=["*.txt"],
            dry_run=True,
        )
    )

    assert result.documents_processed == 2
    assert result.documents_failed == 0
    assert len(result.results) == 2
    assert all(item.status == "dry_run" for item in result.results)
    assert result.results[0].source_path.startswith("/shared/raw_data/")


def test_run_calls_preprocessing_and_embedding(monkeypatch, tmp_path: Path) -> None:
    docs_dir = tmp_path / "raw"
    docs_dir.mkdir()
    (docs_dir / "doc.txt").write_text("hello", encoding="utf-8")

    chunks_payload = [
        {
            "chunk_id": "doc-1:0",
            "document_id": "doc-1",
            "chunk_text": "a",
            "metadata": {"document_checksum": "x"},
        },
        {
            "chunk_id": "doc-1:1",
            "document_id": "doc-1",
            "chunk_text": "b",
            "metadata": {"document_checksum": "x"},
        },
        {
            "chunk_id": "doc-1:2",
            "document_id": "doc-1",
            "chunk_text": "c",
            "metadata": {"document_checksum": "x"},
        },
    ]

    def handler(request: httpx.Request) -> httpx.Response:
        if request.method == "GET" and str(request.url).endswith("/health"):
            return httpx.Response(200, json={"status": "ok"})
        if request.method == "POST" and str(request.url).endswith("/preprocessing/process-source"):
            return httpx.Response(200, json={"status": "ok", "chunks": chunks_payload})
        if request.method == "POST" and str(request.url).endswith("/embedding/index-chunks"):
            body = json.loads(request.content.decode("utf-8"))
            count = len(body["chunks"])
            return httpx.Response(200, json={"status": "ok", "indexed_count": count})
        return httpx.Response(404, json={"detail": "not found"})

    transport = httpx.MockTransport(handler)

    class _MockClient(httpx.Client):
        def __init__(self, *args, **kwargs):
            super().__init__(transport=transport, **kwargs)

    monkeypatch.setattr("app.orchestrator.httpx.Client", _MockClient)

    orchestrator = IngestionOrchestrator(timeout_seconds=5.0)
    result = orchestrator.run(
        IngestionRunParams(
            raw_dir=str(docs_dir),
            source_root_in_preprocessing="/shared/raw_data",
            preprocessing_base_url="http://preprocessing:8000",
            embedding_base_url="http://embedding:8002",
            embedding_batch_size=2,
            recursive=True,
            patterns=["*.txt"],
            dry_run=False,
        )
    )

    assert result.documents_processed == 1
    assert result.documents_failed == 0
    assert result.chunks_total == 3
    assert result.chunks_indexed == 3
    assert result.results[0].status == "ok"

