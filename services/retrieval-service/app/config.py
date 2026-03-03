import os
from dataclasses import dataclass


@dataclass(slots=True)
class Settings:
    app_name: str = "retrieval-service"
    app_version: str = "0.1.0"
    weaviate_http_url: str = "http://localhost:8080"
    weaviate_collection: str = "Chunk"
    openai_key: str = ""
    embedding_model: str = "text-embedding-3-small"
    default_top_k_retrieve: int = 5
    default_top_k_return: int = 3
    default_fusion_type: str = "alpha"
    default_alpha: float = 0.7
    default_rrf_k: int = 60
    default_ranker_type: str = "none"
    default_rerank_top_n: int = 20

    @classmethod
    def from_env(cls) -> "Settings":
        return cls(
            app_name=os.getenv("RETRIEVAL_APP_NAME", "retrieval-service"),
            app_version=os.getenv("RETRIEVAL_APP_VERSION", "0.1.0"),
            weaviate_http_url=os.getenv("WEAVIATE_HTTP_URL", "http://localhost:8080"),
            weaviate_collection=os.getenv("WEAVIATE_COLLECTION", "Chunk"),
            openai_key=os.getenv("OPENAI_KEY", ""),
            embedding_model=os.getenv("EMBEDDING_MODEL", "text-embedding-3-small"),
            default_top_k_retrieve=int(
                os.getenv(
                    "RETRIEVAL_DEFAULT_TOP_K_RETRIEVE",
                    os.getenv("RETRIEVAL_DEFAULT_TOP_K", "5"),
                )
            ),
            default_top_k_return=int(
                os.getenv("RETRIEVAL_DEFAULT_TOP_K_RETURN", "3")
            ),
            default_fusion_type=os.getenv("RETRIEVAL_DEFAULT_FUSION", "alpha"),
            default_alpha=float(os.getenv("RETRIEVAL_DEFAULT_ALPHA", "0.7")),
            default_rrf_k=int(os.getenv("RETRIEVAL_DEFAULT_RRF_K", "60")),
            default_ranker_type=os.getenv("RETRIEVAL_DEFAULT_RANKER", "none"),
            default_rerank_top_n=int(os.getenv("RETRIEVAL_DEFAULT_RERANK_TOP_N", "20")),
        )
