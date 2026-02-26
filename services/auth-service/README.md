# auth-service

Authentication microservice for the Agentic RAG platform.

## Structure

```
app/
├── __init__.py
├── config.py          # Settings dataclass with from_env()
├── main.py            # FastAPI app factory (create_app)
├── models.py          # Domain models (User, UserWithHash, TokenPayload)
├── schemas.py         # Pydantic request/response schemas
├── exceptions.py      # Custom exception hierarchy
├── validators.py      # Password & email validation
├── database.py        # Supabase client wrapper
├── utils.py           # Password hashing (bcrypt) & JWT helpers
├── service.py         # AuthService — core business logic
└── routers/
    ├── __init__.py
    ├── health.py      # GET /health
    └── auth.py        # POST /auth/signup, /auth/login, etc.
tests/
├── test_validators.py
└── test_api_contract.py
```

## FastAPI

- App entrypoint: `services/auth-service/app/main.py`
- Health endpoint: `GET /health`
- Auth endpoints: `POST /auth/signup`, `POST /auth/login`, `GET /auth/me`, `POST /auth/change-password`, `POST /auth/deactivate`
- Admin endpoint: `GET /admin/users/{user_id}`

## Running

```bash
# Install dependencies
pip install -r requirements.txt

# Run with Uvicorn
uvicorn app.main:app --host 0.0.0.0 --port 8001 --reload
```

## Security Features

- BCrypt password hashing (12 rounds)
- JWT tokens (24-hour expiration)
- Strong password policy (8+ chars, upper, lower, special)
- Rate limiting (max 5 login attempts per 15 minutes)
- Audit logging
- Account lockout
- Role-based access control (user / admin)
