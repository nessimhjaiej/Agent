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
  const rawText = await response.text();
  let payload = null;
  if (rawText) {
    try {
      payload = JSON.parse(rawText);
    } catch {
      payload = null;
    }
  }

  if (response.ok) {
    return payload ?? {};
  }

  let detail = `HTTP ${response.status}`;
  if (payload?.detail) {
    detail = typeof payload.detail === 'string' ? payload.detail : JSON.stringify(payload.detail);
  } else if (rawText) {
    detail = rawText;
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

async function postJsonWithAuth(url, body, accessToken) {
  const response = await fetch(url, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      Authorization: `Bearer ${accessToken}`,
    },
    body: JSON.stringify(body),
  });
  return parseResponse(response);
}

async function getJsonWithAuth(url, accessToken) {
  const response = await fetch(url, {
    method: 'GET',
    headers: {
      Authorization: `Bearer ${accessToken}`,
    },
  });
  return parseResponse(response);
}

async function deleteWithAuth(url, accessToken) {
  const response = await fetch(url, {
    method: 'DELETE',
    headers: {
      Authorization: `Bearer ${accessToken}`,
    },
  });
  return parseResponse(response);
}

export async function askGeneration({ query, chatHistory = [] }) {
  return postJson(`${API.generation}/ask`, {
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

export async function removeDocumentChunks(payload) {
  return postJson(`${API.ingestion}/ingestion/remove-document-chunks`, payload);
}

export async function listManagedUsers(accessToken) {
  return getJsonWithAuth(`${API.auth}/admin/users`, accessToken);
}

export async function inviteUser(accessToken, payload) {
  return postJsonWithAuth(`${API.auth}/admin/invite`, payload, accessToken);
}

export async function setUserValidation(accessToken, userId, validated) {
  return postJsonWithAuth(
    `${API.auth}/admin/users/${userId}/validate`,
    { validated },
    accessToken
  );
}

export async function setUserBlock(accessToken, userId, blocked) {
  return postJsonWithAuth(
    `${API.auth}/admin/users/${userId}/block`,
    { blocked },
    accessToken
  );
}

export async function deleteManagedUser(accessToken, userId) {
  return deleteWithAuth(`${API.auth}/admin/users/${userId}`, accessToken);
}

export default API;
