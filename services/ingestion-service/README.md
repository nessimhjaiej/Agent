# ingestion-service

FastAPI service that manages the **document lifecycle** over Supabase Storage and
the `public.documents` table. It is the CRUD layer the admin UI uses to upload,
list, validate/reject, preview, and delete documents.

A document's `status` mirrors its storage folder:

```
pending/<user_id>/<file>    →  validated/<user_id>/<file>    →  rejected/<user_id>/<file>
```

Only **validated** documents are later embedded (by `embedding-service`). Uploads
and metadata writes use the Supabase **service-role** key, so this service needs no
Storage RLS policies to function.

## API endpoints

| Method & path | Auth | Purpose |
|---------------|------|---------|
| `GET /health` | — | service status / version |
| `GET /ingestion/documents` | verified user | list documents (optionally `?user_id=`) |
| `POST /ingestion/documents/upload` | verified user | upload a file → `pending/<user_id>/...` + a row |
| `POST /ingestion/documents/{id}/status` | admin | move between pending/validated/rejected |
| `GET /ingestion/documents/{id}/signed-url` | verified user | time-limited URL for in-app preview |
| `GET /ingestion/documents/signed-url/by-storage-path` | verified user | signed URL by storage path |
| `DELETE /ingestion/documents/{id}` | admin | delete the storage object **and** the row |

Caller tokens are validated against `auth-service` (`_require_verified_user` /
`_require_admin_user`). Document actions emit info events to `security-service`.

## Folder overview

- `app/main.py` — FastAPI entrypoint and router registration.
- `app/routers/ingestion.py` — endpoints + auth guards + event emission.
- `app/routers/health.py` — health check.
- `app/service.py` — `IngestionService`: Supabase Storage + REST calls
  (`upload_document`, `update_document_status`, `get_document_signed_url`,
  `delete_document`, flexible document lookup helpers).
- `app/models.py` — domain dataclasses (`DocumentRecord`, `UploadDocumentParams`, …).
- `app/schemas.py` — Pydantic request/response models.
- `app/errors.py` — `ConfigurationError`, `UpstreamServiceError`, `AuthorizationError`.
- `app/security_events.py` — emits events to `security-service`.
- `tests/` — API-contract tests.

## Run

```powershell
uvicorn app.main:app --reload --app-dir services/ingestion-service --port 8005
```

Interactive docs: `http://127.0.0.1:8005/docs`

## Environment variables

| Var | Required | Purpose |
|-----|----------|---------|
| `AUTH_SUPABASE_URL` | ✅ | Supabase project URL |
| `AUTH_SUPABASE_KEY` | ✅ | Supabase **service-role** key (Storage + table writes) |
| `AUTH_BASE_URL` | | auth-service base URL (token verification) |
| `SECURITY_BASE_URL` | | security-service base URL (event emission) |

See `app/config.py` for the document table/bucket names, signed-URL TTL, and HTTP
timeout defaults.
