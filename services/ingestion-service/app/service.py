from __future__ import annotations

import mimetypes
import re
import time
from pathlib import PurePosixPath
from uuid import UUID

import httpx

from app.config import Settings
from app.errors import ConfigurationError, UpstreamServiceError
from app.models import (
    DeleteDocumentResult,
    DocumentRecord,
    SignedUrlResult,
    UpdateDocumentStatusParams,
    UploadDocumentParams,
)


class IngestionService:
    def __init__(self, settings: Settings) -> None:
        self._settings = settings
        self._settings.validate()

    def list_documents(self, user_id: str | None = None) -> list[DocumentRecord]:
        normalized_user_id = (user_id or "").strip()
        params = {
            "select": "id,user_id,original_name,storage_path,status,embedded,size_bytes,created_at,embedded_at",
            "order": "created_at.desc",
        }
        if normalized_user_id:
            params["user_id"] = f"eq.{normalized_user_id}"

        with self._client() as client:
            response = client.get(
                self._rest_url(self._settings.supabase_docs_table),
                params=params,
                headers=self._auth_headers(),
            )
            self._raise_for_status(response, "list documents")
            payload = response.json()
        return [self._to_document_record(item) for item in payload if isinstance(item, dict)]

    def upload_document(self, params: UploadDocumentParams) -> DocumentRecord:
        if not params.user_id.strip():
            raise ValueError("user_id is required")
        if not params.original_name.strip():
            raise ValueError("original_name is required")
        if not params.content:
            raise ValueError("file content is required")

        sanitized_name = params.original_name.replace(" ", "_")
        storage_path = f"pending/{params.user_id.strip()}/{int(time.time() * 1000)}-{sanitized_name}"
        content_type = params.content_type or mimetypes.guess_type(params.original_name)[0] or "application/octet-stream"

        with self._client() as client:
            upload_response = client.post(
                self._storage_object_url(storage_path),
                headers={
                    **self._storage_headers(content_type=content_type),
                    "x-upsert": "false",
                },
                content=params.content,
            )
            self._raise_for_status(upload_response, f"upload document {params.original_name}")

            insert_response = client.post(
                self._rest_url(self._settings.supabase_docs_table),
                headers={
                    **self._json_headers(),
                    "Prefer": "return=representation",
                },
                json={
                    "user_id": params.user_id.strip(),
                    "original_name": params.original_name,
                    "storage_path": storage_path,
                    "status": "pending",
                    "embedded": False,
                    "size_bytes": params.size_bytes,
                },
            )
            try:
                self._raise_for_status(insert_response, "insert document metadata")
            except Exception:
                client.delete(self._storage_object_url(storage_path), headers=self._auth_headers())
                raise

            payload = insert_response.json()

        if not isinstance(payload, list) or not payload or not isinstance(payload[0], dict):
            raise UpstreamServiceError("Supabase did not return inserted document metadata")
        return self._to_document_record(payload[0])

    def update_document_status(self, params: UpdateDocumentStatusParams) -> DocumentRecord:
        if params.target_status not in {"pending", "validated", "rejected"}:
            raise ValueError("target_status must be one of pending, validated, rejected")

        with self._client() as client:
            current = self._get_document(client, params.document_id)
            filename = PurePosixPath(current.storage_path).name
            target_path = f"{params.target_status}/{current.user_id}/{filename}"

            if current.storage_path != target_path:
                move_response = client.post(
                    self._storage_url("object/move"),
                    headers=self._json_headers(),
                    json={
                        "bucketId": self._settings.supabase_docs_bucket,
                        "sourceKey": current.storage_path,
                        "destinationKey": target_path,
                    },
                )
                self._raise_for_status(move_response, f"move document {current.id}")

            update_response = client.patch(
                self._rest_url(self._settings.supabase_docs_table),
                params={"id": f"eq.{current.id}", "select": "*"},
                headers={
                    **self._json_headers(),
                    "Prefer": "return=representation",
                },
                json={
                    "storage_path": target_path,
                    "status": params.target_status,
                    "embedded": current.embedded if params.target_status == "validated" else False,
                    "embedded_at": current.embedded_at if params.target_status == "validated" else None,
                },
            )
            self._raise_for_status(update_response, f"update document status {current.id}")
            payload = update_response.json()

        if not isinstance(payload, list) or not payload or not isinstance(payload[0], dict):
            raise UpstreamServiceError("Supabase did not return updated document metadata")
        return self._to_document_record(payload[0])

    def get_document_signed_url(self, document_id: str, expires_in: int | None = None) -> SignedUrlResult:
        ttl = expires_in or self._settings.signed_url_ttl_seconds
        if ttl <= 0:
            raise ValueError("expires_in must be > 0")

        with self._client() as client:
            document = self._get_document_flexible(client, document_id)
            sign_response = client.post(
                self._storage_url(f"object/sign/{self._settings.supabase_docs_bucket}/{document.storage_path}"),
                headers=self._json_headers(),
                json={"expiresIn": ttl},
            )
            self._raise_for_status(sign_response, f"sign document url {document.id}")
            payload = sign_response.json()

        signed_url = payload.get("signedURL") if isinstance(payload, dict) else None
        if not isinstance(signed_url, str) or not signed_url.strip():
            raise UpstreamServiceError("Supabase did not return a signed URL")

        absolute_url = signed_url if signed_url.startswith("http") else f"{self._settings.supabase_url.rstrip('/')}/storage/v1{signed_url}"
        return SignedUrlResult(
            document_id=document.id,
            storage_path=document.storage_path,
            signed_url=absolute_url,
            expires_in=ttl,
        )

    def get_document_signed_url_by_storage_path(
        self,
        storage_path: str,
        expires_in: int | None = None,
    ) -> SignedUrlResult:
        ttl = expires_in or self._settings.signed_url_ttl_seconds
        if ttl <= 0:
            raise ValueError("expires_in must be > 0")
        if not storage_path.strip():
            raise ValueError("storage_path is required")

        normalized_storage_path = storage_path.strip().replace("\\", "/").strip("/")

        with self._client() as client:
            document = self._get_document_by_storage_path(client, normalized_storage_path)
            sign_response = client.post(
                self._storage_url(f"object/sign/{self._settings.supabase_docs_bucket}/{document.storage_path}"),
                headers=self._json_headers(),
                json={"expiresIn": ttl},
            )
            self._raise_for_status(sign_response, f"sign document url {document.id}")
            payload = sign_response.json()

        signed_url = payload.get("signedURL") if isinstance(payload, dict) else None
        if not isinstance(signed_url, str) or not signed_url.strip():
            raise UpstreamServiceError("Supabase did not return a signed URL")

        absolute_url = signed_url if signed_url.startswith("http") else f"{self._settings.supabase_url.rstrip('/')}/storage/v1{signed_url}"
        return SignedUrlResult(
            document_id=document.id,
            storage_path=document.storage_path,
            signed_url=absolute_url,
            expires_in=ttl,
        )

    def delete_document(self, document_id: str) -> DeleteDocumentResult:
        with self._client() as client:
            document = self._get_document(client, document_id)
            storage_response = client.delete(
                self._storage_object_url(document.storage_path),
                headers=self._auth_headers(),
            )
            self._raise_for_status(storage_response, f"delete document object {document.id}")

            delete_response = client.delete(
                self._rest_url(self._settings.supabase_docs_table),
                params={"id": f"eq.{document.id}"},
                headers=self._auth_headers(),
            )
            self._raise_for_status(delete_response, f"delete document row {document.id}")

        return DeleteDocumentResult(
            status="ok",
            document_id=document.id,
            storage_path=document.storage_path,
        )

    def _get_document(self, client: httpx.Client, document_id: str) -> DocumentRecord:
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
        return self._to_document_record(payload[0])

    def _get_document_flexible(self, client: httpx.Client, document_id: str) -> DocumentRecord:
        normalized = document_id.strip()
        if not normalized:
            raise ValueError("document_id is required")

        if self._looks_like_uuid(normalized):
            return self._get_document(client, normalized)

        resolved = self._get_document_by_indexed_document_id(client, normalized)
        if resolved is not None:
            return resolved

        return self._get_document(client, normalized)

    def _get_document_by_storage_path(self, client: httpx.Client, storage_path: str) -> DocumentRecord:
        response = client.get(
            self._rest_url(self._settings.supabase_docs_table),
            params={
                "select": "id,user_id,original_name,storage_path,status,embedded,size_bytes,created_at,embedded_at",
                "storage_path": f"eq.{storage_path}",
                "limit": 1,
            },
            headers=self._auth_headers(),
        )
        self._raise_for_status(response, f"get document by storage path {storage_path}")
        payload = response.json()
        if not isinstance(payload, list) or not payload or not isinstance(payload[0], dict):
            raise ConfigurationError(f"Document not found for storage path: {storage_path}")
        return self._to_document_record(payload[0])

    def _get_document_by_indexed_document_id(
        self,
        client: httpx.Client,
        indexed_document_id: str,
    ) -> DocumentRecord | None:
        source_stem = self._source_stem_from_indexed_document_id(indexed_document_id)
        if not source_stem:
            return None

        response = client.get(
            self._rest_url(self._settings.supabase_docs_table),
            params={
                "select": "id,user_id,original_name,storage_path,status,embedded,size_bytes,created_at,embedded_at",
                "storage_path": f"ilike.*{source_stem}*",
                "order": "created_at.desc",
                "limit": 20,
            },
            headers=self._auth_headers(),
        )
        self._raise_for_status(response, f"resolve indexed document id {indexed_document_id}")
        payload = response.json()
        if not isinstance(payload, list):
            return None

        for item in payload:
            if not isinstance(item, dict):
                continue
            storage_path = str(item.get("storage_path") or "")
            if PurePosixPath(storage_path).stem == source_stem:
                return self._to_document_record(item)
        return None

    @staticmethod
    def _looks_like_uuid(value: str) -> bool:
        try:
            UUID(value)
            return True
        except ValueError:
            return False

    @staticmethod
    def _source_stem_from_indexed_document_id(indexed_document_id: str) -> str:
        match = re.match(r"^(?P<stem>.+)-[0-9a-f]{12}$", indexed_document_id.strip(), re.IGNORECASE)
        if match:
            return match.group("stem")
        return indexed_document_id.strip()

    def _to_document_record(self, item: dict) -> DocumentRecord:
        return DocumentRecord(
            id=str(item.get("id", "")),
            user_id=str(item.get("user_id", "")),
            original_name=str(item.get("original_name") or ""),
            storage_path=str(item.get("storage_path") or ""),
            status=str(item.get("status") or "pending"),
            embedded=bool(item.get("embedded")),
            size_bytes=int(item.get("size_bytes") or 0),
            created_at=str(item.get("created_at") or ""),
            embedded_at=str(item.get("embedded_at")) if item.get("embedded_at") is not None else None,
        )

    def _client(self) -> httpx.Client:
        return httpx.Client(timeout=self._settings.http_timeout_seconds)

    def _rest_url(self, path: str) -> str:
        return f"{self._settings.supabase_url.rstrip('/')}/rest/v1/{path.lstrip('/')}"

    def _storage_url(self, path: str) -> str:
        return f"{self._settings.supabase_url.rstrip('/')}/storage/v1/{path.lstrip('/')}"

    def _storage_object_url(self, storage_path: str) -> str:
        return self._storage_url(
            f"object/{self._settings.supabase_docs_bucket}/{storage_path.lstrip('/')}"
        )

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

    def _storage_headers(self, content_type: str) -> dict[str, str]:
        return {
            **self._auth_headers(),
            "Content-Type": content_type,
        }

    def _raise_for_status(self, response: httpx.Response, context: str) -> None:
        if response.status_code < 400:
            return
        detail = response.text.strip()
        raise UpstreamServiceError(f"{context} failed ({response.status_code}): {detail}")
