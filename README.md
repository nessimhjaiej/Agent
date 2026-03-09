# Agentic RAG Platform

Microservice-based Retrieval-Augmented Generation (RAG) platform with:

- Supabase auth + document metadata/storage
- Preprocessing + chunking
- Embedding + Weaviate indexing
- Retrieval + generation services
- React admin/user frontend

## Stack

- Frontend: React + Vite
- Backend: FastAPI services
- Vector DB: Weaviate
- Metadata/File storage: Supabase
- Containers: Docker Compose

## Prerequisites

- Docker Desktop
- Node.js 20+
- npm
- A Supabase project
- OpenAI API key

## 1) Environment Setup

Create root `.env` from `.env.example` and fill real values.

Required minimum:

- `OPENAI_KEY`
- `AUTH_SUPABASE_URL`
- `AUTH_SUPABASE_KEY`
- `WEAVIATE_HTTP_URL` (for local Docker: `http://localhost:8080`)
- `WEAVIATE_COLLECTION` (default: `Chunk`)

Create frontend env:

1. Copy `frontend/.env.example` to `frontend/.env`
2. Fill:
- `VITE_SUPABASE_URL`
- `VITE_SUPABASE_ANON_KEY`
- `VITE_SUPABASE_DOCS_BUCKET` (default: `documents`)
- `VITE_SUPABASE_DOCS_TABLE` (default: `documents`)

## 2) Supabase Setup

### 2.1 Create `documents` table

Run SQL from:

- `docs/supabase_documents_table.sql`

This creates:

- `public.documents`
- RLS policies for `select/insert/update/delete` on own rows (`auth.uid() = user_id`)

### 2.2 Create storage bucket

In Supabase Storage, create bucket:

- `documents`

Set bucket visibility:

- Private (recommended)

### 2.3 Storage RLS policies (required)

If upload fails with `new row violates row-level security policy`, add storage policies in Supabase SQL Editor:

```sql
create policy "docs_storage_select_own"
on storage.objects
for select
to authenticated
using (
  bucket_id = 'documents'
  and (storage.foldername(name))[2] = auth.uid()::text
);

create policy "docs_storage_insert_own"
on storage.objects
for insert
to authenticated
with check (
  bucket_id = 'documents'
  and (storage.foldername(name))[2] = auth.uid()::text
);

create policy "docs_storage_update_own"
on storage.objects
for update
to authenticated
using (
  bucket_id = 'documents'
  and (storage.foldername(name))[2] = auth.uid()::text
);

create policy "docs_storage_delete_own"
on storage.objects
for delete
to authenticated
using (
  bucket_id = 'documents'
  and (storage.foldername(name))[2] = auth.uid()::text
);
```

Note:

- Upload paths are like `pending/<user_id>/<filename>` then moved to `validated/<user_id>/...` or `rejected/<user_id>/...`.

## 3) Start Infrastructure + Services

From project root:

```powershell
docker compose up -d --build
```

This starts:

- `weaviate` (8080)
- `auth-service` (8001)
- `preprocessing-service` (8000)
- `embedding-service` (8002)
- `retrieval-service` (8003)
- `generation-service` (8004)
- `ingestion-service` (8005)

Check status:

```powershell
docker ps --format "table {{.Names}}\t{{.Status}}\t{{.Ports}}"
```

## 4) Bootstrap Weaviate Schema

Run once (or whenever resetting Weaviate):

```powershell
powershell -ExecutionPolicy Bypass -File infrastructure\weaviate\bootstrap-schema.ps1 `
  -BaseUrl "http://localhost:8080" `
  -SchemaPath "infrastructure\weaviate\schema.chunk.json"
```

Schema file:

- `infrastructure/weaviate/schema.chunk.json`

## 5) Start Frontend

```powershell
cd frontend
npm install
npm run dev
```

Frontend runs on:

- `http://localhost:5173`

## 6) Smoke Checks

Backend health:

```powershell
Invoke-RestMethod http://localhost:8000/health
Invoke-RestMethod http://localhost:8002/health
Invoke-RestMethod http://localhost:8003/health
Invoke-RestMethod http://localhost:8004/health
Invoke-RestMethod http://localhost:8005/health
```

Weaviate ready:

```powershell
Invoke-RestMethod http://localhost:8080/v1/.well-known/ready
```

## 7) Document Workflow

In Admin page:

1. Drag-and-drop upload (multiple files supported)
2. Validate or reject docs (single or bulk)
3. On validation, system auto-checks Weaviate and embeds if not already indexed
4. Deleting a document removes:
- Supabase storage object
- Supabase `documents` row
- Related Weaviate chunks

## Troubleshooting

- `Could not find table public.documents`
  - Run SQL file `docs/supabase_documents_table.sql`.
- `Bucket not found`
  - Create `documents` bucket in Supabase Storage.
- `new row violates row-level security policy`
  - Add storage RLS policies (section 2.3).
- Frontend `HTTP 502` on chat
  - Ensure `retrieval-service` and `generation-service` are both up.
- Weaviate schema/collection missing
  - Run bootstrap script in section 4.

## Useful Commands

Tail logs:

```powershell
docker logs generation-service --tail 120
docker logs retrieval-service --tail 120
docker logs ingestion-service --tail 120
```

Rebuild specific service:

```powershell
docker compose up -d --build ingestion-service
docker compose up -d --build retrieval-service generation-service
```

Run ingestion service tests:

```powershell
pytest services\ingestion-service\tests -q
```
