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
  admin: '/api/admin',
  preprocessing: '/api/preprocessing',
  embedding: '/api/embedding',
  retrieval: '/api/retrieval',
  generation: '/api/generation',
  ingestion: '/api/ingestion',
  security: '/api/security',
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

async function postFormWithAuth(url, formData, accessToken) {
  const response = await fetch(url, {
    method: 'POST',
    headers: {
      Authorization: `Bearer ${accessToken}`,
    },
    body: formData,
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

async function getJson(url) {
  const response = await fetch(url, { method: 'GET' });
  return parseResponse(response);
}

async function postForm(url, formData) {
  const response = await fetch(url, {
    method: 'POST',
    body: formData,
  });
  return parseResponse(response);
}

async function deleteJson(url) {
  const response = await fetch(url, { method: 'DELETE' });
  return parseResponse(response);
}

export async function askGeneration({ query, chatHistory = [] }) {
  return postJson(`${API.generation}/ask`, {
    query,
    chat_history: chatHistory,
  });
}

export async function loginWithPassword(email, password) {
  return postJson(`${API.auth}/login`, {
    email,
    password,
  });
}

export async function streamAdmin(payload, onEvent) {
  const response = await fetch(`${API.admin}/admin/chat/stream`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
  });

  if (!response.ok || !response.body) {
    const detail = await parseResponse(response);
    return detail;
  }

  const reader = response.body.getReader();
  const decoder = new TextDecoder();
  let buffer = '';

  while (true) {
    const { done, value } = await reader.read();
    if (done) break;
    buffer += decoder.decode(value, { stream: true });
    const lines = buffer.split('\n');
    buffer = lines.pop() ?? '';

    for (const line of lines) {
      if (!line.trim()) continue;
      onEvent(JSON.parse(line));
    }
  }

  if (buffer.trim()) {
    onEvent(JSON.parse(buffer));
  }
}

export async function listDocuments(accessToken, userId) {
  const query = new URLSearchParams();
  if (userId) {
    query.set('user_id', userId);
  }
  const suffix = query.toString() ? `?${query.toString()}` : '';
  return getJsonWithAuth(`${API.ingestion}/ingestion/documents${suffix}`, accessToken);
}

export async function uploadDocument({ accessToken, userId, file }) {
  const formData = new FormData();
  formData.append('user_id', userId);
  formData.append('file', file);
  return postFormWithAuth(`${API.ingestion}/ingestion/documents/upload`, formData, accessToken);
}

export async function updateDocumentStatus(accessToken, documentId, payload) {
  return postJsonWithAuth(`${API.ingestion}/ingestion/documents/${documentId}/status`, payload, accessToken);
}

export async function getDocumentSignedUrl(accessToken, documentId, expiresIn = 3600) {
  return getJsonWithAuth(`${API.ingestion}/ingestion/documents/${documentId}/signed-url?expires_in=${expiresIn}`, accessToken);
}

export async function getDocumentSignedUrlByStoragePath(accessToken, storagePath, expiresIn = 3600) {
  const query = new URLSearchParams({ storage_path: storagePath, expires_in: String(expiresIn) });
  return getJsonWithAuth(`${API.ingestion}/ingestion/documents/signed-url/by-storage-path?${query.toString()}`, accessToken);
}

export async function deleteDocumentRecord(accessToken, documentId) {
  return deleteWithAuth(`${API.ingestion}/ingestion/documents/${documentId}`, accessToken);
}

export async function indexDocument(payload) {
  return postJson(`${API.embedding}/index-document`, payload);
}

export async function removeDocumentChunks(payload) {
  return postJson(`${API.embedding}/remove-document`, payload);
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

export async function listSecurityAlerts(includeResolved = false) {
  const query = includeResolved ? '?include_resolved=true' : '';
  return getJson(`${API.security}/alerts${query}`);
}

export async function getSecurityAlertsSummary() {
  return getJson(`${API.security}/alerts/summary`);
}

export async function getSecurityLoginAttemptsSummary() {
  return getJson(`${API.security}/login-attempts/summary`);
}

export async function resolveSecurityAlert(alertId) {
  return postJson(`${API.security}/alerts/${alertId}/resolve`, {});
}

export default API;
