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

## Recursive Plan-Mode Agent Rollout

The current Plan-mode reranker agent was built in 9 implementation steps:

1. Agent state contract
- Added structured recursive-agent models for goal, observations, decisions, pending confirmation, and run state.
- Extended admin chat responses so Plan-mode runs can return machine-readable agent state alongside natural-language answers.

2. Bounded recursive controller
- Added a recursive controller loop with a constrained action space: `respond`, `call_tool`, `request_confirmation`, `stop`.
- Added hard iteration and tool-call limits so the agent remains bounded and auditable.

3. Persistent run memory
- Added session-backed storage for recursive agent runs keyed by `session_id`.
- This allows Plan-mode follow-ups like "why?" and "apply it" to resume structured state instead of starting over.

4. Code-backed capability catalogs
- Added read-only catalog tools for reranking, chunking, embeddings, and evaluation capabilities.
- These catalogs ground the agent in real supported options rather than prompt-only descriptions.

5. First domain policy: reranking
- Added the first domain-specific recommendation policy for reranker selection.
- The policy inspects the reranker catalog, infers user preferences, stores a recommendation, and prepares executable steps.

6. Confirmation-aware recursive execution
- Wired the reranker policy into the real Plan-mode orchestrator.
- The agent now pauses before mutation, persists state, and resumes after confirmation to execute the approved change.

7. LLM-guided bounded decisions
- Wrapped the deterministic reranker policy in an LLM-guided decision layer.
- The model can choose the next bounded action, but invalid tool choices or unsafe decisions fall back to deterministic logic.

8. Frontend recursive-run UX
- Updated the admin chat UI so Plan mode shows agent-run state, proposed steps, and recursive activity instead of looking like a plain one-shot tool response.
- Plan mode now reads as an admin copilot workflow rather than an execution-only path.

9. Post-change evaluation loop
- Extended the reranker workflow so the agent can optionally run evaluation after a confirmed change.
- The agent now supports a bounded act-observe-summarize loop by comparing post-change evaluation results against the latest available baseline report.
