from pathlib import Path
import sys

SERVICE_ROOT = Path(__file__).resolve().parents[1]
if str(SERVICE_ROOT) not in sys.path:
    sys.path.insert(0, str(SERVICE_ROOT))

from app.models import ChunkingContext, RawDocument  # noqa: E402
from app.orchestrator import PreprocessingOrchestrator  # noqa: E402
from normalization.basic import BasicTextNormalizer  # noqa: E402
from normalization.language import LightweightLanguageDetector  # noqa: E402


def test_basic_normalizer_cleans_whitespace() -> None:
    raw = RawDocument(
        document_id="doc-a",
        source_type="txt",
        source_uri="sample.txt",
        raw_text="Hello   world\r\n\r\n\r\nLine\t\t2\x00",
        checksum="raw-checksum",
    )

    normalized = BasicTextNormalizer().normalize(raw)

    assert normalized.normalized_text == "Hello world\n\nLine 2"
    assert normalized.normalization_version == "basic-v1"
    assert normalized.checksum


def test_process_source_txt_file(tmp_path: Path) -> None:
    source = tmp_path / "doc.txt"
    source.write_text(
        "The digital economy regulation framework is evolving rapidly and this text is in English.",
        encoding="utf-8",
    )

    orchestrator = PreprocessingOrchestrator(chunk_strategy="overlap", pipeline_version="v-test")
    chunks = orchestrator.process_source(
        str(source),
        context=ChunkingContext(chunk_size=10, chunk_overlap=2),
    )

    assert len(chunks) >= 1
    assert chunks[0].metadata.source_filename == "doc.txt"
    assert chunks[0].metadata.pipeline_version == "v-test"
    assert chunks[0].metadata.normalization_version == "basic-v1"
    assert chunks[0].metadata.language in {"en", "und"}


def test_language_detector_short_text_returns_und() -> None:
    detector = LightweightLanguageDetector(min_chars=20)
    assert detector.detect("hello") == "und"
