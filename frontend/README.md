# Frontend (Synapse)

React + Vite single-page app for the Agentic RAG platform. Users chat with the
RAG assistant; admins manage documents, users, the admin agent, and security.

## Stack

- React 19 + React Router 7
- Vite (dev server + build)
- Tailwind CSS 4
- Framer Motion (animations)
- `@supabase/supabase-js` — used **only** for Storage (avatar upload) + Realtime
  (documents table). All authentication goes through `auth-service`.

## Setup

```powershell
Copy-Item .env.example .env   # then fill in the values below
npm install
npm run dev                   # http://localhost:5173
```

Requires the backend stack running (Vite proxies `/api/*` to the services — see
`vite.config.js`). Scripts: `npm run dev`, `npm run build`, `npm run preview`,
`npm run lint`.

## Environment variables (`frontend/.env`)

| Var | Purpose |
|-----|---------|
| `VITE_SUPABASE_URL` | Supabase project URL |
| `VITE_SUPABASE_ANON_KEY` | Supabase **anon/public** key (Storage + Realtime only) |
| `VITE_SUPABASE_DOCS_TABLE` | documents table name (default `documents`) — Realtime |
| `VITE_SUPABASE_PROFILE_BUCKET` | profile-picture bucket (default `profiles`) |

## How `/api/*` maps to services

The dev server proxies (and rewrites) each prefix to a backend port:

| Prefix | Service | Port |
|--------|---------|------|
| `/api/auth` | auth | 8001 |
| `/api/preprocessing` | preprocessing | 8000 |
| `/api/embedding` | embedding | 8002 |
| `/api/retrieval` | retrieval | 8003 |
| `/api/generation` | generation | 8004 |
| `/api/ingestion` | ingestion | 8005 |
| `/api/admin` | admin | 8006 |
| `/api/security` | security | 8007 |

## Structure

- `src/main.jsx` — mounts `BrowserRouter → ThemeProvider → AuthProvider → App`.
- `src/App.jsx` — routing + role guards. `/` chat (public), `/admin` and
  `/security` (admin only), `/login`, `*` not-found.
- `src/config/api.js` — the single API layer (all backend calls + auth functions +
  the admin chat stream). Handles silent token refresh; never auto-logs-out.
- `src/context/AuthContext.jsx` — owns the session (tokens in `localStorage`),
  refreshes via `auth-service`, hydrates the user from `/auth/me`, blocked-poll.
- `src/context/ThemeContext.jsx` — dark/light theme (OS-aware, persisted).
- `src/pages/` — `ChatPage` (RAG chat + citations + voice), `AdminPage`
  (documents / users / admin agent tabs), `SecurityPage` (alerts dashboard),
  `LoginPage`, `NotFoundPage`.
- `src/components/` — `Navbar`, `Layout`, modals (`AuthModal`, `ProfileModal`,
  `ChangePasswordModal`), `VoiceRecordButton` / `VoiceWaveform`, `SplashScreen`, …
- `src/hooks/useVoiceTranscription.js` — mic capture → `/generation/transcribe`.
- `src/utils/passwordPolicy.js` — password rules (mirrors the backend).

For a deep dive into flows and every component, see `docs/PROJECT_GUIDE.md`.
