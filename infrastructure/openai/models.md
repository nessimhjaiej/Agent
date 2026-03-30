# OpenAI Models In This Repository

This file documents the OpenAI-facing model configuration currently used by the project.

## Current Default Models

- Embeddings
  - env var: `EMBEDDING_MODEL`
  - default: `text-embedding-3-small`
  - used by: `embedding-service`

- Generation
  - env var: `GENERATION_MODEL`
  - default in code: `gpt-4o`
  - example/default in `.env.example`: `gpt-5`
  - used by: `generation-service`

- Audio transcription
  - env var: `TRANSCRIPTION_MODEL`
  - default: `gpt-4o-mini-transcribe`
  - used by: `generation-service`

- Retrieval LLM reranker
  - env var: `RETRIEVAL_LLM_RERANK_MODEL`
  - default: `gpt-4.1-mini`
  - used by: `retrieval-service`

- Admin planner
  - env var: `ADMIN_PLANNER_MODEL`
  - default: `gpt-5-mini`
  - used by: `admin-service`

- RAGAS evaluation model
  - env var: `RAGAS_EVAL_MODEL`
  - fallback behavior: if unset, uses `GENERATION_MODEL`, otherwise falls back in code to `gpt-4o-mini`
  - used by: `generation-service` evaluation runner

## Fallback Model Configuration

- Fallback enabled flag
  - env var: `GENERATION_FALLBACK_ENABLED`

- Fallback provider
  - env var: `GENERATION_FALLBACK_PROVIDER`
  - example default: `ollama`

- Fallback model
  - env var: `GENERATION_FALLBACK_MODEL`
  - example default: `qwen2.5:7b`

This fallback is not an OpenAI model, but it affects how the generation path behaves when OpenAI requests fail.

## Where These Models Are Defined

- root [`.env.example`](C:/Users/NESSIM/Desktop/agentic/.env.example)
- [`services/embedding-service/app/config.py`](C:/Users/NESSIM/Desktop/agentic/services/embedding-service/app/config.py)
- [`services/retrieval-service/app/config.py`](C:/Users/NESSIM/Desktop/agentic/services/retrieval-service/app/config.py)
- [`services/generation-service/app/config.py`](C:/Users/NESSIM/Desktop/agentic/services/generation-service/app/config.py)
- [`services/admin-service/app/config.py`](C:/Users/NESSIM/Desktop/agentic/services/admin-service/app/config.py)
- [`services/generation-service/app/evaluation/ragas_runner.py`](C:/Users/NESSIM/Desktop/agentic/services/generation-service/app/evaluation/ragas_runner.py)

## Important Note

There is currently a mismatch between `.env.example` and generation-service code:

- `.env.example` sets `GENERATION_MODEL=gpt-5`
- generation-service code defaults to `gpt-4o` when the env var is missing

That is not necessarily wrong, but it means the actual runtime model depends on whether your `.env` explicitly sets `GENERATION_MODEL`.

