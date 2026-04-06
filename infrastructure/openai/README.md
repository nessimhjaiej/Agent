# OpenAI Infrastructure

OpenAI is an external dependency used by the stack for:

- embeddings
- grounded generation
- admin planning and summarization
- audio transcription
- RAG evaluation support

Configuration is currently provided through the root `.env`, primarily:

- `OPENAI_KEY`
- generation model settings
- retrieval reranker model settings
- evaluation model settings

Files in this folder:

- `README.md` overview
- `USAGE.md` usage and cost script guide
- `models.md` repository model mapping
- `check-connectivity.ps1` simple API-key connectivity check
- `check-usage.ps1` terminal helper for organization usage and cost reporting

The usage script relies on the official organization usage and costs endpoints and is meant to reduce dashboard-only dependency for routine reporting checks.
