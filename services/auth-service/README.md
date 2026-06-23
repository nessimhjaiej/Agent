# auth-service

Authentication, session management, and admin user-management for the platform,
built on top of **Supabase Auth (GoTrue)**. The browser talks only to this
service for auth — it never calls Supabase Auth directly.

> **Key requirement:** `AUTH_SUPABASE_KEY` must be the Supabase **service-role**
> key. The service performs admin user actions and writes RLS-protected tables
> (`login_attempts`, `audit_logs`). An anon/public key makes login and user
> management fail.

## How it works

- **Signup** (`POST /auth/signup`): creates the account via the Supabase **admin**
  API (`admin.create_user`, `email_confirm=true`) — no confirmation email is sent.
  The new user gets `role=user` and `account_validated=false`, so they **cannot log
  in until an admin validates them**. Signup returns no session.
- **Login** (`POST /auth/login`): enforces a lockout (max attempts within a window),
  records every attempt in `login_attempts`, emits a `BRUTE_FORCE_ATTEMPTS` alert at
  the threshold, and rejects blocked / invite-pending / unvalidated accounts. On
  success it returns a Supabase session (access + refresh token).
- **Refresh** (`POST /auth/refresh`): exchanges a refresh token for a new session.
  The browser uses this to renew tokens (server-owned refresh).
- **Profile** (`GET /auth/me`, `POST /auth/update-profile`): returns / updates the
  caller's own profile (username, phone, avatar URL, onboarding flag, password).
- **Password reset** (`POST /auth/password-reset`): self-service, but only for an
  existing, non-blocked, **non-admin** account (admins must be re-invited). Sends a
  branded reset email; returns `{ success, message }`.
- **Admin** endpoints: list users, invite (always grants admin), validate, block
  (also force-kicks active sessions), and delete users. All are audit-logged and
  emit security events.

## API endpoints

| Method & path | Auth | Purpose |
|---------------|------|---------|
| `GET /health` | — | service status / version |
| `POST /auth/signup` | — | register (pending admin validation) |
| `POST /auth/login` | — | authenticate, return session |
| `POST /auth/refresh` | refresh token | renew session |
| `POST /auth/password-reset` | — | email a reset link (gated) |
| `POST /auth/update-password` | bearer | change own password |
| `GET /auth/me` | bearer | full self-profile |
| `POST /auth/update-profile` | bearer | update own metadata / password |
| `POST /auth/logout` | bearer | sign out |
| `GET /auth/admin/users` | admin | list users |
| `POST /auth/admin/invite` | admin | invite an admin |
| `POST /auth/admin/users/{id}/validate` | admin | approve / un-approve |
| `POST /auth/admin/users/{id}/block` | admin | block / unblock |
| `DELETE /auth/admin/users/{id}` | admin | delete a user |

## Folder overview

- `app/main.py` — FastAPI entrypoint and router registration.
- `app/routers/auth.py` — all `/auth/*` endpoints; maps service exceptions to HTTP
  codes (e.g. `AccountLocked`→429, `InvalidCredentials`→401, `Unauthorized`→403).
- `app/routers/health.py` — health check.
- `app/service.py` — `AuthService`: the core business logic over Supabase Auth.
- `app/database.py` — `SupabaseClient`: Supabase client + `log_audit`,
  `record_login_attempt`, `get_failed_login_count`.
- `app/schemas.py` — Pydantic request/response models (the API contract).
- `app/models.py` — domain models (`AuthUser`, `AuthSession`).
- `app/validators.py` — `PasswordValidator`, `EmailValidator`.
- `app/exceptions.py` — exception hierarchy under `AuthServiceException`.
- `app/security_events.py` — emits events to `security-service`.
- `app/assets/logo.png` — logo embedded in the branded HTML emails.
- `tests/` — unit + API-contract tests.

## Run

```powershell
uvicorn app.main:app --reload --app-dir services/auth-service --port 8001
```

Interactive docs: `http://127.0.0.1:8001/docs`

## Environment variables

| Var | Required | Default | Purpose |
|-----|----------|---------|---------|
| `AUTH_SUPABASE_URL` | ✅ | — | Supabase project URL |
| `AUTH_SUPABASE_KEY` | ✅ | — | Supabase **service-role** key |
| `AUTH_MAX_LOGIN_ATTEMPTS` | | `5` | failed logins before lockout |
| `AUTH_LOCKOUT_DURATION_MINUTES` | | `15` | lockout window |
| `FRONTEND_URL` | | — | base URL used in email links |
| `SECURITY_BASE_URL` | | `http://security-service:8007` | where to emit security events |
| `AUTH_SMTP_HOST` / `AUTH_SMTP_PORT` / `AUTH_SMTP_USERNAME` / `AUTH_SMTP_PASSWORD` / `AUTH_SMTP_FROM_EMAIL` / `AUTH_SMTP_FROM_NAME` / `AUTH_SMTP_USE_TLS` | | — | SMTP for branded invite / reset emails (falls back to Supabase's built-in email if unset) |

See `app/config.py` for the full list and exact defaults.

## Security features

- Strong password policy (8+ chars, upper, lower, digit, special).
- Login lockout + brute-force detection → security alerts.
- Account validation gate (new users wait for admin approval).
- Blocking with global session kick + ban.
- Role-based access (`user` / `admin`); admin endpoints require an admin token.
- Gated self-service password reset (existing, non-blocked, non-admin only).
- Audit logging of auth events; security events forwarded to `security-service`.
