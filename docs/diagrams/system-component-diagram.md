# System Component Diagram

```mermaid
flowchart LR
    user[User]
    frontend[React Frontend<br/>Vite]

    subgraph platform[Agentic RAG Platform]
        auth[auth-service<br/>:8001]
        preprocessing[preprocessing-service<br/>:8000]
        embedding[embedding-service<br/>:8002]
        retrieval[retrieval-service<br/>:8003]
        generation[generation-service<br/>:8004]
        ingestion[ingestion-service<br/>:8005]
        admin[admin-service<br/>:8006]
    end

    subgraph data[Data and External Systems]
        supabase[(Supabase)]
        weaviate[(Weaviate)]
        openai[OpenAI API]
        ollama[Ollama Fallback Model]
        storage[Shared Raw Data<br/>/shared/raw_data]
    end

    user --> frontend

    frontend --> auth
    frontend --> ingestion
    frontend --> generation
    frontend --> admin

    auth --> supabase
    ingestion --> supabase
    admin --> supabase

    ingestion --> preprocessing
    ingestion --> embedding
    preprocessing --> storage
    embedding --> storage
    embedding --> weaviate

    generation --> retrieval
    retrieval --> weaviate

    generation --> openai
    generation --> ollama
    embedding --> openai
    admin --> openai
```

Notes:

- `generation-service` performs retrieve-then-generate by calling `retrieval-service`.
- `embedding-service` depends on `preprocessing-service` and writes vectors to Weaviate.
- `admin-service` orchestrates operational tools across the backend services.
