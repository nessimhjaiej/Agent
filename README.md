# Agentic RAG Platform

Microservice-based Retrieval-Augmented Generation platform with Supabase auth and storage, document preprocessing, OpenAI embeddings, Weaviate retrieval, answer generation, admin tooling, security monitoring, and a React frontend.

## Stack

- Frontend: React + Vite
- Backend: FastAPI services
- Vector DB: Weaviate
- Auth, metadata, and storage: Supabase
- Containers: Docker Compose

## Prerequisites

- Docker Desktop
- Node.js 20+
- npm
- Python 3.11+ only if running services outside Docker
- A Supabase project
- An OpenAI API key
- Windows PowerShell for the included helper scripts

## 1) Create Environment Files

From the project root, create the backend env file:

```powershell
Copy-Item .env.example .env
```

Fill these required values in `.env`:

```dotenv
OPENAI_KEY=your-openai-api-key
AUTH_SUPABASE_URL=https://your-project.supabase.co
AUTH_SUPABASE_KEY=your-supabase-service-role-key
```

Use the Supabase `service_role` key for `AUTH_SUPABASE_KEY`. The backend performs admin user actions, metadata writes, and storage operations that an anon key usually cannot perform.

Optional backend values:

```dotenv
FRONTEND_URL=http://localhost:5173
WEAVIATE_COLLECTION=Chunk
AUTH_SMTP_HOST=
AUTH_SMTP_PORT=587
AUTH_SMTP_USERNAME=
AUTH_SMTP_PASSWORD=
AUTH_SMTP_FROM_EMAIL=
AUTH_SMTP_FROM_NAME=ICC Agent Admin
AUTH_SMTP_USE_TLS=true
```

Create the frontend env file:

```powershell
Copy-Item frontend\.env.example frontend\.env
```

Fill these values in `frontend/.env`:

```dotenv
VITE_SUPABASE_URL=https://your-project.supabase.co
VITE_SUPABASE_ANON_KEY=your-supabase-anon-key
VITE_SUPABASE_DOCS_BUCKET=documents
VITE_SUPABASE_DOCS_TABLE=documents
VITE_SUPABASE_PROFILE_BUCKET=profiles
```

Use the Supabase anon/public key for `VITE_SUPABASE_ANON_KEY`.

## 2) Configure Supabase

In the Supabase SQL Editor, run these files in order. Each one is safe to re-run,
and together they fully provision the project — **including the Storage buckets**,
so you do not need to create anything by hand:

```text
infrastructure/supabase/supabase_users_table.sql
infrastructure/supabase/app_tables.sql
infrastructure/supabase/security_alerts.sql
infrastructure/supabase/storage_buckets.sql
```

What they create:

- `public.users` + role-sync triggers (keep `role` mirrored with `auth.users`)
- `public.documents`, `public.audit_logs`, `public.login_attempts`
- `public.security_alerts`
- the `documents` (private) and `profiles` (public) Storage buckets + access policies

Documents are stored under `pending/<user_id>/...`, `validated/<user_id>/...`, and
`rejected/<user_id>/...`; profile pictures under `<user_id>/...` in `profiles`. The
backend reaches the `documents` bucket with the service-role key; the browser
uploads profile pictures with the anon key (the policy created by
`storage_buckets.sql` restricts each user to their own folder).

## 3) Start Backend With Docker

From the project root:

```powershell
docker compose up -d --build
```

This starts:

- `weaviate`: http://localhost:8080
- `preprocessing-service`: http://localhost:8000
- `auth-service`: http://localhost:8001
- `embedding-service`: http://localhost:8002
- `retrieval-service`: http://localhost:8003
- `generation-service`: http://localhost:8004
- `ingestion-service`: http://localhost:8005
- `admin-service`: http://localhost:8006
- `security-service`: http://localhost:8007

Useful helper scripts:

```powershell
powershell -ExecutionPolicy Bypass -File .\infrastructure\docker\start-stack.ps1
powershell -ExecutionPolicy Bypass -File .\infrastructure\docker\status.ps1
powershell -ExecutionPolicy Bypass -File .\infrastructure\docker\logs.ps1 -Tail 120
powershell -ExecutionPolicy Bypass -File .\infrastructure\docker\stop-stack.ps1
```

## 4) Bootstrap Weaviate Schema

Run once after Weaviate is running:

```powershell
powershell -ExecutionPolicy Bypass -File infrastructure\weaviate\bootstrap-schema.ps1 `
  -BaseUrl "http://localhost:8080" `
  -SchemaPath "infrastructure\weaviate\schema.chunk.json"
```

Verify Weaviate:

```powershell
Invoke-RestMethod http://localhost:8080/v1/.well-known/ready
```

Expected response:

```text
READY
```

## 5) Start Frontend

Open a new terminal:

```powershell
cd frontend
npm install
npm run dev
```

Open:

```text
http://localhost:5173
```

Vite proxies `/api/...` requests to the local backend services, so keep the backend stack running while using the frontend.

## 6) Smoke Checks

Run these from PowerShell:

```powershell
Invoke-RestMethod http://localhost:8000/health
Invoke-RestMethod http://localhost:8001/health
Invoke-RestMethod http://localhost:8002/health
Invoke-RestMethod http://localhost:8003/health
Invoke-RestMethod http://localhost:8004/health
Invoke-RestMethod http://localhost:8005/health
Invoke-RestMethod http://localhost:8006/health
Invoke-RestMethod http://localhost:8007/health
Invoke-RestMethod http://localhost:8080/v1/.well-known/ready
```

If all checks return successfully, the local stack is up.

## 7) Create First Admin User

Create or sign up a user in the app, then promote that user in Supabase. Because
`supabase_users_table.sql` installs a role-sync trigger, you only need to set the
role on `public.users` — it is pushed into `auth.users` automatically. In the SQL
Editor, replace the email and run:

```sql
update public.users set role = 'admin' where email = 'admin@example.com';
```

Then log in again. Admin-only screens and admin APIs require a user whose role is
`admin`. (Promoting via the dashboard or the older `auth.users` metadata update
also works — the trigger keeps both tables in sync either way.)

## 8) Document Workflow

In the Admin page:

1. Upload one or more documents.
2. Validate the documents.
3. The system moves files from `pending/<user_id>/...` to `validated/<user_id>/...`.
4. Validated documents are indexed through preprocessing, embedding, and Weaviate.
5. Ask questions in the chat page after indexing finishes.

Deleting a document removes:

- the Supabase storage object
- the Supabase `documents` row
- related Weaviate chunks

## 9) Run Backend Locally Without Docker

Docker is the recommended path. For local uvicorn development, install Python dependencies first:

```powershell
pip install -r requirements.txt
```

Start Weaviate:

```powershell
docker compose up -d weaviate
```

Then run the launcher:

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\start-local-backend.ps1
```

Stop local uvicorn processes:

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\stop-local-backend.ps1
```

## Troubleshooting

- `Could not find table public.documents`: run `infrastructure/supabase/app_tables.sql`.
- `Could not find table public.login_attempts`: run `infrastructure/supabase/app_tables.sql`.
- `Could not find table public.security_alerts`: run `infrastructure/supabase/security_alerts.sql`.
- `Bucket not found`: create the `documents` and `profiles` buckets in Supabase Storage.
- Auth admin, invite, upload, or delete actions fail: confirm `AUTH_SUPABASE_KEY` is the service-role key, not the anon key.
- Frontend chat returns a proxy or 502 error: confirm `retrieval-service` and `generation-service` are running.
- Admin page cannot load agent/security data: confirm `admin-service` on port `8006` and `security-service` on port `8007` are running.
- Weaviate collection missing: run the bootstrap command in section 4.
- Embedding fails with OpenAI errors: confirm `OPENAI_KEY` is valid and has API access.

## Useful Commands

Show containers:

```powershell
docker ps --format "table {{.Names}}\t{{.Status}}\t{{.Ports}}"
```

Tail selected logs:

```powershell
docker logs auth-service --tail 120
docker logs ingestion-service --tail 120
docker logs embedding-service --tail 120
docker logs retrieval-service --tail 120
docker logs generation-service --tail 120
docker logs admin-service --tail 120
docker logs security-service --tail 120
```

Rebuild selected services:

```powershell
docker compose up -d --build auth-service
docker compose up -d --build ingestion-service embedding-service
docker compose up -d --build retrieval-service generation-service admin-service security-service
```

Run tests:

```powershell
pytest services\auth-service\tests -q
pytest services\ingestion-service\tests -q
pytest services\embedding-service\tests -q
pytest services\retrieval-service\tests -q
pytest services\generation-service\tests -q
pytest services\admin-service\tests -q
pytest services\security-service\tests -q
```
