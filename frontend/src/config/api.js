/**
 * Service Endpoints Configuration
 *
 * Active backend services in this stack:
 * - preprocessing-service: 8000
 * - auth-service: 8001
 * - embedding-service: 8002
 * - retrieval-service: 8003
 * - generation-service: 8004
 */

const API = {
  auth: '/api/auth',
  preprocessing: '/api/preprocessing',
  embedding: '/api/embedding',
  retrieval: '/api/retrieval',
  generation: '/api/generation',
};

export default API;
