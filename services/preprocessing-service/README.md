# preprocessing-service

1. Input arrives as a file path (`.pdf`, `.txt`, `.md`, etc.).
2. `PreprocessingOrchestrator.process_source(...)` infers source type (or uses provided one).
3. `InputAdapterFactory` selects the right adapter.
4. Adapter loads content into a `RawDocument` (`document_id`, `source_uri`, `raw_text`, `checksum`).
5. `BasicTextNormalizer` cleans text and outputs `NormalizedDocument` with normalization version + checksum.
6. `ChunkerFactory` selects the chunking strategy (`overlap` now, others scaffolded).
7. Chunker splits normalized text into `ChunkRecord` objects with base metadata (offsets, token estimate, strategy).
8. `DefaultMetadataBuilder` enriches each chunk with traceability metadata (`source_filename`, `document_checksum`, `normalization_version`, `pipeline_version`).
9. Final output is a list of chunks ready for embedding/indexing.

## FastAPI

- App entrypoint: `services/preprocessing-service/app/main.py`
- Health endpoint: `GET /health`
- Processing endpoint: `POST /preprocessing/process-source`

Example request body:

```json
{
  "source_path": "shared/raw_data/example.txt",
  "source_type": "txt",
  "chunk_strategy": "overlap",
  "chunk_size": 800,
  "chunk_overlap": 120
}
```
