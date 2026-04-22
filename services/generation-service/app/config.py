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
    project_root: Path = _PROJECT_ROOT
    openai_key: str = ""
    generation_model: str = "gpt-4o"
    transcription_model: str = "gpt-4o-mini-transcribe"
    retrieval_base_url: str = "http://localhost:8003"
    security_base_url: str = ""
    retrieval_timeout_seconds: float = 20.0
    generation_http_max_retries: int = 2
    generation_retry_base_seconds: float = 0.5
    generation_block_prompt_attack_queries: bool = False
    generation_temperature: float = 0.0
    generation_timeout_seconds: float = 30.0
    generation_max_context_chunks: int = 8
    generation_max_history_turns: int = 6
    generation_max_history_chars: int = 4000
    generation_max_chunk_chars: int = 1200
    generation_ollama_base_url: str = "http://localhost:11434"
    generation_fallback_enabled: bool = True
    generation_fallback_provider: str = "ollama"
    generation_fallback_model: str = "qwen2.5:7b"
    generation_require_citations: bool = True
    generation_strict_citation_validation: bool = True
    default_scope_fallback: str = "This is beyond my scope."
    evaluation_reports_dir: str = str(_PROJECT_ROOT / "docs" / "evaluation_reports")

    @classmethod
    def from_env(cls) -> "Settings":
        defaults = cls()
        return cls(
            app_name=os.getenv("GENERATION_APP_NAME", defaults.app_name),
            app_version=os.getenv("GENERATION_APP_VERSION", defaults.app_version),
            project_root=_PROJECT_ROOT,
            openai_key=os.getenv("OPENAI_KEY", ""),
            generation_model=os.getenv("GENERATION_MODEL", defaults.generation_model),
            transcription_model=os.getenv(
                "TRANSCRIPTION_MODEL", defaults.transcription_model
            ),
            retrieval_base_url=os.getenv(
                "RETRIEVAL_BASE_URL", defaults.retrieval_base_url
            ),
            security_base_url=os.getenv("SECURITY_BASE_URL", defaults.security_base_url),
            retrieval_timeout_seconds=_parse_float(
                "RETRIEVAL_TIMEOUT_SECONDS", defaults.retrieval_timeout_seconds
            ),
            generation_http_max_retries=_parse_int(
                "GENERATION_HTTP_MAX_RETRIES", defaults.generation_http_max_retries
            ),
            generation_retry_base_seconds=_parse_float(
                "GENERATION_RETRY_BASE_SECONDS", defaults.generation_retry_base_seconds
            ),
            generation_block_prompt_attack_queries=_parse_bool(
                "GENERATION_BLOCK_PROMPT_ATTACK_QUERIES",
                defaults.generation_block_prompt_attack_queries,
            ),
            generation_temperature=_parse_float(
                "GENERATION_TEMPERATURE", defaults.generation_temperature
            ),
            generation_timeout_seconds=_parse_float(
                "GENERATION_TIMEOUT_SECONDS", defaults.generation_timeout_seconds
            ),
            generation_max_context_chunks=_parse_int(
                "GENERATION_MAX_CONTEXT_CHUNKS", defaults.generation_max_context_chunks
            ),
            generation_max_history_turns=_parse_int(
                "GENERATION_MAX_HISTORY_TURNS", defaults.generation_max_history_turns
            ),
            generation_max_history_chars=_parse_int(
                "GENERATION_MAX_HISTORY_CHARS", defaults.generation_max_history_chars
            ),
            generation_max_chunk_chars=_parse_int(
                "GENERATION_MAX_CHUNK_CHARS", defaults.generation_max_chunk_chars
            ),
            generation_ollama_base_url=os.getenv(
                "GENERATION_OLLAMA_BASE_URL", defaults.generation_ollama_base_url
            ),
            generation_fallback_enabled=_parse_bool(
                "GENERATION_FALLBACK_ENABLED", defaults.generation_fallback_enabled
            ),
            generation_fallback_provider=os.getenv(
                "GENERATION_FALLBACK_PROVIDER", defaults.generation_fallback_provider
            ),
            generation_fallback_model=os.getenv(
                "GENERATION_FALLBACK_MODEL", defaults.generation_fallback_model
            ),
            generation_require_citations=_parse_bool(
                "GENERATION_REQUIRE_CITATIONS", defaults.generation_require_citations
            ),
            generation_strict_citation_validation=_parse_bool(
                "GENERATION_STRICT_CITATION_VALIDATION",
                defaults.generation_strict_citation_validation,
            ),
            default_scope_fallback=os.getenv(
                "GENERATION_SCOPE_FALLBACK_TEXT", defaults.default_scope_fallback
            ),
            evaluation_reports_dir=os.getenv(
                "GENERATION_EVALUATION_REPORTS_DIR",
                defaults.evaluation_reports_dir,
            ),
        )
