from pathlib import Path
import os
import sys

import httpx
import pytest
from dotenv import load_dotenv
from fastapi.testclient import TestClient

SERVICE_ROOT = Path(__file__).resolve().parents[1]
REPO_ROOT = Path(__file__).resolve().parents[3]
if str(SERVICE_ROOT) not in sys.path:
    sys.path.insert(0, str(SERVICE_ROOT))

load_dotenv(REPO_ROOT / ".env", override=True)

from app.config import Settings  # noqa: E402
from app.main import create_app  # noqa: E402


def _ollama_ready(base_url: str) -> bool:
    try:
        response = httpx.get(f"{base_url.rstrip('/')}/api/tags", timeout=5.0)
    except httpx.HTTPError:
        return False
    return response.status_code == 200


def _ollama_has_model(base_url: str, model_name: str) -> bool:
    try:
        response = httpx.get(f"{base_url.rstrip('/')}/api/tags", timeout=5.0)
    except httpx.HTTPError:
        return False
    if response.status_code != 200:
        return False
    models = response.json().get("models", [])
    names = {item.get("name") for item in models if isinstance(item, dict)}
    return model_name in names


@pytest.mark.integration
def test_generation_chat_uses_local_ollama_fallback_end_to_end() -> None:
    if os.getenv("GENERATION_RUN_OLLAMA_IT", "").strip().lower() not in {"1", "true", "yes"}:
        pytest.skip("Set GENERATION_RUN_OLLAMA_IT=true to run Ollama generation integration test")

    settings = Settings.from_env()
    if settings.generation_fallback_provider.strip().lower() != "ollama":
        pytest.skip("GENERATION_FALLBACK_PROVIDER must be 'ollama' for this integration test")
    if not _ollama_ready(settings.generation_ollama_base_url):
        pytest.skip("Ollama is not reachable at GENERATION_OLLAMA_BASE_URL")
    if not _ollama_has_model(settings.generation_ollama_base_url, settings.generation_fallback_model):
        pytest.skip("Configured Ollama fallback model is not installed locally")

    app = create_app(settings)
    client = TestClient(app)
    response = client.post(
        "/generation/chat",
        json={
            "query": "What is the obligation?",
            "retrieved_chunks": [
                {
                    "chunk_id": "doc-1:0",
                    "document_id": "doc-1",
                    "document_name": "doc-1.pdf",
                    "chunk_text": "The institution must apply strong customer authentication.",
                    "metadata": {"source_filename": "doc-1.pdf"},
                    "rerank_score": 0.9,
                }
            ],
        },
    )

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["status"] == "ok"
    assert isinstance(body["answer"], str)
    assert body["model"] in {settings.generation_model, settings.generation_fallback_model}
