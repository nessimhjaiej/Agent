# generation-service

Produces the final, **grounded answer** for the RAG pipeline. Given a query and a
set of retrieved chunks, it prompts an LLM for a strict-JSON answer, **enforces
citations** against the real chunks, and falls back safely when anything fails.
It also hosts **voice transcription** and a **RAGAS evaluation** subsystem.

## What it does

- **`/generation/chat`** — answer from chunks you already have.
- **`/generation/ask`** — one-shot: call `retrieval-service`, then generate. This is
  what the user chat uses.
- Guardrail: a prompt-injection detector blocks malicious queries (and raises a
  `PROMPT_INJECTION_DETECTED` security event) before any LLM call.
- Identity / capability questions ("who are you?") are answered directly as
  **"Synapse"** without hitting the LLM.

### Generation flow (`GenerationOrchestrator.generate`)

1. Rank chunks by best score (`rerank → fusion → vector → bm25`); keep the top N.
2. Build the prompt: language rule + query + a trimmed chat-history window + the
   chunks as authoritative evidence; ask for JSON only
   `{"answer": "...", "citations": [{"chunk_id": "..."}]}`.
3. Try each model in the fallback plan (primary, then fallback provider/model):
   parse the JSON, then run the **CitationEnforcer** so only citations that map to
   real retrieved chunks survive. If citation validation fails, attach the top
   chunk rather than returning an uncited answer.
4. If every attempt fails, return the scope fallback ("This is beyond my scope.").

## API endpoints

| Method & path | Purpose |
|---------------|---------|
| `GET /health` | service status / version |
| `POST /generation/chat` | generate from supplied chunks |
| `POST /generation/ask` | retrieve + generate (returns answer, citations, retrieval stats) |
| `POST /generation/transcribe` | transcribe an uploaded audio file (Whisper) |
| `POST /generation/evaluation/run` | run a RAGAS evaluation over a dataset |
| `GET /generation/evaluations` | list evaluation reports |
| `GET /generation/evaluations/{id}` | read one report |
| `POST /generation/evaluations/compare` | compare two reports |

### Chat response shape

```json
{
  "status": "ok",
  "session_id": "...",
  "query": "...",
  "answer": "...",
  "citations": [
    { "chunk_id": "...", "document_id": "...", "document_name": "...", "chunk_text": "...", "storage_path": "..." }
  ],
  "used_chunk_ids": ["..."],
  "model": "..."
}
```

## Folder overview

- `app/orchestrator.py` — `GenerationOrchestrator`: prompt building, model fallback,
  JSON parsing, citation enforcement.
- `app/service.py` — `GenerationService`: chat/ask/transcribe, guardrail + special
  answers, contextual follow-up query expansion.
- `app/clients/` — `OpenAIChatClient`, `OllamaChatClient`, `OpenAIAudioClient`,
  `RetrievalClient`.
- `app/guardrails.py` — `is_prompt_attack_query` (multilingual prompt-injection rules).
- `citation_enforcement/enforcer.py` — `CitationEnforcer`.
- `fallback_model/plan.py` — `ModelFallbackPlan`.
- `app/evaluation/` — `RagasEvaluationRunner` + `report_store.py`.
- `prompt_templates/system_prompt.txt` — the system prompt.
- `evals/sample_eval_dataset.json` — sample evaluation dataset.

## Run

```powershell
uvicorn app.main:app --reload --app-dir services/generation-service --port 8004
```

Interactive docs: `http://127.0.0.1:8004/docs`

## Evaluation (CLI)

```bash
python -m app.evaluation.ragas_runner --dataset evals/sample_eval_dataset.json
```

Each run executes the ask pipeline per dataset row, computes RAGAS metrics (e.g.
context recall, faithfulness, factual correctness), and writes a timestamped report
to `evaluation_reports/ragas_report_YYYYMMDD_HHMMSS.json`.

## Environment variables

| Var | Purpose |
|-----|---------|
| `OPENAI_KEY` | OpenAI key (generation, reranking input, transcription) |
| `RETRIEVAL_BASE_URL` | retrieval-service base URL (used by `/ask`) |
| `SECURITY_BASE_URL` | security-service base URL (guardrail events) |
| `GENERATION_MODEL` | primary chat model |
| `GENERATION_FALLBACK_ENABLED` / `GENERATION_FALLBACK_PROVIDER` / `GENERATION_FALLBACK_MODEL` | fallback model chain (e.g. Ollama) |
| `GENERATION_REQUIRE_CITATIONS` / `GENERATION_STRICT_CITATION_VALIDATION` | citation enforcement (default `true`) |
| `GENERATION_MAX_HISTORY_TURNS` / `GENERATION_MAX_HISTORY_CHARS` | chat-history window |
| `GENERATION_BLOCK_PROMPT_ATTACK_QUERIES` | enable the prompt-injection guardrail |
| `TRANSCRIPTION_MODEL` | Whisper model (default `gpt-4o-mini-transcribe`) |

See `app/config.py` for the full list and defaults.

## Design patterns

- **Strategy** — swappable LLM clients behind a `ChatClient` protocol; fallback plan.
- **Orchestrator** — `GenerationOrchestrator` coordinates rank → prompt → call →
  enforce.
- **Layered architecture** — router → service → orchestrator → clients.
- **Guardrail / policy** — input filtering + citation enforcement as explicit gates.
