# auth-service

This service provides secure authentication and authorization for the Agentic RAG platform using Supabase Auth as the backend authentication provider.

## Workflow

1. **Signup**: Client sends email/password to `POST /auth/signup`.
2. `AuthService.signup(...)` validates input using password validators.
3. Request is forwarded to Supabase Auth via `SupabaseClient`.
4. Supabase creates user account and sends confirmation email automatically.
5. Supabase returns session with JWT access token and refresh token.
6. Service maps Supabase user to `AuthUser` model and returns `AuthSession` with tokens.

7. **Login**: Client sends credentials to `POST /auth/login`.
8. `AuthService.login(...)` forwards to Supabase Auth for verification.
9. Supabase validates credentials and checks email confirmation status.
10. On success, Supabase returns valid session with tokens.
11. Service tracks login attempts for rate limiting and audit logging.

12. **Protected Routes**: Client includes JWT token in Authorization header.
13. `AuthService.verify_token(...)` validates token via Supabase.
14. Supabase verifies token signature and expiration.
15. Service retrieves user data and checks role permissions if needed.

## Folder Overview

- `app/`: API and core authentication logic.
- `app/main.py`: FastAPI entrypoint and router registration.
- `app/config.py`: environment-driven settings (Supabase credentials, rate limits).
- `app/schemas.py`: Pydantic request/response models for API endpoints.
- `app/models.py`: domain models (`AuthUser`, `AuthSession`).
- `app/service.py`: `AuthService` — core business logic wrapping Supabase Auth.
- `app/database.py`: `SupabaseClient` — Supabase auth client wrapper.
- `app/exceptions.py`: custom exception hierarchy for auth errors.
- `app/validators.py`: password and email validation logic.
- `app/utils.py`: utility functions (reserved for future use).
- `app/routers/`: API route handlers.
- `app/routers/health.py`: health check endpoint.
- `app/routers/auth.py`: authentication endpoints (signup, login, profile, etc.).
- `tests/`: unit and API contract tests.

## API Endpoints

- `GET /health`: service status and version.
- `POST /auth/signup`: register new user account.
- `POST /auth/login`: authenticate user and get tokens.
- `GET /auth/me`: get current user profile (requires auth token).
- `POST /auth/change-password`: change user password (requires auth token).
- `POST /auth/deactivate`: deactivate user account (requires auth token).
- `GET /admin/users/{user_id}`: get user by ID (admin role required).

## Usage

1. Install dependencies:

```bash
pip install -r requirements.txt
```

2. Run the API:

```bash
uvicorn app.main:app --reload --host 0.0.0.0 --port 8001
```

Or from project root:

```bash
uvicorn app.main:app --reload --app-dir services/auth-service --host 0.0.0.0 --port 8001
```

3. Open interactive docs:

`http://127.0.0.1:8001/docs`

4. Example request body for `POST /auth/signup`:

```json
{
  "email": "user@example.com",
  "password": "SecureP@ssw0rd!",
  "role": "user"
}
```

5. Example request body for `POST /auth/login`:

```json
{
  "email": "user@example.com",
  "password": "SecureP@ssw0rd!"
}
```

6. Example Authorization header for protected endpoints:

```
Authorization: Bearer eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...
```

## Environment Variables

- `AUTH_APP_NAME`: service name (default: `auth-service`)
- `AUTH_APP_VERSION`: service version (default: `0.1.0`)
- `AUTH_SUPABASE_URL`: **Required** — your Supabase project URL
- `AUTH_SUPABASE_KEY`: **Required** — your Supabase anon/public API key
- `AUTH_MAX_LOGIN_ATTEMPTS`: max login attempts before lockout (default: `5`)
- `AUTH_LOCKOUT_DURATION_MINUTES`: account lockout duration in minutes (default: `15`)

**Getting Supabase Credentials:**
1. Sign up at [Supabase](https://supabase.com)
2. Create a new project
3. Navigate to: Project Settings → API
4. Copy the project URL and anon/public key to your `.env` file

## Design Patterns Used

- **Service Layer Pattern**:
  - `AuthService` encapsulates business logic and Supabase Auth integration
  - Separates API layer from domain logic
  
- **Wrapper Pattern**:
  - `SupabaseClient` wraps Supabase SDK for easier testing and abstraction
  
- **Exception Hierarchy**:
  - Custom exceptions (`InvalidCredentialsException`, `UserNotFoundException`, etc.)
  - Centralized error handling and meaningful error messages
  
- **Validator Pattern**:
  - `PasswordValidator` and `EmailValidator` enforce security policies
  - Reusable validation logic separate from business logic
  
- **Layered Architecture** (separation of concerns):
  - API layer (`routers`, `schemas`)
  - Service layer (`service.py`)
  - Domain layer (`models`, `validators`, `exceptions`)
  - Infrastructure layer (`database.py`, `config.py`)

## Security Features

**Supabase Auth handles:**
- Password hashing & verification (bcrypt)
- JWT token creation, signing & validation
- Email verification (automatic confirmation emails on signup)
- Password reset flows via email
- Secure session management with refresh tokens
- Token expiration and rotation

**Application-level security:**
- Strong password policy validation (8+ chars, uppercase, lowercase, special characters)
- Rate limiting on login attempts (configurable)
- Account lockout on suspicious activity
- Role-based access control (user / admin roles)
- Audit logging for authentication events
- Input validation and sanitization
