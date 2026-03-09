from pathlib import Path
import sys

SERVICE_ROOT = Path(__file__).resolve().parents[1]
if str(SERVICE_ROOT) not in sys.path:
    sys.path.insert(0, str(SERVICE_ROOT))

from app.config import Settings  # noqa: E402
from app.errors import GenerationProviderError  # noqa: E402
from app.models import ChatContext, RetrievedChunk  # noqa: E402
from app.orchestrator import GenerationOrchestrator  # noqa: E402


class _FakeLLMClient:
    def __init__(self, raw_response: str, raises: bool = False) -> None:
        self._raw_response = raw_response
        self._raises = raises
        self.calls: list[dict] = []

    def complete_json(self, system_prompt: str, user_prompt: str) -> str:
        self.calls.append({"system_prompt": system_prompt, "user_prompt": user_prompt})
        if self._raises:
            raise GenerationProviderError("provider failed")
        return self._raw_response


def _chunk(chunk_id: str, score: float) -> RetrievedChunk:
    return RetrievedChunk(
        chunk_id=chunk_id,
        document_id=chunk_id.split(":")[0],
        document_name=f"{chunk_id}.pdf",
        chunk_text=f"text for {chunk_id}",
        metadata={},
        rerank_score=score,
    )


def test_orchestrator_uses_llm_json_and_maps_citations() -> None:
    llm = _FakeLLMClient(
        raw_response='{"answer":"Concise answer.","citations":[{"chunk_id":"doc-2:0"}]}'
    )
    orchestrator = GenerationOrchestrator(
        settings=Settings(openai_key="test-key", generation_model="gpt-4o"),
        llm_client=llm,  # type: ignore[arg-type]
        fallback_llm_client=llm,  # type: ignore[arg-type]
    )
    ctx = ChatContext(
        query="Explain this.",
        retrieved_chunks=[_chunk("doc-1:0", 0.2), _chunk("doc-2:0", 0.9)],
    )

    result = orchestrator.generate(ctx)

    assert len(llm.calls) == 1
    assert result.status == "ok"
    assert result.answer == "Concise answer."
    assert result.used_chunk_ids == ["doc-2:0"]
    assert result.citations[0].document_id == "doc-2"
    assert result.model == "gpt-4o"


def test_orchestrator_falls_back_when_model_output_is_invalid_json() -> None:
    llm = _FakeLLMClient(raw_response="not a json")
    orchestrator = GenerationOrchestrator(
        settings=Settings(openai_key="test-key", generation_model="gpt-4o"),
        llm_client=llm,  # type: ignore[arg-type]
        fallback_llm_client=llm,  # type: ignore[arg-type]
    )
    ctx = ChatContext(
        query="Explain this.",
        retrieved_chunks=[_chunk("doc-1:0", 0.2)],
    )

    result = orchestrator.generate(ctx)

    assert result.status == "degraded"
    assert result.answer == "This is beyond my scope."
    assert result.citations == []
    assert result.used_chunk_ids == []


def test_orchestrator_falls_back_when_strict_citation_validation_fails() -> None:
    llm = _FakeLLMClient(
        raw_response='{"answer":"Concise answer.","citations":[{"chunk_id":"doc-x:0"}]}'
    )
    orchestrator = GenerationOrchestrator(
        settings=Settings(
            openai_key="test-key",
            generation_model="gpt-4o",
            generation_fallback_enabled=False,
            generation_require_citations=True,
            generation_strict_citation_validation=True,
        ),
        llm_client=llm,  # type: ignore[arg-type]
        fallback_llm_client=llm,  # type: ignore[arg-type]
    )
    ctx = ChatContext(
        query="Explain this.",
        retrieved_chunks=[_chunk("doc-1:0", 0.2)],
    )

    result = orchestrator.generate(ctx)

    assert result.status == "degraded"
    assert result.answer == "This is beyond my scope."
    assert result.citations == []
    assert result.used_chunk_ids == []


def test_orchestrator_uses_fallback_model_when_primary_provider_fails() -> None:
    primary = _FakeLLMClient(raw_response="", raises=True)
    fallback = _FakeLLMClient(
        raw_response='{"answer":"Fallback answer.","citations":[{"chunk_id":"doc-1:0"}]}'
    )
    orchestrator = GenerationOrchestrator(
        settings=Settings(
            openai_key="test-key",
            generation_model="gpt-4o",
            generation_fallback_enabled=True,
            generation_fallback_model="gpt-4o-mini",
        ),
        llm_client=primary,  # type: ignore[arg-type]
        fallback_llm_client=fallback,  # type: ignore[arg-type]
    )
    ctx = ChatContext(
        query="Explain this.",
        retrieved_chunks=[_chunk("doc-1:0", 0.9)],
    )

    result = orchestrator.generate(ctx)

    assert len(primary.calls) == 1
    assert len(fallback.calls) == 1
    assert result.status == "degraded"
    assert result.answer == "Fallback answer."
    assert result.model == "gpt-4o-mini"


def test_orchestrator_instructs_model_to_answer_in_user_language() -> None:
    llm = _FakeLLMClient(
        raw_response='{"answer":"Réponse concise.","citations":[{"chunk_id":"doc-1:0"}]}'
    )
    orchestrator = GenerationOrchestrator(
        settings=Settings(openai_key="test-key", generation_model="gpt-4o"),
        llm_client=llm,  # type: ignore[arg-type]
        fallback_llm_client=llm,  # type: ignore[arg-type]
    )
    ctx = ChatContext(
        query="Réponds-moi en français: quelles sont les obligations ?",
        retrieved_chunks=[_chunk("doc-1:0", 0.9)],
    )

    result = orchestrator.generate(ctx)

    assert result.answer == "Réponse concise."
    assert "Answer in the same language as the user's latest query" in llm.calls[0]["user_prompt"]
    assert "answer in the language requested by the user" in llm.calls[0]["system_prompt"].lower()
def test_orchestrator_instructs_model_to_explain_without_chunk_availability_wording() -> None:
    llm = _FakeLLMClient(
        raw_response='{"answer":"Concise answer.","citations":[{"chunk_id":"doc-1:0"}]}'
    )
    orchestrator = GenerationOrchestrator(
        settings=Settings(openai_key="test-key", generation_model="gpt-4o"),
        llm_client=llm,  # type: ignore[arg-type]
        fallback_llm_client=llm,  # type: ignore[arg-type]
    )
    ctx = ChatContext(
        query="Please explain this more clearly.",
        retrieved_chunks=[_chunk("doc-1:0", 0.9)],
    )

    orchestrator.generate(ctx)

    assert "do not say that the information is \"not available in the retrieved chunks\"" in llm.calls[0][
        "system_prompt"
    ].lower()
