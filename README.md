# Agentic RAG Platform

Microservice-based Retrieval-Augmented Generation platform with:

- Supabase authentication and metadata
- preprocessing and chunking
- embedding and Weaviate indexing
- retrieval and grounded generation
- React frontend
- admin orchestration tools

## Repository Layout

- `frontend/` React + Vite client
- `services/` FastAPI microservices
- `docs/api_spec/` OpenAPI contracts
- `docs/diagrams/` architecture and workflow diagrams
- `docs/evaluation_reports/` generated evaluation artifacts
- `infrastructure/weaviate/` local Weaviate setup
- `scripts/` Windows PowerShell helper scripts

## Services

- `auth-service` on `http://localhost:8001`
- `preprocessing-service` on `http://localhost:8000`
- `embedding-service` on `http://localhost:8002`
- `retrieval-service` on `http://localhost:8003`
- `generation-service` on `http://localhost:8004`
- `ingestion-service` on `http://localhost:8005`
- `admin-service` on `http://localhost:8006`
- `weaviate` on `http://localhost:8080`
- frontend on `http://localhost:5173`

## Prerequisites

- Docker Desktop
- Node.js 20+
- npm
- Python 3.11+ if you want to run services outside Docker
- a Supabase project
- an OpenAI API key

## Environment Setup

1. Create the root env file:

```powershell
Copy-Item .env.example .env
```

2. Fill the required values in `.env`:

- `OPENAI_KEY`
- `AUTH_SUPABASE_URL`
- `AUTH_SUPABASE_KEY`
- `WEAVIATE_HTTP_URL`
- `WEAVIATE_COLLECTION`

3. Create the frontend env file:

```powershell
Copy-Item frontend\.env.example frontend\.env
```

4. Fill the frontend values:

- `VITE_SUPABASE_URL`
- `VITE_SUPABASE_ANON_KEY`
- `VITE_SUPABASE_DOCS_BUCKET`
- `VITE_SUPABASE_DOCS_TABLE`

## Supabase Setup

The repository currently includes one SQL setup script:

- `docs/supabase_users_table.sql`

This script creates `public.users` and keeps role metadata synchronized with `auth.users`.

Run it in the Supabase SQL editor before using auth and admin flows.

You also need a storage bucket for uploaded documents:

- bucket name: `documents`
- recommended visibility: private

If your local workflow uses document ingestion and document metadata in Supabase, make sure the corresponding table and storage policies exist in your Supabase project as well. The repository currently does not include a checked-in SQL file for a `public.documents` table.

## Run Locally

There are two supported ways to run the backend:

- Docker Compose for the full backend stack
- local `uvicorn` processes for each Python service, with Weaviate still running in Docker

### Option A: Run Backend With Docker Compose

From the project root:

```powershell
docker compose up -d --build
```

This starts:

- `weaviate`
- `auth-service`
- `preprocessing-service`
- `embedding-service`
- `retrieval-service`
- `generation-service`
- `ingestion-service`
- `admin-service`

Check container status:

```powershell
docker ps --format "table {{.Names}}\t{{.Status}}\t{{.Ports}}"
```

Stop the backend:

```powershell
docker compose down
```

### Option B: Run Backend Services Locally With Uvicorn

Weaviate still needs to run in Docker:

```powershell
docker compose up -d weaviate
```

You can then either use the helper script or run each service manually.

#### Start all local backend services with the helper script

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\start-local-backend.ps1
```

Stop them:

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\stop-local-backend.ps1
```

#### Start services manually

Open one terminal per service.

`auth-service`

```powershell
cd services\auth-service
python -m uvicorn app.main:app --host 0.0.0.0 --port 8001 --reload
```

`preprocessing-service`

```powershell
cd services\preprocessing-service
python -m uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
```

`embedding-service`

```powershell
cd services\embedding-service
python -m uvicorn app.main:app --host 0.0.0.0 --port 8002 --reload
```

`retrieval-service`

```powershell
cd services\retrieval-service
python -m uvicorn app.main:app --host 0.0.0.0 --port 8003 --reload
```

`generation-service`

```powershell
cd services\generation-service
python -m uvicorn app.main:app --host 0.0.0.0 --port 8004 --reload
```

`ingestion-service`

```powershell
cd services\ingestion-service
python -m uvicorn app.main:app --host 0.0.0.0 --port 8005 --reload
```

`admin-service`

```powershell
cd services\admin-service
python -m uvicorn app.main:app --host 0.0.0.0 --port 8006 --reload
```

## Bootstrap Weaviate

Run this once after starting Weaviate, or whenever you reset Weaviate data:

```powershell
powershell -ExecutionPolicy Bypass -File infrastructure\weaviate\bootstrap-schema.ps1 `
  -BaseUrl "http://localhost:8080" `
  -SchemaPath "infrastructure\weaviate\schema.chunk.json"
```

## Run the Frontend

In a new terminal:

```powershell
cd frontend
npm install
npm run dev
```

Open:

- `http://localhost:5173`

## Smoke Checks

Backend health endpoints:

```powershell
curl.exe http://localhost:8000/health
curl.exe http://localhost:8001/health
curl.exe http://localhost:8002/health
curl.exe http://localhost:8003/health
curl.exe http://localhost:8004/health
curl.exe http://localhost:8005/health
curl.exe http://localhost:8006/health
```

Weaviate readiness:

```powershell
curl.exe http://localhost:8080/v1/.well-known/ready
```

## Typical Local Startup Order

1. Clone the repository.
2. Create `.env` and `frontend/.env`.
3. Configure Supabase and storage.
4. Start the backend with Docker Compose or local `uvicorn`.
5. Bootstrap Weaviate schema.
6. Start the frontend.
7. Run the health checks.

## Useful Commands

Tail logs for selected containers:

```powershell
docker logs generation-service --tail 120
docker logs retrieval-service --tail 120
docker logs ingestion-service --tail 120
docker logs admin-service --tail 120
```

Rebuild selected services:

```powershell
docker compose up -d --build ingestion-service
docker compose up -d --build retrieval-service generation-service admin-service
```

Run selected tests:

```powershell
pytest services\generation-service\tests -q
pytest services\admin-service\tests -q
pytest services\ingestion-service\tests -q
```

## Notes

- `RUN_LOCAL.txt` contains Windows-specific helper notes, but this README should be the primary onboarding path.
- The backend services read configuration from the project root `.env`.
- `docs/api_spec/` contains the API contracts for the HTTP services.
