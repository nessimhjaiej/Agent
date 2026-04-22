# security-service

Security monitoring and alert aggregation service for the Agentic platform.

## Responsibilities

- receive security events from backend services
- persist aggregated alerts in Supabase table `public.security_alerts`
- expose alert listing, summary, and resolution endpoints for the admin UI
- expose read-only login-attempt analytics from Supabase table `login_attempts`

## Current event sources

- `auth-service`
  - brute-force threshold reached
  - unauthorized access to admin auth endpoints
- `admin-service`
  - unauthorized access to admin chat and graph endpoints
- `preprocessing-service`
  - rate limit exceeded
  - request size limit exceeded
- `generation-service`
  - prompt injection detection when blocking is enabled

## Endpoints

- `GET /health`
- `GET /security/alerts`
- `GET /security/alerts/summary`
- `GET /security/login-attempts/summary`
- `POST /security/events`
- `POST /security/alerts/{alert_id}/resolve`

## Storage

### Persistent alerts

Alerts are stored in Supabase table `public.security_alerts`.

Expected columns:

- `id`
- `fingerprint`
- `event_type`
- `source_service`
- `severity`
- `status`
- `title`
- `message`
- `count`
- `metadata`
- `created_at`
- `last_seen_at`

The `fingerprint` is used to merge repeated active events into a single alert by incrementing `count` and updating `last_seen_at`.

### Login-attempt analytics

The service reads from Supabase table `login_attempts` in read-only mode to produce:

- total attempts in the configured time window
- failed vs successful attempts
- unique targeted emails
- recent failed attempts
- top targeted accounts

## Configuration

Loaded from `.env` / `.env.local`:

- `SECURITY_APP_NAME`
- `SECURITY_APP_VERSION`
- `SECURITY_RECENT_ALERT_LIMIT`
- `SECURITY_SUPABASE_URL`
- `SECURITY_SUPABASE_KEY`
- `SECURITY_LOGIN_ATTEMPTS_WINDOW_HOURS`
- `SECURITY_LOGIN_ATTEMPTS_MAX_ROWS`

Fallback behavior:

- if Supabase is configured, alerts are stored in `public.security_alerts`
- if Supabase is not configured, the service falls back to in-memory alerts so local development still works

## Local run

The service is started by:

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\start-local-backend.ps1
```

Default local port:

- `8007`

Health check:

```powershell
curl.exe http://localhost:8007/health
```

## Notes

- admin-only enforcement is implemented in `auth-service` and `admin-service`; this service stores the resulting alerts
- login-attempt analytics do not currently include reliable client IP data in local development
