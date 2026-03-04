from uuid import NAMESPACE_URL, uuid5

import httpx

from app.config import Settings
from app.errors import VectorStoreError
from app.models import Chunk, IndexChunkResult
from indexers.base import BaseVectorIndexer


class WeaviateIndexer(BaseVectorIndexer):
    def __init__(self, settings: Settings) -> None:
        self._base_url = settings.weaviate_http_url.rstrip("/")
        self._collection = settings.weaviate_collection
        self._batch_size = settings.weaviate_batch_size
        self._timeout = settings.weaviate_startup_timeout_seconds
        self._fail_if_collection_missing = settings.fail_if_collection_missing
        self._embedding_model = settings.embedding_model
        self._embedding_dimensions = settings.embedding_dimensions
        self._client = httpx.Client(timeout=self._timeout)

        if self._fail_if_collection_missing:
            self._assert_collection_exists()

    @property
    def name(self) -> str:
        return "weaviate"

    def upsert_chunks(self, chunks: list[Chunk], vectors: list[list[float]]) -> list[IndexChunkResult]:
        if len(chunks) != len(vectors):
            raise VectorStoreError("Chunks and vectors length mismatch")
        if not chunks:
            return []

        results: list[IndexChunkResult] = []
        for start in range(0, len(chunks), self._batch_size):
            batch_chunks = chunks[start : start + self._batch_size]
            batch_vectors = vectors[start : start + self._batch_size]
            results.extend(self._upsert_batch(batch_chunks, batch_vectors))
        return results

    def _upsert_batch(self, chunks: list[Chunk], vectors: list[list[float]]) -> list[IndexChunkResult]:
        results: list[IndexChunkResult] = []
        for chunk, vector in zip(chunks, vectors):
            object_id = self._build_object_uuid(chunk)
            object_body = {
                "class": self._collection,
                "id": object_id,
                "properties": self._to_properties(chunk),
                "vector": vector,
            }
            results.append(
                self._upsert_object(
                    chunk_id=chunk.chunk_id,
                    object_id=object_id,
                    object_body=object_body,
                )
            )
        return results

    def _upsert_object(
        self,
        chunk_id: str,
        object_id: str,
        object_body: dict[str, object],
    ) -> IndexChunkResult:
        update_url = f"{self._base_url}/v1/objects/{object_id}"
        try:
            update_response = self._client.put(update_url, json=object_body)
        except httpx.HTTPError as exc:
            raise VectorStoreError(f"Weaviate connection error: {exc}") from exc

        if update_response.status_code in {200, 204}:
            return IndexChunkResult(chunk_id=chunk_id, indexed=True, reason="upsert_update")

        # Fallback to create for new objects when update endpoint indicates missing object.
        if update_response.status_code == 404 or self._is_missing_object(update_response):
            create_url = f"{self._base_url}/v1/objects"
            try:
                create_response = self._client.post(create_url, json=object_body)
            except httpx.HTTPError as exc:
                raise VectorStoreError(f"Weaviate connection error: {exc}") from exc

            if create_response.status_code in {200, 201}:
                return IndexChunkResult(chunk_id=chunk_id, indexed=True, reason="upsert_create")
            return IndexChunkResult(
                chunk_id=chunk_id,
                indexed=False,
                reason=self._error_from_response(create_response),
            )

        return IndexChunkResult(
            chunk_id=chunk_id,
            indexed=False,
            reason=self._error_from_response(update_response),
        )

    def _assert_collection_exists(self) -> None:
        try:
            response = self._client.get(f"{self._base_url}/v1/schema")
        except httpx.HTTPError as exc:
            raise VectorStoreError(f"Weaviate schema check failed: {exc}") from exc

        if response.status_code >= 400:
            raise VectorStoreError(
                f"Weaviate schema check failed {response.status_code}: {response.text}"
            )

        payload = response.json()
        classes = payload.get("classes", [])
        class_names = {entry.get("class") for entry in classes if isinstance(entry, dict)}
        if self._collection not in class_names:
            raise VectorStoreError(
                f"Weaviate collection '{self._collection}' not found. Run schema bootstrap first."
            )

    def _build_object_uuid(self, chunk: Chunk) -> str:
        dim_marker = self._embedding_dimensions or 0
        seed = (
            f"{chunk.chunk_id}|{chunk.metadata.document_checksum}|"
            f"{self._embedding_model}|{dim_marker}"
        )
        return str(uuid5(NAMESPACE_URL, seed))

    def _to_properties(self, chunk: Chunk) -> dict[str, object]:
        return {
            "chunk_id": chunk.chunk_id,
            "document_id": chunk.document_id,
            "chunk_text": chunk.chunk_text,
            "source_type": chunk.metadata.source_type,
            "source_uri": chunk.metadata.source_uri,
            "source_filename": chunk.metadata.source_filename,
            "language": chunk.metadata.language,
            "chunk_index": chunk.metadata.chunk_index,
            "start_char": chunk.metadata.start_char,
            "end_char": chunk.metadata.end_char,
            "char_count": chunk.metadata.char_count,
            "token_count_estimate": chunk.metadata.token_count_estimate,
            "chunking_strategy": chunk.metadata.chunking_strategy,
            "embedding_model": self._embedding_model,
            "document_checksum": chunk.metadata.document_checksum,
            "normalization_version": chunk.metadata.normalization_version,
            "pipeline_version": chunk.metadata.pipeline_version,
            "created_at": chunk.metadata.created_at,
        }

    def _error_from_response(self, response: httpx.Response) -> str:
        try:
            payload = response.json()
            if isinstance(payload, dict):
                details = payload.get("error") or payload.get("message")
                if isinstance(details, list) and details:
                    first = details[0]
                    if isinstance(first, dict):
                        message = first.get("message")
                        if isinstance(message, str) and message.strip():
                            return message.strip()
                if isinstance(details, str) and details.strip():
                    return details.strip()
        except ValueError:
            pass

        text = response.text.strip()
        if text:
            return f"Weaviate request failed {response.status_code}: {text}"
        return f"Weaviate request failed {response.status_code}"

    def _is_missing_object(self, response: httpx.Response) -> bool:
        message = self._error_from_response(response).lower()
        return "no object with id" in message
