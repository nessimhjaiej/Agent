from pathlib import Path, PurePosixPath

import httpx

from app.errors import ConfigurationError, UpstreamServiceError
from app.models import (
    IndexDocumentParams,
    IndexDocumentResult,
    IngestionDocumentResult,
    IngestionRunParams,
    IngestionRunResult,
    RemoveDocumentChunksResult,
)


class IngestionOrchestrator:
    def __init__(self, timeout_seconds: float = 120.0) -> None:
        self._timeout_seconds = timeout_seconds

    def run(self, params: IngestionRunParams) -> IngestionRunResult:
        raw_dir = Path(params.raw_dir).resolve()
        if not raw_dir.exists():
            raise ConfigurationError(f"Raw directory not found: {raw_dir}")

        files = self._discover_files(
            raw_dir=raw_dir,
            patterns=params.patterns,
            recursive=params.recursive,
        )

        if not files:
            return IngestionRunResult(
                documents_processed=0,
                documents_failed=0,
                chunks_total=0,
                chunks_indexed=0,
                failed_files=[],
                results=[],
            )

        source_paths = [
            self._to_preprocessing_source_path(
                local_file=file_path,
                local_root=raw_dir,
                source_root_in_preprocessing=params.source_root_in_preprocessing,
            )
            for file_path in files
        ]

        if params.dry_run:
            dry_results = [
                IngestionDocumentResult(
                    file_path=str(file_path),
                    source_path=source_path,
                    chunks_count=0,
                    indexed_count=0,
                    status="dry_run",
                )
                for file_path, source_path in zip(files, source_paths)
            ]
            return IngestionRunResult(
                documents_processed=len(files),
                documents_failed=0,
                chunks_total=0,
                chunks_indexed=0,
                failed_files=[],
                results=dry_results,
            )

        total_docs = 0
        total_chunks = 0
        total_indexed = 0
        failed_files: list[str] = []
        document_results: list[IngestionDocumentResult] = []

        with httpx.Client(timeout=self._timeout_seconds) as client:
            self._call_health(client, params.preprocessing_base_url, "preprocessing-service")
            self._call_health(client, params.embedding_base_url, "embedding-service")

            for file_path, source_path in zip(files, source_paths):
                try:
                    chunks = self._call_preprocessing(
                        client=client,
                        preprocessing_url=params.preprocessing_base_url,
                        source_path=source_path,
                    )
                    indexed_count = self._index_chunks_in_batches(
                        client=client,
                        embedding_url=params.embedding_base_url,
                        chunks=chunks,
                        batch_size=params.embedding_batch_size,
                    )

                    total_docs += 1
                    total_chunks += len(chunks)
                    total_indexed += indexed_count
                    document_results.append(
                        IngestionDocumentResult(
                            file_path=str(file_path),
                            source_path=source_path,
                            chunks_count=len(chunks),
                            indexed_count=indexed_count,
                            status="ok",
                        )
                    )
                except Exception as exc:  # noqa: BLE001
                    failed_files.append(str(file_path))
                    document_results.append(
                        IngestionDocumentResult(
                            file_path=str(file_path),
                            source_path=source_path,
                            chunks_count=0,
                            indexed_count=0,
                            status="error",
                            error=str(exc),
                        )
                    )

        return IngestionRunResult(
            documents_processed=total_docs,
            documents_failed=len(failed_files),
            chunks_total=total_chunks,
            chunks_indexed=total_indexed,
            failed_files=failed_files,
            results=document_results,
        )

    def index_document(self, params: IndexDocumentParams) -> IndexDocumentResult:
        if not params.source_url and not params.source_path:
            raise ConfigurationError("Either source_url or source_path must be provided")

        with httpx.Client(timeout=self._timeout_seconds) as client:
            self._call_health(client, params.preprocessing_base_url, "preprocessing-service")
            self._call_health(client, params.embedding_base_url, "embedding-service")

            resolved_source_path = params.source_path or self._download_source_file(
                client=client,
                source_url=params.source_url or "",
                target_source_path=params.target_relative_path,
            )

            exists = False
            if params.skip_if_exists:
                exists = self._source_exists_in_weaviate(
                    client=client,
                    weaviate_base_url=params.weaviate_http_url,
                    collection=params.weaviate_collection,
                    source_uri=resolved_source_path,
                )
                if exists:
                    return IndexDocumentResult(
                        status="already_exists",
                        source_path=resolved_source_path,
                        exists_in_weaviate=True,
                        indexed=False,
                        chunks_count=0,
                        indexed_count=0,
                        message="Document already indexed in Weaviate",
                    )

            chunks = self._call_preprocessing(
                client=client,
                preprocessing_url=params.preprocessing_base_url,
                source_path=resolved_source_path,
            )
            indexed_count = self._index_chunks_in_batches(
                client=client,
                embedding_url=params.embedding_base_url,
                chunks=chunks,
                batch_size=params.embedding_batch_size,
            )
            return IndexDocumentResult(
                status="indexed",
                source_path=resolved_source_path,
                exists_in_weaviate=exists,
                indexed=True,
                chunks_count=len(chunks),
                indexed_count=indexed_count,
                message="Document indexed successfully",
            )

    def check_documents_exist(
        self,
        weaviate_base_url: str,
        collection: str,
        source_paths: list[str],
    ) -> dict[str, bool]:
        if not source_paths:
            return {}
        result: dict[str, bool] = {}
        with httpx.Client(timeout=self._timeout_seconds) as client:
            for source_path in source_paths:
                result[source_path] = self._source_exists_in_weaviate(
                    client=client,
                    weaviate_base_url=weaviate_base_url,
                    collection=collection,
                    source_uri=source_path,
                )
        return result

    def remove_document_chunks(
        self,
        weaviate_base_url: str,
        collection: str,
        source_paths: list[str],
    ) -> RemoveDocumentChunksResult:
        unique_paths = list(dict.fromkeys(path for path in source_paths if path))
        if not unique_paths:
            return RemoveDocumentChunksResult(
                status="ok",
                requested_count=0,
                matched_objects_count=0,
                deleted_count=0,
            )

        matched_total = 0
        deleted_total = 0
        with httpx.Client(timeout=self._timeout_seconds) as client:
            for source_path in unique_paths:
                object_ids = self._lookup_weaviate_object_ids_by_source(
                    client=client,
                    weaviate_base_url=weaviate_base_url,
                    collection=collection,
                    source_uri=source_path,
                )
                matched_total += len(object_ids)
                for object_id in object_ids:
                    self._delete_weaviate_object(
                        client=client,
                        weaviate_base_url=weaviate_base_url,
                        object_id=object_id,
                    )
                    deleted_total += 1

        return RemoveDocumentChunksResult(
            status="ok",
            requested_count=len(unique_paths),
            matched_objects_count=matched_total,
            deleted_count=deleted_total,
        )

    def _discover_files(self, raw_dir: Path, patterns: list[str], recursive: bool) -> list[Path]:
        files: set[Path] = set()
        for pattern in patterns:
            iterator = raw_dir.rglob(pattern) if recursive else raw_dir.glob(pattern)
            for path in iterator:
                if path.is_file():
                    files.add(path.resolve())
        return sorted(files)

    def _to_preprocessing_source_path(
        self,
        local_file: Path,
        local_root: Path,
        source_root_in_preprocessing: str,
    ) -> str:
        relative = local_file.relative_to(local_root)
        posix_relative = PurePosixPath(*relative.parts)
        source_root = PurePosixPath(source_root_in_preprocessing)
        return str(source_root.joinpath(posix_relative))

    def _call_health(self, client: httpx.Client, base_url: str, service_name: str) -> None:
        try:
            response = client.get(f"{base_url.rstrip('/')}/health")
        except httpx.HTTPError as exc:
            raise UpstreamServiceError(f"{service_name} health check failed: {exc}") from exc
        self._raise_for_status(response, f"{service_name} health check")

    def _call_preprocessing(
        self,
        client: httpx.Client,
        preprocessing_url: str,
        source_path: str,
    ) -> list[dict]:
        try:
            response = client.post(
                f"{preprocessing_url.rstrip('/')}/preprocessing/process-source",
                json={"source_path": source_path},
            )
        except httpx.HTTPError as exc:
            raise UpstreamServiceError(f"preprocessing request failed: {exc}") from exc
        self._raise_for_status(response, f"preprocessing for {source_path}")
        payload = response.json()
        chunks = payload.get("chunks", [])
        if not isinstance(chunks, list):
            raise UpstreamServiceError("Unexpected preprocessing response: 'chunks' must be a list")
        return chunks

    def _index_chunks_in_batches(
        self,
        client: httpx.Client,
        embedding_url: str,
        chunks: list[dict],
        batch_size: int,
    ) -> int:
        indexed_count = 0
        for start in range(0, len(chunks), batch_size):
            batch = chunks[start : start + batch_size]
            try:
                response = client.post(
                    f"{embedding_url.rstrip('/')}/embedding/index-chunks",
                    json={"chunks": batch},
                )
            except httpx.HTTPError as exc:
                raise UpstreamServiceError(f"embedding/index request failed: {exc}") from exc
            self._raise_for_status(response, "embedding/index")
            payload = response.json()
            indexed_count += int(payload.get("indexed_count", 0))
        return indexed_count

    def _raise_for_status(self, response: httpx.Response, context: str) -> None:
        if response.status_code < 400:
            return
        detail = response.text.strip()
        raise UpstreamServiceError(f"{context} failed ({response.status_code}): {detail}")

    def _download_source_file(
        self,
        client: httpx.Client,
        source_url: str,
        target_source_path: str,
    ) -> str:
        target_path = Path(target_source_path)
        target_path.parent.mkdir(parents=True, exist_ok=True)

        try:
            response = client.get(source_url, follow_redirects=True)
        except httpx.HTTPError as exc:
            raise UpstreamServiceError(f"download failed: {exc}") from exc
        self._raise_for_status(response, f"download from {source_url}")
        target_path.write_bytes(response.content)
        return target_source_path

    def _source_exists_in_weaviate(
        self,
        client: httpx.Client,
        weaviate_base_url: str,
        collection: str,
        source_uri: str,
    ) -> bool:
        escaped = source_uri.replace("\\", "\\\\").replace('"', '\\"')
        query = (
            "{ Get { "
            f"{collection}(where: {{path: [\"source_uri\"], operator: Equal, valueText: \"{escaped}\"}}, limit: 1) "
            "{ source_uri } } }"
        )
        try:
            response = client.post(
                f"{weaviate_base_url.rstrip('/')}/v1/graphql",
                json={"query": query},
            )
        except httpx.HTTPError as exc:
            raise UpstreamServiceError(f"weaviate graphql lookup failed: {exc}") from exc
        self._raise_for_status(response, "weaviate graphql lookup")
        payload = response.json()
        hits = (
            payload.get("data", {})
            .get("Get", {})
            .get(collection, [])
        )
        return isinstance(hits, list) and len(hits) > 0

    def _lookup_weaviate_object_ids_by_source(
        self,
        client: httpx.Client,
        weaviate_base_url: str,
        collection: str,
        source_uri: str,
    ) -> list[str]:
        escaped = source_uri.replace("\\", "\\\\").replace('"', '\\"')
        query = (
            "{ Get { "
            f"{collection}(where: {{path: [\"source_uri\"], operator: Equal, valueText: \"{escaped}\"}}, limit: 5000) "
            "{ _additional { id } } } }"
        )
        try:
            response = client.post(
                f"{weaviate_base_url.rstrip('/')}/v1/graphql",
                json={"query": query},
            )
        except httpx.HTTPError as exc:
            raise UpstreamServiceError(f"weaviate graphql lookup failed: {exc}") from exc
        self._raise_for_status(response, "weaviate graphql lookup")
        payload = response.json()
        hits = payload.get("data", {}).get("Get", {}).get(collection, [])
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

    def _delete_weaviate_object(
        self,
        client: httpx.Client,
        weaviate_base_url: str,
        object_id: str,
    ) -> None:
        try:
            response = client.delete(f"{weaviate_base_url.rstrip('/')}/v1/objects/{object_id}")
        except httpx.HTTPError as exc:
            raise UpstreamServiceError(f"weaviate object delete failed: {exc}") from exc
        self._raise_for_status(response, f"weaviate delete object {object_id}")
