from pathlib import Path
import sys

import pytest

SERVICE_ROOT = Path(__file__).resolve().parents[1]
if str(SERVICE_ROOT) not in sys.path:
    sys.path.insert(0, str(SERVICE_ROOT))

from app.models import ChunkingContext, NormalizedDocument  # noqa: E402
from app.orchestrator import PreprocessingOrchestrator  # noqa: E402
from chunking.factory import ChunkerFactory  # noqa: E402


def _make_doc(text: str) -> NormalizedDocument:
    return NormalizedDocument(
        document_id="doc-1",
        source_type="pdf",
        source_uri="raw_data/sample.pdf",
        normalized_text=text,
        checksum="dummy-checksum",
        language="fr",
    )


def test_overlap_chunking_respects_size_and_overlap() -> None:
    doc = _make_doc("abcdefghijklmnopqrstuvwxyz")
    ctx = ChunkingContext(chunk_size=10, chunk_overlap=3)

    chunks = PreprocessingOrchestrator("overlap").process_document(doc, ctx)

    assert len(chunks) == 4
    assert chunks[0].chunk_text == "abcdefghij"
    assert chunks[1].chunk_text == "hijklmnopq"
    assert chunks[2].chunk_text == "opqrstuvwx"
    assert chunks[3].chunk_text == "vwxyz"
    assert chunks[0].metadata.start_char == 0
    assert chunks[1].metadata.start_char == 7
    assert chunks[0].metadata.chunking_strategy == "overlap"
    assert chunks[0].metadata.document_checksum == "dummy-checksum"


def test_factory_returns_requested_chunker() -> None:
    chunker = ChunkerFactory.create("overlap")
    assert chunker.name == "overlap"


def test_factory_raises_for_unknown_strategy() -> None:
    with pytest.raises(ValueError):
        ChunkerFactory.create("unknown")


@pytest.mark.parametrize("strategy", ["semantic", "late", "sentence"])
def test_placeholder_chunkers_raise_not_implemented(strategy: str) -> None:
    doc = _make_doc("hello world")
    ctx = ChunkingContext(chunk_size=10, chunk_overlap=2)
    orchestrator = PreprocessingOrchestrator(strategy)

    with pytest.raises(NotImplementedError):
        orchestrator.process_document(doc, ctx)
