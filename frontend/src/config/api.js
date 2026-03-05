/**
 * Service Endpoints Configuration
 *
 * Active backend services in this stack:
 * - preprocessing-service: 8000
 * - auth-service: 8001
 * - embedding-service: 8002
 * - retrieval-service: 8003
 * - generation-service: 8004
 * - ingestion-service: 8005
 */

const API = {
  auth: '/api/auth',
  preprocessing: '/api/preprocessing',
  embedding: '/api/embedding',
  retrieval: '/api/retrieval',
  generation: '/api/generation',
  ingestion: '/api/ingestion',
};

async function parseResponse(response) {
  if (response.ok) {
    return response.json();
  }

  let detail = `HTTP ${response.status}`;
  try {
    const payload = await response.json();
    if (payload?.detail) {
      detail = typeof payload.detail === 'string' ? payload.detail : JSON.stringify(payload.detail);
    }
  } catch {
    const text = await response.text();
    if (text) {
      detail = text;
    }
  }
  throw new Error(detail);
}

async function postJson(url, body) {
  const response = await fetch(url, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  });
  return parseResponse(response);
}

export async function askGeneration({ query, chatHistory = [] }) {
  return postJson(`${API.generation}/generation/ask`, {
    query,
    chat_history: chatHistory,
  });
}

export async function runIngestion(payload = {}) {
  return postJson(`${API.ingestion}/ingestion/run`, payload);
}

export async function indexDocument(payload) {
  return postJson(`${API.ingestion}/ingestion/index-document`, payload);
}

export default API;
