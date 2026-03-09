from app.clients.openai_audio_client import OpenAIAudioClient
from app.clients.retrieval_client import RetrievalClient
from app.config import Settings
from app.guardrails import is_prompt_attack_query
from app.models import ChatContext, ChatTurn, RetrievedChunk
from app.orchestrator import GenerationOrchestrator
from app.schemas import (
    AskRequest,
    AskResponse,
    ChatRequest,
    ChatResponse,
    CitationResponse,
    TranscriptionResponse,
)


class GenerationService:
    def __init__(
        self,
        settings: Settings | None = None,
        orchestrator: GenerationOrchestrator | None = None,
        retrieval_client: RetrievalClient | None = None,
    ) -> None:
        self._settings = settings or Settings.from_env()
        self._orchestrator = orchestrator or GenerationOrchestrator(settings=self._settings)
        self._retrieval_client = retrieval_client or RetrievalClient(
            base_url=self._settings.retrieval_base_url,
            timeout_seconds=self._settings.retrieval_timeout_seconds,
            max_retries=self._settings.generation_http_max_retries,
            retry_base_seconds=self._settings.generation_retry_base_seconds,
        )
        self._audio_client = OpenAIAudioClient(
            api_key=self._settings.openai_key,
            model=self._settings.transcription_model,
            timeout_seconds=self._settings.generation_timeout_seconds,
            max_retries=self._settings.generation_http_max_retries,
            retry_base_seconds=self._settings.generation_retry_base_seconds,
        )

    def chat(self, payload: ChatRequest) -> ChatResponse:
        if self._should_block_query(payload.query):
            return self._scope_fallback_response(
                query=payload.query,
                session_id=payload.session_id,
            )
        context = ChatContext(
            query=payload.query,
            retrieved_chunks=[
                RetrievedChunk(
                    chunk_id=item.chunk_id,
                    document_id=item.document_id,
                    document_name=item.document_name,
                    chunk_text=item.chunk_text,
                    metadata=item.metadata,
                    bm25_score=item.bm25_score,
                    vector_score=item.vector_score,
                    fusion_score=item.fusion_score,
                    rerank_score=item.rerank_score,
                )
                for item in payload.retrieved_chunks
            ],
            chat_history=[ChatTurn(role=turn.role, content=turn.content) for turn in payload.chat_history],
            session_id=payload.session_id,
        )
        result = self._orchestrator.generate(context)
        return self._to_chat_response(
            result=result,
            query=payload.query,
            session_id=payload.session_id,
        )

    def ask(self, payload: AskRequest) -> AskResponse:
        if self._should_block_query(payload.query):
            fallback = self._scope_fallback_response(
                query=payload.query,
                session_id=payload.session_id,
            )
            return AskResponse(
                **fallback.model_dump(),
                retrieval_count=0,
                returned_count=0,
                retrieval_mode=payload.mode,
                fusion_type=payload.fusion.type if payload.fusion and payload.fusion.type else "",
                rerank_type=payload.rerank.type if payload.rerank and payload.rerank.type else "none",
            )

        retrieval_request = {
            "query": self._build_retrieval_query(payload.query, payload.chat_history),
            "mode": payload.mode,
            "top_k_retrieve": payload.top_k_retrieve,
            "top_k_return": payload.top_k_return,
            "filters": payload.filters,
            "fusion": payload.fusion.model_dump() if payload.fusion else None,
            "rerank": payload.rerank.model_dump() if payload.rerank else None,
        }
        retrieval_request = {k: v for k, v in retrieval_request.items() if v is not None}
        retrieval_response = self._retrieval_client.search(retrieval_request)

        chat_payload = ChatRequest(
            query=payload.query,
            retrieved_chunks=retrieval_response.get("chunks", []),
            chat_history=payload.chat_history,
            session_id=payload.session_id,
        )
        chat_response = self.chat(chat_payload)
        return AskResponse(
            **chat_response.model_dump(),
            retrieval_count=int(retrieval_response.get("retrieval_count", 0)),
            returned_count=int(retrieval_response.get("returned_count", 0)),
            retrieval_mode=str(retrieval_response.get("mode", payload.mode)),
            fusion_type=str(retrieval_response.get("fusion_type", "")),
            rerank_type=str(retrieval_response.get("rerank_type", "")),
        )

    def transcribe(
        self,
        filename: str,
        content: bytes,
        content_type: str | None = None,
        language: str | None = None,
        prompt: str | None = None,
    ) -> TranscriptionResponse:
        if not filename.strip():
            raise ValueError("Audio filename is required")
        if not content:
            raise ValueError("Audio file is empty")

        text = self._audio_client.transcribe(
            filename=filename,
            content=content,
            content_type=content_type or "application/octet-stream",
            language=language,
            prompt=prompt,
        )
        return TranscriptionResponse(
            text=text,
            model=self._settings.transcription_model,
            filename=filename,
        )

    def _to_chat_response(self, result, query: str, session_id: str | None) -> ChatResponse:  # noqa: ANN001
        return ChatResponse(
            status=result.status,
            session_id=session_id,
            query=query,
            answer=result.answer,
            citations=[
                CitationResponse(
                    chunk_id=item.chunk_id,
                    document_id=item.document_id,
                    document_name=item.document_name,
                    chunk_text=item.chunk_text,
                )
                for item in result.citations
            ],
            used_chunk_ids=result.used_chunk_ids,
            model=result.model,
        )

    def _scope_fallback_response(self, query: str, session_id: str | None) -> ChatResponse:
        return ChatResponse(
            status="degraded",
            session_id=session_id,
            query=query,
            answer=self._settings.default_scope_fallback,
            citations=[],
            used_chunk_ids=[],
            model=self._settings.generation_model,
        )

    def _should_block_query(self, query: str) -> bool:
        if not self._settings.generation_block_prompt_attack_queries:
            return False
        return is_prompt_attack_query(query)

    def _build_retrieval_query(self, query: str, chat_history: list[ChatTurn]) -> str:
        cleaned_query = query.strip()
        if not cleaned_query or not chat_history:
            return cleaned_query
        if not self._is_contextual_follow_up(cleaned_query):
            return cleaned_query

        previous_user = ""
        previous_assistant = ""
        for turn in reversed(chat_history):
            content = turn.content.strip()
            if not content:
                continue
            if turn.role == "user" and not previous_user:
                previous_user = content
            if turn.role == "assistant" and not previous_assistant:
                previous_assistant = content
            if previous_user and previous_assistant:
                break

        context_parts = []
        if previous_user:
            context_parts.append(f"Previous user topic: {self._trim_text(previous_user, 400)}")
        if previous_assistant:
            context_parts.append(
                f"Previous assistant answer: {self._trim_text(previous_assistant, 500)}"
            )
        context_parts.append(f"Current follow-up request: {cleaned_query}")
        return "\n".join(context_parts)

    def _is_contextual_follow_up(self, query: str) -> bool:
        lowered = query.lower()
        word_count = len(query.split())
        clarification_markers = (
            "explain",
            "clarify",
            "clarification",
            "elaborate",
            "rephrase",
            "summarize",
            "translate",
            "in french",
            "in english",
            "in arabic",
            "in spanish",
            "in simple terms",
            "what does that mean",
            "can you explain",
            "can you clarify",
            "peux-tu expliquer",
            "explique",
            "explique en",
            "précise",
            "precise",
            "clarifie",
            "résume",
            "resume",
            "traduis",
            "en français",
            "en francais",
        )
        referential_markers = ("this", "that", "it", "they", "ceci", "cela", "ça", "ca", "le", "la")
        return (
            word_count <= 12
            or any(marker in lowered for marker in clarification_markers)
            or lowered in referential_markers
        )

    def _trim_text(self, value: str, max_chars: int) -> str:
        text = value.strip()
        if len(text) <= max_chars:
            return text
        return f"{text[: max_chars - 3].rstrip()}..."
