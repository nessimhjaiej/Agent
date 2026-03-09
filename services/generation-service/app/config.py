import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv


_PROJECT_ROOT = Path(__file__).resolve().parents[3]
load_dotenv(_PROJECT_ROOT / ".env", override=True)
load_dotenv(_PROJECT_ROOT / ".env.local", override=True)


def _parse_int(name: str, default: int) -> int:
    raw = os.getenv(name)
    if raw is None or raw.strip() == "":
        return default
    try:
        return int(raw)
    except ValueError as exc:
        raise ValueError(f"{name} must be an integer") from exc


def _parse_float(name: str, default: float) -> float:
    raw = os.getenv(name)
    if raw is None or raw.strip() == "":
        return default
    try:
        return float(raw)
    except ValueError as exc:
        raise ValueError(f"{name} must be a number") from exc


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
    app_name: str = "generation-service"
    app_version: str = "0.1.0"
    openai_key: str = ""
    generation_model: str = "gpt-4o"
    transcription_model: str = "gpt-4o-mini-transcribe"
    retrieval_base_url: str = "http://localhost:8003"
    retrieval_timeout_seconds: float = 20.0
    generation_http_max_retries: int = 2
    generation_retry_base_seconds: float = 0.5
    generation_block_prompt_attack_queries: bool = True
    generation_temperature: float = 0.0
    generation_timeout_seconds: float = 30.0
    generation_max_context_chunks: int = 8
    generation_max_history_turns: int = 6
    generation_max_chunk_chars: int = 1200
    generation_ollama_base_url: str = "http://localhost:11434"
    generation_fallback_enabled: bool = True
    generation_fallback_provider: str = "ollama"
    generation_fallback_model: str = "qwen2.5:7b"
    generation_require_citations: bool = True
    generation_strict_citation_validation: bool = True
    default_scope_fallback: str = "This is beyond my scope."

    @classmethod
    def from_env(cls) -> "Settings":
        return cls(
            app_name=os.getenv("GENERATION_APP_NAME", "generation-service"),
            app_version=os.getenv("GENERATION_APP_VERSION", "0.1.0"),
            openai_key=os.getenv("OPENAI_KEY", ""),
            generation_model=os.getenv("GENERATION_MODEL", "gpt-4o"),
            transcription_model=os.getenv(
                "TRANSCRIPTION_MODEL", "gpt-4o-mini-transcribe"
            ),
            retrieval_base_url=os.getenv("RETRIEVAL_BASE_URL", "http://localhost:8003"),
            retrieval_timeout_seconds=_parse_float("RETRIEVAL_TIMEOUT_SECONDS", 20.0),
            generation_http_max_retries=_parse_int("GENERATION_HTTP_MAX_RETRIES", 2),
            generation_retry_base_seconds=_parse_float("GENERATION_RETRY_BASE_SECONDS", 0.5),
            generation_block_prompt_attack_queries=_parse_bool(
                "GENERATION_BLOCK_PROMPT_ATTACK_QUERIES", True
            ),
            generation_temperature=_parse_float("GENERATION_TEMPERATURE", 0.0),
            generation_timeout_seconds=_parse_float("GENERATION_TIMEOUT_SECONDS", 30.0),
            generation_max_context_chunks=_parse_int("GENERATION_MAX_CONTEXT_CHUNKS", 8),
            generation_max_history_turns=_parse_int("GENERATION_MAX_HISTORY_TURNS", 6),
            generation_max_chunk_chars=_parse_int("GENERATION_MAX_CHUNK_CHARS", 1200),
            generation_ollama_base_url=os.getenv(
                "GENERATION_OLLAMA_BASE_URL", "http://localhost:11434"
            ),
            generation_fallback_enabled=_parse_bool("GENERATION_FALLBACK_ENABLED", True),
            generation_fallback_provider=os.getenv("GENERATION_FALLBACK_PROVIDER", "ollama"),
            generation_fallback_model=os.getenv("GENERATION_FALLBACK_MODEL", "qwen2.5:7b"),
            generation_require_citations=_parse_bool("GENERATION_REQUIRE_CITATIONS", True),
            generation_strict_citation_validation=_parse_bool(
                "GENERATION_STRICT_CITATION_VALIDATION", True
            ),
            default_scope_fallback=os.getenv(
                "GENERATION_SCOPE_FALLBACK_TEXT", "This is beyond my scope."
            ),
        )
