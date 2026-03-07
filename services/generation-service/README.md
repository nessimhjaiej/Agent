# generation-service

## Step 1 Contract (Frozen)

Generation receives already retrieved and reranked chunks from retrieval-service.

### Input contract (chat request)

- `query`: user question/message for the current turn.
- `retrieved_chunks[]`: ranked evidence list from retrieval with:
  - `chunk_id`
  - `document_id`
  - `document_name`
  - `chunk_text`
  - `metadata`
  - optional scores (`bm25_score`, `vector_score`, `fusion_score`, `rerank_score`)
- `chat_history[]` (optional): list of prior `user`/`assistant` turns.
- `session_id` (optional): chat session correlation id.

### Output contract (chat response)

- `status`
- `session_id`
- `query`
- `answer`
- `citations[]` with full traceable source rows:
  - `chunk_id`
  - `document_id`
  - `document_name`
  - `chunk_text`
- `used_chunk_ids[]`
- `model`

## Step 2 Runtime Skeleton (Implemented)

- `GET /health`
- `POST /generation/chat`

Current `POST /generation/chat` behavior is a minimal orchestrated baseline:
- consumes the frozen contract;
- ranks chunks by score priority (`rerank_score`, `fusion_score`, `vector_score`, `bm25_score`);
- returns the top chunk as concise answer with traceable citation payload.

This is a placeholder baseline so Step 3 can replace answer construction with GPT-4o prompting while preserving contracts.

## Step 3 GPT-4o Integration (Implemented)

- Added OpenAI chat client with JSON-mode response handling.
- Added strict system prompt template in `prompt_templates/system_prompt.txt`.
- Orchestrator now:
  - ranks and trims chunk context;
  - builds prompt with query, recent chat history, and retrieved chunks;
  - calls GPT-4o and parses strict JSON output:
    `{"answer":"...","citations":[{"chunk_id":"..."}]}`
  - maps cited chunk ids to full citation payload;
  - falls back to `This is beyond my scope.` on provider or parse failure.

## Step 4 Citation Enforcement (Implemented)

- Added dedicated enforcement module:
  - `citation_enforcement/enforcer.py`
- Enforcement rules:
  - `GENERATION_REQUIRE_CITATIONS` (default `true`): response must cite at least one valid chunk.
  - `GENERATION_STRICT_CITATION_VALIDATION` (default `true`): unknown chunk ids trigger validation failure.
- Validation failures are treated as unsafe output and converted to scope fallback response.

## Step 5 Fallback Model Strategy (Implemented)

- Added model fallback plan in `fallback_model/plan.py`.
- Orchestrator tries models in order:
  1. `GENERATION_MODEL` (primary)
  2. `GENERATION_FALLBACK_MODEL` via `GENERATION_FALLBACK_PROVIDER` (if `GENERATION_FALLBACK_ENABLED=true`)
- If primary fails (provider error, invalid JSON, or citation validation failure), fallback model is attempted automatically.
- Scope fallback text is returned only when all enabled model attempts fail.

Default fallback provider is local Ollama with `qwen2.5:7b`.

## Step 7 Retrieval-Generation Orchestration (Implemented)

Added `POST /generation/ask` for one-shot flow:
1. Calls retrieval-service `/retrieval/search`
2. Feeds returned chunks to generation pipeline
3. Returns final answer + citations + retrieval summary metadata

## Ragas Evaluation Reports (Implemented)

Ragas evaluation is available directly inside generation-service.

- Runner module: `app/evaluation/ragas_runner.py`
- Sample dataset: `evals/sample_eval_dataset.json`
- Report output folder: `evaluation_reports/`

Run:

```bash
python -m app.evaluation.ragas_runner --dataset evals/sample_eval_dataset.json
```

Environment:
- set `OPENAI_API_KEY` (or `OPENAI_KEY`; runner maps it automatically for Ragas).

Each run:
- executes generation-service ask logic for each dataset row;
- computes Ragas metrics (`ContextRecall`, `Faithfulness`, `FactualCorrectness`);
- writes a timestamped JSON report like:
  `evaluation_reports/ragas_report_YYYYMMDD_HHMMSS.json`.
