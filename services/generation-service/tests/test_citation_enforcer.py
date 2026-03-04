from pathlib import Path
import sys

import pytest

SERVICE_ROOT = Path(__file__).resolve().parents[1]
if str(SERVICE_ROOT) not in sys.path:
    sys.path.insert(0, str(SERVICE_ROOT))

from app.errors import GenerationValidationError  # noqa: E402
from app.models import RetrievedChunk  # noqa: E402
from citation_enforcement.enforcer import CitationEnforcer  # noqa: E402


def _chunks() -> dict[str, RetrievedChunk]:
    first = RetrievedChunk(
        chunk_id="doc-1:0",
        document_id="doc-1",
        document_name="doc-1.pdf",
        chunk_text="evidence 1",
        metadata={},
    )
    second = RetrievedChunk(
        chunk_id="doc-2:0",
        document_id="doc-2",
        document_name="doc-2.pdf",
        chunk_text="evidence 2",
        metadata={},
    )
    return {first.chunk_id: first, second.chunk_id: second}


def test_enforcer_accepts_valid_citations() -> None:
    enforcer = CitationEnforcer(require_citations=True, strict_validation=True)

    citations = enforcer.enforce(["doc-2:0"], _chunks())

    assert len(citations) == 1
    assert citations[0].chunk_id == "doc-2:0"


def test_enforcer_raises_on_unknown_citation_in_strict_mode() -> None:
    enforcer = CitationEnforcer(require_citations=True, strict_validation=True)

    with pytest.raises(GenerationValidationError):
        _ = enforcer.enforce(["doc-x:0"], _chunks())


def test_enforcer_drops_unknown_citation_in_lenient_mode() -> None:
    enforcer = CitationEnforcer(require_citations=False, strict_validation=False)

    citations = enforcer.enforce(["doc-x:0", "doc-1:0"], _chunks())

    assert len(citations) == 1
    assert citations[0].chunk_id == "doc-1:0"


def test_enforcer_requires_at_least_one_valid_citation_when_enabled() -> None:
    enforcer = CitationEnforcer(require_citations=True, strict_validation=False)

    with pytest.raises(GenerationValidationError):
        _ = enforcer.enforce([], _chunks())
