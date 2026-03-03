/**
 * ─── Service Endpoints Configuration ───
 * 
 * Central registry for all backend microservice endpoints.
 * In development, Vite proxy handles routing (see vite.config.js).
 * In production, update BASE_URL to point to your API gateway.
 * 
 * Service Ports (for reference):
 * ┌─────────────────────────┬──────┐
 * │ Service                 │ Port │
 * ├─────────────────────────┼──────┤
 * │ preprocessing-service   │ 8000 │
 * │ auth-service            │ 8001 │
 * │ embedding-service       │ 8002 │
 * │ retrieval-service       │ 8003 │
 * │ generation-service      │ 8004 │
 * │ reranking-service       │ 8005 │
 * │ security-service        │ 8006 │
 * │ ingestion-service       │ 8007 │
 * │ feedback-service        │ 8008 │
 * └─────────────────────────┴──────┘
 * 
 * Infrastructure:
 * │ Weaviate (HTTP)         │ 8080 │
 * │ Weaviate (gRPC)         │ 50051│
 */

const API = {
  auth: '/api/auth',
  preprocessing: '/api/preprocessing',
  embedding: '/api/embedding',
  retrieval: '/api/retrieval',
  generation: '/api/generation',
  reranking: '/api/reranking',
  security: '/api/security',
  ingestion: '/api/ingestion',
  feedback: '/api/feedback',
};

export default API;
