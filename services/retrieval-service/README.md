# retrieval-service

This service performs retrieval for RAG with three modes:

1. `bm25` keyword retrieval
2. `vector` semantic retrieval
3. `hybrid` retrieval (BM25 + vector) with pluggable fusion (`alpha` or `rrf`)

It also includes internal reranker modules (`none`, `cross_encoder`, `llm_batch`), with `llm_batch` active by default.

## Workflow

1. Client sends `POST /retrieval/search` with `query`, `mode`, limits, filters, fusion options, and rerank options.
2. Service builds a `QueryContext`.
3. `RetrievalOrchestrator` asks `HybridRetriever` for candidates according to mode:
   - `bm25`: BM25 branch only
   - `vector`: vector branch only
   - `hybrid`: both branches
4. `FusionFactory` selects `AlphaFusion` or `RRFFusion` and combines candidates.
5. `RankerFactory` selects the reranker (`llm_batch` by default).
6. Service returns ranked chunks and grouped document hits.

## Folder Overview

- `app/`: API and orchestration.
- `app/main.py`: FastAPI entrypoint.
- `app/config.py`: env-driven settings.
- `app/models.py`: domain models (`CandidateChunk`, `QueryContext`).
- `app/schemas.py`: request/response models.
- `app/orchestrator.py`: retrieve -> fuse -> rank flow.
- `app/service.py`: request mapping and response shaping.
- `app/routers/`: health and search endpoints.
- `retrievers/`: BM25, vector, and hybrid retrieval logic.
- `fusion/`: `alpha` and `rrf` implementations + factory.
- `rankers/`: ranker implementations + factory.
- `clients/`: Weaviate and OpenAI adapters.
- `tests/`: unit, contract, and integration tests.

## API Endpoints

- `GET /health`
- `POST /retrieval/search` — run a search and return ranked chunks + document hits.
- `GET /retrieval/config` — current fusion/rerank/top-k defaults.
- `PUT /retrieval/config` — update those defaults (persisted to `config.py`; this is
  what the admin agent tunes).
- `GET /retrieval/rerankers` — list available reranker methods.

## Request Example

```json
{
  "query": "digital payment regulation",
  "mode": "hybrid",
  "top_k_retrieve": 5,
  "top_k_return": 3,
  "filters": {
    "language": "en"
  },
  "fusion": {
    "type": "alpha",
    "alpha": 0.7,
    "rrf_k": 60
  },
  "rerank": {
    "enabled": false,
    "type": "none",
    "top_n": 20,
    "batch_size": 16
  }
}
```

## Environment Variables

- `RETRIEVAL_APP_NAME`
- `RETRIEVAL_APP_VERSION`
- `RETRIEVAL_DEFAULT_TOP_K_RETRIEVE` (default `4`)
- `RETRIEVAL_DEFAULT_TOP_K_RETURN` (default `3`)
- `RETRIEVAL_DEFAULT_FUSION` (`alpha` or `rrf`; default `alpha`)
- `RETRIEVAL_DEFAULT_ALPHA` (default `0.7`)
- `RETRIEVAL_DEFAULT_RRF_K` (default `60`)
- `RETRIEVAL_DEFAULT_RANKER` (`none`, `cross_encoder`, `llm_batch`; default `llm_batch`)
- `RETRIEVAL_DEFAULT_RERANK_TOP_N`
- `RETRIEVAL_ENFORCE_EMBEDDING_MODEL_MATCH` (default `true`)
- `WEAVIATE_HTTP_URL`
- `WEAVIATE_COLLECTION`
- `OPENAI_KEY`
- `EMBEDDING_MODEL`

## Test Strategy

- `test_api_contract.py`: payload contract and defaults.
- `test_bm25_retriever.py`: BM25 adapter mapping and request args.
- `test_vector_retriever.py`: query embedding + vector adapter mapping.
- `test_hybrid_retriever.py`: mode branching (`bm25`/`vector`/`hybrid`).
- `test_fusion.py`: alpha and rrf fusion behavior.
- `test_orchestrator.py`: stage ordering and factory selection.
- `test_integration_retrieval.py`: live API retrieval against Weaviate/OpenAI (guarded by skips).
