# Query and Generation Sequence Diagram

```mermaid
sequenceDiagram
    actor User
    participant Frontend
    participant Generation as generation-service
    participant Retrieval as retrieval-service
    participant Weaviate
    participant OpenAI as OpenAI Chat Model
    participant Ollama as Ollama Fallback

    User->>Frontend: Ask question
    Frontend->>Generation: POST /generation/ask
    Generation->>Retrieval: POST /retrieval/search
    Retrieval->>Weaviate: BM25 / vector / hybrid search
    Weaviate-->>Retrieval: Candidate chunks
    Retrieval-->>Generation: Ranked chunks + document hits

    Generation->>Generation: Build chat context + select top chunks
    Generation->>OpenAI: Generate grounded JSON answer with citations

    alt Primary model succeeds
        OpenAI-->>Generation: Answer + citation chunk_ids
    else Primary model fails or output is invalid
        Generation->>Ollama: Fallback generation attempt
        Ollama-->>Generation: Degraded answer
    end

    Generation->>Generation: Enforce citations and shape response
    Generation-->>Frontend: Answer + citations + model used
    Frontend-->>User: Render grounded response
```

Notes:

- `generation-service` exposes both `/generation/chat` and `/generation/ask`.
- `/generation/ask` is the end-to-end path that first calls `retrieval-service`.
- Retrieval supports fusion and optional reranking before generation.
