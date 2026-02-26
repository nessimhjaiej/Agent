# preprocessing-service

This service transforms source files into normalized, chunked, metadata-enriched records ready for embedding and indexing.

## Workflow

1. Input arrives as a file path (`.pdf`, `.txt`, `.md`, etc.).
2. `PreprocessingOrchestrator.process_source(...)` infers source type (or uses provided one).
3. `InputAdapterFactory` selects the right adapter.
4. Adapter loads content into a `RawDocument` (`document_id`, `source_uri`, `raw_text`, `checksum`).
5. `BasicTextNormalizer` cleans text and outputs `NormalizedDocument` with normalization version + checksum.
6. `ChunkerFactory` selects the chunking strategy (`overlap`, `semantic`, `late`; `sentence` is scaffolded).
7. Chunker splits normalized text into `ChunkRecord` objects with base metadata (offsets, token estimate, strategy).
8. `DefaultMetadataBuilder` enriches each chunk with traceability metadata (`source_filename`, `document_checksum`, `normalization_version`, `pipeline_version`).
9. Final output is a list of chunks ready for embedding/indexing.

## Folder Overview

- `app/`: API and orchestration layer.
- `app/main.py`: FastAPI entrypoint and router registration.
- `app/config.py`: environment-driven settings (strategy, chunk params, version).
- `app/schemas.py`: request/response API models.
- `app/service.py`: service layer connecting API payloads to orchestrator calls.
- `app/orchestrator.py`: end-to-end preprocessing pipeline coordination.
- `app/input_adapters/`: source ingestion adapters by format (`pdf`, `txt`, `md`).
- `chunking/`: chunking strategy interface + implementations (`overlap`, `semantic`, `late` implemented; `sentence` scaffolded).
- `normalization/`: normalization interface + implementations (`BasicTextNormalizer`).
- `metadata/`: metadata enrichment logic for chunk traceability.
- `tests/`: unit and API contract tests.

## API Endpoints

- `GET /health`: service status/version.
- `POST /preprocessing/process-source`: process one source file into chunks.

## Usage

1. Install dependencies:

```bash
pip install -r requirements.txt
```

2. Run the API:

```bash
uvicorn app.main:app --reload --app-dir services/preprocessing-service
```

3. Open interactive docs:

`http://127.0.0.1:8000/docs`

4. Example request body for `POST /preprocessing/process-source`:

```json
{
  "source_path": "c:/Users/NESSIM/Desktop/agentic/shared/raw_data/example.pdf",
  "source_type": "pdf",
  "chunk_strategy": "late",
  "chunk_size": 800,
  "chunk_overlap": 120,
  "late_size_multiplier": 2.0,
  "late_overlap_multiplier": 2.0
}
```

## Environment Variables

- `PREPROCESSING_APP_NAME`
- `PREPROCESSING_APP_VERSION`
- `PREPROCESSING_CHUNK_STRATEGY`
- `PREPROCESSING_CHUNK_SIZE`
- `PREPROCESSING_CHUNK_OVERLAP`
- `PREPROCESSING_PIPELINE_VERSION`
- `PREPROCESSING_RATE_LIMIT_REQUESTS`
- `PREPROCESSING_RATE_LIMIT_WINDOW_SECONDS`
- `PREPROCESSING_MAX_REQUEST_SIZE_BYTES`

## Design Patterns Used

- Strategy Pattern:
  - `BaseChunker` with `OverlapChunker`, `SemanticChunker`, `LateChunker`, `SentenceChunker`
  - `BaseInputAdapter` with concrete input adapters
  - `BaseNormalizer` with `BasicTextNormalizer`
  - `BaseMetadataBuilder` with `DefaultMetadataBuilder`
- Factory Pattern:
  - `ChunkerFactory`
  - `InputAdapterFactory`
- Orchestrator Pattern:
  - `PreprocessingOrchestrator` coordinates adapter -> normalizer -> chunker -> metadata builder
- Layered Architecture (separation of concerns):
  - API layer (`routers`, `schemas`)
  - Service layer (`service.py`)
  - Domain/pipeline layer (`models`, `chunking`, `normalization`, `metadata`)
- Middleware Pattern:
  - Rate limiting and request-size controls in FastAPI middleware

## UML DIGRAMS
