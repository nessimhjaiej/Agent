from pathlib import Path
import sys

SERVICE_ROOT = Path(__file__).resolve().parents[1]
if str(SERVICE_ROOT) not in sys.path:
    sys.path.insert(0, str(SERVICE_ROOT))

from app.config import Settings  # noqa: E402
from app.models import IndexDocumentResult, IngestionRunResult  # noqa: E402
from app.schemas import IndexDocumentRequest, RunIngestionRequest  # noqa: E402
from app.service import IngestionService  # noqa: E402


def test_service_uses_request_overrides(monkeypatch, tmp_path: Path) -> None:
    captured = {}

    service = IngestionService(
        Settings(
            raw_dir=str(tmp_path),
            source_root_in_preprocessing="/shared/raw_data",
            preprocessing_base_url="http://localhost:8000",
            embedding_base_url="http://localhost:8002",
            embedding_batch_size=100,
        )
    )

    def _fake_run(self, params):  # noqa: ANN001
        captured["params"] = params
        return IngestionRunResult(
            documents_processed=0,
            documents_failed=0,
            chunks_total=0,
            chunks_indexed=0,
            failed_files=[],
            results=[],
        )

    monkeypatch.setattr(service, "_orchestrator", type("_Stub", (), {"run": _fake_run})())

    service.run_ingestion(
        RunIngestionRequest(
            embedding_batch_size=12,
            recursive=False,
            patterns=["*.pdf"],
            dry_run=True,
        )
    )

    assert captured["params"].embedding_batch_size == 12
    assert captured["params"].recursive is False
    assert captured["params"].patterns == ["*.pdf"]
    assert captured["params"].dry_run is True


def test_index_document_builds_expected_source_path(monkeypatch, tmp_path: Path) -> None:
    captured = {}
    service = IngestionService(
        Settings(
            raw_dir=str(tmp_path),
            source_root_in_preprocessing="/shared/raw_data",
            preprocessing_base_url="http://localhost:8000",
            embedding_base_url="http://localhost:8002",
            embedding_batch_size=100,
        )
    )

    def _fake_index(self, params):  # noqa: ANN001
        captured["params"] = params
        return IndexDocumentResult(
            status="indexed",
            source_path=params.target_relative_path,
            exists_in_weaviate=False,
            indexed=True,
            chunks_count=1,
            indexed_count=1,
            message="ok",
        )

    stub = type("_Stub", (), {"run": service._orchestrator.run, "index_document": _fake_index})()
    monkeypatch.setattr(service, "_orchestrator", stub)

    service.index_document(
        IndexDocumentRequest(
            source_url="https://example.com/doc.pdf",
            target_relative_path="supabase/validated/user/doc.pdf",
            skip_if_exists=True,
        )
    )

    assert (
        captured["params"].target_relative_path
        == "/shared/raw_data/supabase/validated/user/doc.pdf"
    )
    assert captured["params"].skip_if_exists is True
