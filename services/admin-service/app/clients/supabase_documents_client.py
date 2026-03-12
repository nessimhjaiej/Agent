from __future__ import annotations

from app.config import Settings


class SupabaseDocumentsClient:
    def __init__(self, settings: Settings, client=None) -> None:  # noqa: ANN001
        self._settings = settings
        self._client = client

    def list_documents(self) -> list[dict]:
        client = self._ensure_client()
        response = (
            client.table(self._settings.supabase_docs_table)
            .select("id,user_id,original_name,storage_path,status,embedded,created_at")
            .execute()
        )
        return response.data or []

    def delete_document(self, storage_path: str) -> dict:
        normalized = str(storage_path).strip().lstrip("/")
        if not normalized:
            raise ValueError("storage_path is required")

        client = self._ensure_client()
        lookup = (
            client.table(self._settings.supabase_docs_table)
            .select("id,user_id,original_name,storage_path,status,embedded,created_at")
            .eq("storage_path", normalized)
            .execute()
        )
        document_rows = lookup.data or []
        if not document_rows:
            raise ValueError(f"Supabase document not found: {normalized}")

        client.storage.from_(self._settings.supabase_docs_bucket).remove([normalized])
        delete_result = (
            client.table(self._settings.supabase_docs_table)
            .delete()
            .eq("storage_path", normalized)
            .execute()
        )
        return {
            "storage_path": normalized,
            "documents_deleted": len(delete_result.data or []),
            "document": document_rows[0],
        }

    def _ensure_client(self):  # noqa: ANN201
        if self._client is not None:
            return self._client
        if not self._settings.supabase_url or not self._settings.supabase_key:
            raise ValueError("Supabase admin client is not configured")
        from supabase import create_client

        self._client = create_client(self._settings.supabase_url, self._settings.supabase_key)
        return self._client
