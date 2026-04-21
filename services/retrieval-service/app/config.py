import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv


_PROJECT_ROOT = Path(__file__).resolve().parents[3]
load_dotenv(_PROJECT_ROOT / ".env", override=True)
load_dotenv(_PROJECT_ROOT / ".env.local", override=True)


def _parse_bool(name: str, default: bool) -> bool:
    raw = os.getenv(name)
    if raw is None or raw.strip() == "":
        return default
    value = raw.strip().lower()
    if value in {"1", "true", "yes", "on"}:
        return True
    if value in {"0", "false", "no", "off"}:
        return False
    raise ValueError(f"{name} must be a boolean (true/false)")


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
    default_ranker_type: str = "llm_batch"
    default_rerank_top_n: int = 20
    enforce_embedding_model_match: bool = True

    @classmethod
    def from_env(cls) -> "Settings":
        defaults = cls()
        return cls(
            app_name=os.getenv("RETRIEVAL_APP_NAME", defaults.app_name),
            app_version=os.getenv("RETRIEVAL_APP_VERSION", defaults.app_version),
            weaviate_http_url=os.getenv("WEAVIATE_HTTP_URL", defaults.weaviate_http_url),
            weaviate_collection=os.getenv("WEAVIATE_COLLECTION", defaults.weaviate_collection),
            openai_key=os.getenv("OPENAI_KEY", ""),
            embedding_model=os.getenv("EMBEDDING_MODEL", defaults.embedding_model),
            default_top_k_retrieve=defaults.default_top_k_retrieve,
            default_top_k_return=defaults.default_top_k_return,
            default_fusion_type=os.getenv("RETRIEVAL_DEFAULT_FUSION", defaults.default_fusion_type),
            default_alpha=float(os.getenv("RETRIEVAL_DEFAULT_ALPHA", str(defaults.default_alpha))),
            default_rrf_k=int(os.getenv("RETRIEVAL_DEFAULT_RRF_K", str(defaults.default_rrf_k))),
            default_ranker_type=defaults.default_ranker_type,
            default_rerank_top_n=int(os.getenv("RETRIEVAL_DEFAULT_RERANK_TOP_N", str(defaults.default_rerank_top_n))),
            enforce_embedding_model_match=_parse_bool(
                "RETRIEVAL_ENFORCE_EMBEDDING_MODEL_MATCH", defaults.enforce_embedding_model_match
            ),
        )
