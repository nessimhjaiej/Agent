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

// The 401 detail strings the backends return for a dead session — a missing,
// malformed, empty, or expired/invalid token. These differ across services:
//   - auth-service & ingestion-service: "Missing or invalid Authorization header"
//   - all three on an expired/invalid token: "Invalid or expired token"
//   - admin-service (chat) with no token: "Missing admin access token"
// We treat any of them the same: try a silent refresh, then log out. NOTE: this
// excludes 403 "Admin access required" (a valid non-admin user) and 401
// "Invalid credentials" (a failed login) — those must NOT sign anyone out.
const DEAD_SESSION_ERRORS = [
  'Missing or invalid Authorization header',
  'Invalid or expired token',
  'Missing admin access token',
];

let unauthorizedHandler = null;
let tokenRefresher = null;

/**
 * Register a callback invoked when an authenticated request is rejected for a
 * dead session that could NOT be recovered by refreshing. AuthContext wires
 * this to sign the user out. Pass null to unregister.
 */
export function setUnauthorizedHandler(handler) {
  unauthorizedHandler = typeof handler === 'function' ? handler : null;
}

/**
 * Register an async callback that force-refreshes the Supabase session and
 * resolves to a fresh access token (or '' if it cannot). Used to silently
 * retry a request once before giving up and logging the user out.
 */
export function setTokenRefresher(refresher) {
  tokenRefresher = typeof refresher === 'function' ? refresher : null;
}

async function readResponse(response) {
  const rawText = await response.text();
  let payload = null;
  if (rawText) {
    try {
      payload = JSON.parse(rawText);
    } catch {
      payload = null;
    }
  }

  let detail = `HTTP ${response.status}`;
  if (payload?.detail) {
    detail = typeof payload.detail === 'string' ? payload.detail : JSON.stringify(payload.detail);
  } else if (rawText) {
    detail = rawText;
  }

  return { ok: response.ok, status: response.status, payload, detail };
}

// True for a 401 that means the session is dead (any of the messages above).
// Strictly 401-scoped so a 403 (e.g. non-admin) never counts.
function isDeadSessionError(result) {
  return result.status === 401
    && DEAD_SESSION_ERRORS.some((message) => result.detail.includes(message));
}

async function parseResponse(response) {
  const result = await readResponse(response);
  if (result.ok) {
    return result.payload ?? {};
  }
  if (isDeadSessionError(result) && unauthorizedHandler) {
    unauthorizedHandler(result.detail);
  }
  throw new Error(result.detail);
}

async function postJson(url, body) {
  const response = await fetch(url, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  });
  return parseResponse(response);
}

/**
 * Authenticated request with silent token recovery. If the call comes back with
 * a dead-session 401, we force-refresh the token once and retry. Only if the
 * retry still fails (or no fresh token could be obtained) do we trigger logout.
 */
async function fetchWithAuth(url, { method = 'GET', accessToken, jsonBody, formBody } = {}) {
  const doFetch = (token) => {
    const headers = { Authorization: `Bearer ${token}` };
    const init = { method, headers };
    if (formBody !== undefined) {
      init.body = formBody;
    } else if (jsonBody !== undefined) {
      headers['Content-Type'] = 'application/json';
      init.body = JSON.stringify(jsonBody);
    }
    return fetch(url, init);
  };

  let result = await readResponse(await doFetch(accessToken));

  if (isDeadSessionError(result) && tokenRefresher) {
    let refreshedToken = '';
    try {
      refreshedToken = await tokenRefresher();
    } catch {
      refreshedToken = '';
    }
    // Only retry if we actually got a different, usable token; a same/empty
    // token would just fail again and delay the logout.
    if (refreshedToken && refreshedToken !== accessToken) {
      result = await readResponse(await doFetch(refreshedToken));
    }
  }

  if (result.ok) {
    return result.payload ?? {};
  }
  if (isDeadSessionError(result) && unauthorizedHandler) {
    unauthorizedHandler(result.detail);
  }
  throw new Error(result.detail);
}

async function postJsonWithAuth(url, body, accessToken) {
  return fetchWithAuth(url, { method: 'POST', accessToken, jsonBody: body });
}

async function postFormWithAuth(url, formData, accessToken) {
  return fetchWithAuth(url, { method: 'POST', accessToken, formBody: formData });
}

async function getJsonWithAuth(url, accessToken) {
  return fetchWithAuth(url, { method: 'GET', accessToken });
}

async function deleteWithAuth(url, accessToken) {
  return fetchWithAuth(url, { method: 'DELETE', accessToken });
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
  const accessToken = typeof payload?.access_token === 'string' ? payload.access_token.trim() : '';

  // The admin token travels in both the header and the body, so a refreshed
  // retry has to rebuild both.
  const doFetch = (token) => fetch(`${API.admin}/admin/chat/stream`, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      ...(token ? { Authorization: `Bearer ${token}` } : {}),
    },
    body: JSON.stringify(token ? { ...payload, access_token: token } : payload),
  });

  let response = await doFetch(accessToken);

  // Dead-session 401: try a silent refresh + retry once before surfacing it
  // (parseResponse below will log out if it still fails).
  if (response.status === 401 && tokenRefresher) {
    const peek = await readResponse(response.clone());
    if (isDeadSessionError(peek)) {
      let refreshedToken = '';
      try {
        refreshedToken = await tokenRefresher();
      } catch {
        refreshedToken = '';
      }
      if (refreshedToken && refreshedToken !== accessToken) {
        response = await doFetch(refreshedToken);
      }
    }
  }

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
