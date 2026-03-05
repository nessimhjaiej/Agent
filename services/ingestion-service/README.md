# ingestion-service

FastAPI service that orchestrates:

1. `preprocessing-service` (`POST /preprocessing/process-source`)
2. `embedding-service` (`POST /embedding/index-chunks`)

## API

- `GET /health`
- `POST /ingestion/run`
- `POST /ingestion/index-document`

Example request:

```json
{
  "raw_dir": "shared/raw_data",
  "source_root_in_preprocessing": "/shared/raw_data",
  "embedding_batch_size": 100,
  "recursive": true,
  "patterns": ["*.pdf"],
  "dry_run": false
}
```

## Run service

```powershell
uvicorn app.main:app --reload --app-dir services/ingestion-service --port 8005
```

## Run CLI workflow

```powershell
python services/ingestion-service/workflow/run_ingestion.py --recursive
```

## Environment variables

- `INGESTION_APP_NAME`
- `INGESTION_APP_VERSION`
- `INGESTION_RAW_DIR`
- `INGESTION_SOURCE_ROOT_IN_PREPROCESSING`
- `INGESTION_PREPROCESSING_BASE_URL`
- `INGESTION_EMBEDDING_BASE_URL`
- `INGESTION_EMBEDDING_BATCH_SIZE`
- `INGESTION_RECURSIVE`
- `INGESTION_HTTP_TIMEOUT_SECONDS`
- `INGESTION_FILE_PATTERNS` (comma-separated)
- `INGESTION_SUPABASE_SYNC_SUBDIR`
- `WEAVIATE_HTTP_URL`
- `WEAVIATE_COLLECTION`
