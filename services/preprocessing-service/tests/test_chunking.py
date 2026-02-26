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


def test_semantic_chunking_with_overlap() -> None:
    doc = _make_doc(
        "Sentence one. Sentence two with more words. Sentence three.\n\n"
        "Second paragraph starts here. It ends here."
    )
    ctx = ChunkingContext(chunk_size=45, chunk_overlap=12)

    chunks = PreprocessingOrchestrator("semantic").process_document(doc, ctx)

    assert len(chunks) >= 2
    assert chunks[0].metadata.chunking_strategy == "semantic"
    assert chunks[1].metadata.start_char < chunks[0].metadata.end_char


def test_late_chunking_with_overlap() -> None:
    doc = _make_doc(
        "Alpha sentence. Beta sentence. Gamma sentence. Delta sentence.\n\n"
        "Paragraph two starts. Another sentence. Final sentence."
    )
    ctx = ChunkingContext(
        chunk_size=30,
        chunk_overlap=8,
        strategy_params={"late_size_multiplier": 2.0, "late_overlap_multiplier": 2.0},
    )

    chunks = PreprocessingOrchestrator("late").process_document(doc, ctx)

    assert len(chunks) >= 1
    assert chunks[0].metadata.chunking_strategy == "late"
    if len(chunks) > 1:
        assert chunks[1].metadata.start_char < chunks[0].metadata.end_char


def test_sentence_chunker_still_not_implemented() -> None:
    doc = _make_doc("hello world")
    ctx = ChunkingContext(chunk_size=10, chunk_overlap=2)
    orchestrator = PreprocessingOrchestrator("sentence")

    with pytest.raises(NotImplementedError):
        orchestrator.process_document(doc, ctx)
