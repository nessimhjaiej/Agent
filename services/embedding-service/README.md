# embedding-service

This service receives preprocessed chunks, generates embeddings with OpenAI, and stores vectors + metadata in Weaviate.

## Workflow (Simple View)

1. Client calls `POST /embedding/index-chunks` with one or more chunks.
2. API validates payload shape with Pydantic schemas.
3. `EmbeddingService` maps API input models to internal domain models.
4. `EmbeddingOrchestrator` removes duplicate `chunk_id` values inside the same request.
5. `OpenAIEmbedder` generates vectors in batches using `text-embedding-3-small` (or configured model).
6. Orchestrator checks vector dimensions for consistency.
7. `WeaviateIndexer` upserts each chunk into Weaviate:
   - tries update first (`PUT /v1/objects/{id}`)
   - falls back to create (`POST /v1/objects`) when object is missing
8. API returns per-chunk indexing results.
9. Service logs ingestion metrics (requested, indexed, failed, duplicates, duration).

## Folder Overview

- `app/`: API and orchestration layer.
- `app/main.py`: FastAPI app creation and router registration.
- `app/config.py`: environment-driven typed settings + validation.
- `app/schemas.py`: request/response API models.
- `app/models.py`: internal domain models.
- `app/service.py`: maps API DTOs to domain and delegates to orchestrator.
- `app/orchestrator.py`: central pipeline coordination (dedupe -> embed -> index).
- `app/errors.py`: typed service/provider/store exceptions.
- `app/routers/health.py`: health endpoint.
- `app/routers/embedding.py`: indexing endpoint and HTTP error mapping.
- `embeddings/`: embedding provider adapters.
- `embeddings/base.py`: embedder interface.
- `embeddings/openai_embedder.py`: OpenAI embedding implementation with retry/backoff.
- `indexers/`: vector store adapters.
- `indexers/base.py`: indexer interface.
- `indexers/weaviate_indexer.py`: Weaviate upsert implementation with deterministic object IDs.
- `tests/`: contract, unit, and integration tests.

## API Endpoints

- `GET /health`: service status/version.
- `POST /embedding/index-chunks`: index a batch of already-built chunks into Weaviate.
- `POST /embedding/index-document`: full pipeline for one document — fetch the
  Supabase row, download the file, call `preprocessing-service` to chunk it, embed,
  upsert to Weaviate, and mark the row `embedded=true` (skips if already embedded).
- `POST /embedding/remove-document`: delete a document's vectors from Weaviate and
  clear its `embedded` flag.

## Request Contract (`POST /embedding/index-chunks`)

Each item in `chunks` follows your preprocessing output structure:

- `chunk_id`
- `document_id`
- `chunk_text`
- `metadata`:
  - `source_type`, `source_uri`, `language`
  - `chunk_index`, `start_char`, `end_char`, `char_count`, `token_count_estimate`
  - `chunking_strategy`, `source_filename`
  - `document_checksum`, `normalization_version`, `pipeline_version`, `created_at`

## Idempotency Logic

- Object IDs in Weaviate are deterministic UUIDs generated from:
  - `chunk_id`
  - `document_checksum`
  - `embedding_model`
  - `embedding_dimensions` (or `0` when not set)
- This ensures the same logical chunk version maps to the same vector object.
- Upsert behavior updates existing objects and creates new ones when missing.

## Environment Variables

- `OPENAI_KEY` (required)
- `EMBEDDING_APP_NAME`
- `EMBEDDING_APP_VERSION`
- `EMBEDDING_MODEL`
- `EMBEDDING_DIMENSIONS`
- `EMBEDDING_BATCH_SIZE`
- `EMBEDDING_TIMEOUT_SECONDS`
- `OPENAI_MAX_RETRIES`
- `OPENAI_RETRY_BASE_SECONDS`
- `WEAVIATE_HTTP_URL`
- `WEAVIATE_GRPC_HOST`
- `WEAVIATE_GRPC_PORT`
- `WEAVIATE_COLLECTION`
- `WEAVIATE_BATCH_SIZE`
- `WEAVIATE_STARTUP_TIMEOUT_SECONDS`
- `WEAVIATE_FAIL_IF_COLLECTION_MISSING`

## Running Locally

1. Start Weaviate:

```bash
docker compose -f infrastructure/weaviate/docker-compose.yml up -d
```

2. Bootstrap `Chunk` schema (if not created yet):

```powershell
powershell -ExecutionPolicy Bypass -File infrastructure/weaviate/bootstrap-schema.ps1 `
  -BaseUrl "http://localhost:8080" `
  -SchemaPath "infrastructure/weaviate/schema.chunk.json"
```

3. Run API:

```bash
uvicorn app.main:app --reload --app-dir services/embedding-service
```

4. Open docs:

`http://127.0.0.1:8000/docs`

## Test Strategy (Logic Behind Tests)

- `tests/test_api_contract.py`:
  - validates request contract behavior (422 on malformed payloads).
  - protects API boundary and schema assumptions.

- `tests/test_openai_embedder.py`:
  - validates batching behavior from `EMBEDDING_BATCH_SIZE`.
  - validates retry/backoff for rate limits.
  - validates fail-fast behavior after retry exhaustion.

- `tests/test_weaviate_indexer.py`:
  - validates idempotent upsert paths:
    - update existing object
    - create when update reports missing object
  - protects indexing behavior against Weaviate response variants.

- `tests/test_integration_indexing.py`:
  - real end-to-end path: API -> OpenAI -> Weaviate.
  - verifies inserted object exists with deterministic UUID.
  - auto-skips when `OPENAI_KEY` is missing or Weaviate is not ready.

## Design Patterns Used

- Strategy Pattern:
  - `BaseEmbedder` -> `OpenAIEmbedder`
  - `BaseVectorIndexer` -> `WeaviateIndexer`

- Orchestrator Pattern:
  - `EmbeddingOrchestrator` coordinates dedupe, embedding, dimension validation, and indexing.

- Layered Architecture:
  - API layer (`routers`, `schemas`)
  - Application/service layer (`service.py`, `orchestrator.py`)
  - Infrastructure adapters (`embeddings/`, `indexers/`)
  - Domain layer (`models.py`)

- Dependency Injection (lightweight):
  - Orchestrator accepts custom embedder/indexer implementations for testing and extensibility.

- Error Mapping Pattern:
  - Internal typed exceptions are translated to consistent HTTP responses in router layer.
