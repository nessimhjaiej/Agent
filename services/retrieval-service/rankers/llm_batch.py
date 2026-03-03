import json
import os
import re
from dataclasses import replace

import httpx

from app.errors import RetrievalProviderError
from app.models import CandidateChunk
from rankers.base import BaseRanker


class LLMBatchRanker(BaseRanker):
    def __init__(
        self,
        api_key: str | None = None,
        model: str | None = None,
        batch_size: int | None = None,
        max_chars: int | None = None,
        temperature: float | None = None,
        timeout_seconds: float | None = None,
    ) -> None:
        self._api_key = api_key or os.getenv("OPENAI_KEY", "")
        self._model = model or os.getenv("RETRIEVAL_LLM_RERANK_MODEL", "gpt-4.1-mini")
        self._batch_size = batch_size or int(os.getenv("RETRIEVAL_LLM_RERANK_BATCH_SIZE", "10"))
        self._max_chars = max_chars or int(os.getenv("RETRIEVAL_LLM_RERANK_MAX_CHARS", "1000"))
        self._temperature = (
            temperature
            if temperature is not None
            else float(os.getenv("RETRIEVAL_LLM_RERANK_TEMPERATURE", "0"))
        )
        self._timeout_seconds = (
            timeout_seconds
            if timeout_seconds is not None
            else float(os.getenv("RETRIEVAL_LLM_RERANK_TIMEOUT_SECONDS", "30"))
        )
        self._client = httpx.Client(
            base_url="https://api.openai.com/v1",
            timeout=self._timeout_seconds,
            trust_env=False,
            headers={
                "Authorization": f"Bearer {self._api_key}",
                "Content-Type": "application/json",
            },
        )

    @property
    def name(self) -> str:
        return "llm_batch"

    def rank(self, query: str, candidates: list[CandidateChunk], top_n: int) -> list[CandidateChunk]:
        if not candidates:
            return []

        candidate_subset = candidates[:top_n]
        try:
            scored = self._score_all_batches(query, candidate_subset)
        except Exception:
            # Safe fallback: preserve fused order when reranking fails.
            return candidate_subset

        by_id = {chunk.chunk_id: chunk for chunk in candidate_subset}
        scored_candidates: list[CandidateChunk] = []
        seen: set[str] = set()
        for chunk_id, score in scored:
            candidate = by_id.get(chunk_id)
            if candidate is None or chunk_id in seen:
                continue
            seen.add(chunk_id)
            scored_candidates.append(replace(candidate, rerank_score=score))

        # Append any missing items in original order as fallback.
        for candidate in candidate_subset:
            if candidate.chunk_id not in seen:
                scored_candidates.append(candidate)

        scored_candidates.sort(
            key=lambda x: (
                x.rerank_score if x.rerank_score is not None else float("-inf"),
                x.fusion_score if x.fusion_score is not None else float("-inf"),
            ),
            reverse=True,
        )
        return scored_candidates[:top_n]

    def _score_all_batches(
        self,
        query: str,
        candidates: list[CandidateChunk],
    ) -> list[tuple[str, float]]:
        scored: list[tuple[str, float]] = []
        for start in range(0, len(candidates), self._batch_size):
            batch = candidates[start : start + self._batch_size]
            scored.extend(self._score_batch(query, batch))
        return scored

    def _score_batch(
        self,
        query: str,
        batch: list[CandidateChunk],
    ) -> list[tuple[str, float]]:
        prompt_candidates = [
            {
                "chunk_id": item.chunk_id,
                "chunk_text": item.chunk_text[: self._max_chars],
            }
            for item in batch
        ]

        user_payload = {
            "query": query,
            "candidates": prompt_candidates,
            "instructions": (
                "Return ONLY JSON with key 'scores'. "
                "scores is a list of objects: {chunk_id: string, score: number between 0 and 1}. "
                "Include each candidate chunk_id exactly once."
            ),
        }

        body = {
            "model": self._model,
            "temperature": self._temperature,
            "messages": [
                {
                    "role": "system",
                    "content": "You are a retrieval reranker. Respond with strict JSON only.",
                },
                {
                    "role": "user",
                    "content": json.dumps(user_payload, ensure_ascii=False),
                },
            ],
        }

        response = self._client.post("/chat/completions", json=body)
        if response.status_code >= 400:
            raise RetrievalProviderError(
                f"LLM batch reranking failed {response.status_code}: {response.text}"
            )

        payload = response.json()
        content = (
            payload.get("choices", [{}])[0]
            .get("message", {})
            .get("content", "")
        )
        parsed = self._parse_scores_json(content)

        valid_ids = {item.chunk_id for item in batch}
        out: list[tuple[str, float]] = []
        for item in parsed:
            chunk_id = str(item.get("chunk_id", ""))
            if chunk_id not in valid_ids:
                continue
            try:
                score = float(item.get("score"))
            except (TypeError, ValueError):
                continue
            score = max(0.0, min(1.0, score))
            out.append((chunk_id, score))
        return out

    def _parse_scores_json(self, content: str) -> list[dict]:
        raw = content.strip()
        # Strip fenced code blocks if present.
        fenced = re.fullmatch(r"```(?:json)?\s*(.*?)\s*```", raw, flags=re.DOTALL)
        if fenced:
            raw = fenced.group(1).strip()

        data = json.loads(raw)
        scores = data.get("scores") if isinstance(data, dict) else None
        if not isinstance(scores, list):
            raise RetrievalProviderError("LLM reranker response missing 'scores' list")
        return [item for item in scores if isinstance(item, dict)]
