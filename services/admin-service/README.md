# admin-service

Conversational orchestration service for administrator operations across the RAG stack.

Current scaffold:
- `POST /admin/chat`
- `GET /health`
- hybrid admin intent routing and multi-step execution for:
  - `get_pipeline_status`
  - `get_embedding_config`
  - `update_embedding_model`
  - `get_chunking_config`
  - `update_chunking_config`
  - `get_reranker_config`
  - `update_reranker_config`
  - `embed_document`
  - `embed_validated_documents`
  - `delete_validated_documents`
  - `reindex_corpus`
  - `delete_document`
  - `run_rag_evaluation`
  - `get_evaluation_report`
  - `restart_services`

This service is intentionally thin:
- it decides and orchestrates
- existing backend services execute domain operations
- security/audit events are emitted outward rather than stored locally

Current behavior notes:
- tool execution now supports confirmed multi-step plans
- corpus reindex performs a clean delete of validated indexed chunks before re-embedding
- local backend services can be restarted through repo-level PowerShell orchestration
