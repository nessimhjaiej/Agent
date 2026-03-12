from __future__ import annotations

import mimetypes
import time
from pathlib import PurePosixPath

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

    def list_documents(self, user_id: str) -> list[DocumentRecord]:
        if not user_id.strip():
            raise ValueError("user_id is required")

        with self._client() as client:
            response = client.get(
                self._rest_url(self._settings.supabase_docs_table),
                params={
                    "select": "id,user_id,original_name,storage_path,status,embedded,size_bytes,created_at,embedded_at",
                    "user_id": f"eq.{user_id.strip()}",
                    "order": "created_at.desc",
                },
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
            document = self._get_document(client, document_id)
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
