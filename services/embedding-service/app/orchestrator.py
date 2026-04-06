from __future__ import annotations

from pathlib import Path

import httpx

from app.config import Settings
from app.errors import ConfigurationError, EmbeddingServiceError, VectorStoreError
from app.models import Chunk, ChunkMetadata, IndexChunkResult, IndexDocumentResult, RemoveDocumentResult
from embeddings.base import BaseEmbedder
from embeddings.openai_embedder import OpenAIEmbedder
from indexers.base import BaseVectorIndexer
from indexers.weaviate_indexer import WeaviateIndexer


class EmbeddingOrchestrator:
    def __init__(
        self,
        settings: Settings,
        embedder: BaseEmbedder | None = None,
        indexer: BaseVectorIndexer | None = None,
    ) -> None:
        self._settings = settings
        self._embedder = embedder or OpenAIEmbedder(settings)
        self._indexer = indexer or WeaviateIndexer(settings)

    def index_chunks(self, chunks: list[Chunk]) -> list[IndexChunkResult]:
        seen_counts: dict[str, int] = {}
        unique_chunks: list[Chunk] = []

        for chunk in chunks:
            count = seen_counts.get(chunk.chunk_id, 0) + 1
            seen_counts[chunk.chunk_id] = count
            if count == 1:
                unique_chunks.append(chunk)

        if not unique_chunks:
            return []

        vectors = self._embedder.embed_texts([chunk.chunk_text for chunk in unique_chunks])
        if len(vectors) != len(unique_chunks):
            raise VectorStoreError("Embedding output count does not match chunk count")

        self._validate_vector_dimensions(vectors)
        index_results = self._indexer.upsert_chunks(unique_chunks, vectors)
        by_chunk_id = {result.chunk_id: result for result in index_results}

        final_results: list[IndexChunkResult] = []
        emitted_first: set[str] = set()
        for chunk in chunks:
            if chunk.chunk_id in emitted_first:
                final_results.append(
                    IndexChunkResult(
                        chunk_id=chunk.chunk_id,
                        indexed=False,
                        reason="duplicate_chunk_id_in_request",
                    )
                )
                continue
            emitted_first.add(chunk.chunk_id)
            final_results.append(
                by_chunk_id.get(
                    chunk.chunk_id,
                    IndexChunkResult(
                        chunk_id=chunk.chunk_id,
                        indexed=False,
                        reason="index_result_missing",
                    ),
                )
            )
        return final_results

    def index_document(self, document_id: str, skip_if_embedded: bool = True) -> IndexDocumentResult:
        with self._client() as client:
            document = self._get_document(client, document_id)
            if document["status"] != "validated":
                raise ConfigurationError("Only validated documents can be indexed")
            if skip_if_embedded and document.get("embedded") is True:
                return IndexDocumentResult(
                    status="already_embedded",
                    document_id=str(document["id"]),
                    storage_path=str(document["storage_path"]),
                    chunks_count=0,
                    indexed_count=0,
                    embedded=True,
                    message="Document is already marked embedded",
                )

            local_path = self._download_document(client, document)
            chunks = self._call_preprocessing(client, str(local_path), str(document["id"]))
            index_results = self.index_chunks(chunks)
            indexed_count = sum(1 for item in index_results if item.indexed)

            update_response = client.patch(
                self._rest_url(self._settings.supabase_docs_table),
                params={"id": f"eq.{document_id}", "select": "id,storage_path"},
                headers={
                    **self._json_headers(),
                    "Prefer": "return=representation",
                },
                json={
                    "embedded": True,
                    "embedded_at": self._utc_now_iso(),
                },
            )
            self._raise_for_status(update_response, f"mark embedded {document_id}")

        return IndexDocumentResult(
            status="indexed",
            document_id=str(document["id"]),
            storage_path=str(document["storage_path"]),
            chunks_count=len(chunks),
            indexed_count=indexed_count,
            embedded=True,
            message="Document preprocessed, embedded, and stored in Weaviate",
        )

    def remove_document(self, document_id: str) -> RemoveDocumentResult:
        with self._client() as client:
            document = self._get_document(client, document_id)
            source_uri = str(self._local_document_path(str(document["storage_path"])))
            object_ids = self._lookup_weaviate_object_ids_by_source(
                client=client,
                source_uri=source_uri,
            )
            for object_id in object_ids:
                self._delete_weaviate_object(client=client, object_id=object_id)

            update_response = client.patch(
                self._rest_url(self._settings.supabase_docs_table),
                params={"id": f"eq.{document_id}"},
                headers=self._json_headers(),
                json={"embedded": False, "embedded_at": None},
            )
            self._raise_for_status(update_response, f"clear embedded state {document_id}")

        return RemoveDocumentResult(
            status="ok",
            document_id=str(document["id"]),
            storage_path=str(document["storage_path"]),
            matched_objects_count=len(object_ids),
            deleted_count=len(object_ids),
        )

    def _validate_vector_dimensions(self, vectors: list[list[float]]) -> None:
        if not vectors:
            return

        expected = self._settings.embedding_dimensions or len(vectors[0])
        for vector in vectors:
            if len(vector) != expected:
                raise VectorStoreError(
                    f"Vector dimension mismatch. Expected {expected}, got {len(vector)}"
                )

    def _call_preprocessing(
        self,
        client: httpx.Client,
        source_path: str,
        document_id: str,
    ) -> list[Chunk]:
        response = client.post(
            f"{self._settings.preprocessing_base_url.rstrip('/')}/preprocessing/process-source",
            json={"source_path": source_path, "document_id": document_id},
        )
        self._raise_for_status(response, f"preprocessing {source_path}")
        payload = response.json()
        raw_chunks = payload.get("chunks", [])
        if not isinstance(raw_chunks, list):
            raise EmbeddingServiceError("Unexpected preprocessing response")

        chunks: list[Chunk] = []
        for item in raw_chunks:
            if not isinstance(item, dict) or not isinstance(item.get("metadata"), dict):
                raise EmbeddingServiceError("Invalid chunk payload returned by preprocessing")
            metadata = item["metadata"]
            chunks.append(
                Chunk(
                    chunk_id=str(item["chunk_id"]),
                    document_id=str(item["document_id"]),
                    chunk_text=str(item["chunk_text"]),
                    metadata=ChunkMetadata(
                        source_type=str(metadata["source_type"]),
                        source_uri=str(metadata["source_uri"]),
                        language=str(metadata["language"]),
                        chunk_index=int(metadata["chunk_index"]),
                        start_char=int(metadata["start_char"]),
                        end_char=int(metadata["end_char"]),
                        char_count=int(metadata["char_count"]),
                        token_count_estimate=int(metadata["token_count_estimate"]),
                        chunking_strategy=str(metadata["chunking_strategy"]),
                        source_filename=str(metadata["source_filename"]),
                        document_checksum=str(metadata["document_checksum"]),
                        normalization_version=str(metadata["normalization_version"]),
                        pipeline_version=str(metadata["pipeline_version"]),
                        created_at=str(metadata["created_at"]),
                    ),
                )
            )
        return chunks

    def _download_document(self, client: httpx.Client, document: dict) -> Path:
        storage_path = str(document["storage_path"])
        local_path = self._local_document_path(storage_path)
        local_path.parent.mkdir(parents=True, exist_ok=True)
        response = client.get(
            self._storage_url(f"object/{self._settings.supabase_docs_bucket}/{storage_path}"),
            headers=self._auth_headers(),
        )
        self._raise_for_status(response, f"download document {document['id']}")
        local_path.write_bytes(response.content)
        return local_path

    def _local_document_path(self, storage_path: str) -> Path:
        return Path(self._settings.shared_raw_dir).resolve().joinpath("supabase", *Path(storage_path).parts)

    def _get_document(self, client: httpx.Client, document_id: str) -> dict:
        if not document_id.strip():
            raise ValueError("document_id is required")
        response = client.get(
            self._rest_url(self._settings.supabase_docs_table),
            params={
                "select": "id,user_id,original_name,storage_path,status,embedded,size_bytes,created_at,embedded_at",
                "id": f"eq.{document_id.strip()}",
                "limit": 1,
            },
            headers=self._auth_headers(),
        )
        self._raise_for_status(response, f"get document {document_id}")
        payload = response.json()
        if not isinstance(payload, list) or not payload or not isinstance(payload[0], dict):
            raise ConfigurationError(f"Document not found: {document_id}")
        return payload[0]

    def _lookup_weaviate_object_ids_by_source(
        self,
        client: httpx.Client,
        source_uri: str,
    ) -> list[str]:
        escaped = source_uri.replace("\\", "\\\\").replace('"', '\\"')
        query = (
            "{ Get { "
            f"{self._settings.weaviate_collection}(where: {{path: [\"source_uri\"], operator: Equal, valueText: \"{escaped}\"}}, limit: 5000) "
            "{ _additional { id } } } }"
        )
        response = client.post(
            f"{self._settings.weaviate_http_url.rstrip('/')}/v1/graphql",
            json={"query": query},
        )
        self._raise_for_status(response, "weaviate graphql lookup")
        payload = response.json()
        hits = payload.get("data", {}).get("Get", {}).get(self._settings.weaviate_collection, [])
        if not isinstance(hits, list):
            return []

        object_ids: list[str] = []
        for hit in hits:
            if not isinstance(hit, dict):
                continue
            additional = hit.get("_additional", {})
            if not isinstance(additional, dict):
                continue
            object_id = additional.get("id")
            if isinstance(object_id, str) and object_id.strip():
                object_ids.append(object_id.strip())
        return object_ids

    def _delete_weaviate_object(self, client: httpx.Client, object_id: str) -> None:
        response = client.delete(f"{self._settings.weaviate_http_url.rstrip('/')}/v1/objects/{object_id}")
        self._raise_for_status(response, f"weaviate delete object {object_id}")

    def _client(self) -> httpx.Client:
        return httpx.Client(timeout=self._settings.http_timeout_seconds, follow_redirects=True)

    def _rest_url(self, path: str) -> str:
        return f"{self._settings.supabase_url.rstrip('/')}/rest/v1/{path.lstrip('/')}"

    def _storage_url(self, path: str) -> str:
        return f"{self._settings.supabase_url.rstrip('/')}/storage/v1/{path.lstrip('/')}"

    def _auth_headers(self) -> dict[str, str]:
        return {
            "apikey": self._settings.supabase_key,
            "Authorization": f"Bearer {self._settings.supabase_key}",
        }

    def _json_headers(self) -> dict[str, str]:
        return {
            **self._auth_headers(),
            "Content-Type": "application/json",
        }

    def _raise_for_status(self, response: httpx.Response, context: str) -> None:
        if response.status_code < 400:
            return
        raise EmbeddingServiceError(f"{context} failed ({response.status_code}): {response.text.strip()}")

    def _utc_now_iso(self) -> str:
        from datetime import datetime, timezone

        return datetime.now(timezone.utc).isoformat()
