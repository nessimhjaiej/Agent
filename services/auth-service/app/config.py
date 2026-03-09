import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv

# Walk up from this file to find the project root .env
_PROJECT_ROOT = (
    Path(__file__).resolve().parents[3]
)  # auth-service/app/config.py → Agent/
load_dotenv(_PROJECT_ROOT / ".env", override=True)
load_dotenv(_PROJECT_ROOT / ".env.local", override=True)


@dataclass(slots=True)
class Settings:
    app_name: str = "auth-service"
    app_version: str = "0.1.0"

    # Supabase
    supabase_url: str = ""
    supabase_key: str = ""

    # Rate limiting (kept for audit purposes)
    max_login_attempts: int = 5
    lockout_duration_minutes: int = 15

    @classmethod
    def from_env(cls) -> "Settings":
        return cls(
            app_name=os.getenv("AUTH_APP_NAME", "auth-service"),
            app_version=os.getenv("AUTH_APP_VERSION", "0.1.0"),
            supabase_url=os.getenv("AUTH_SUPABASE_URL", ""),
            supabase_key=os.getenv("AUTH_SUPABASE_KEY", ""),
            max_login_attempts=int(os.getenv("AUTH_MAX_LOGIN_ATTEMPTS", "5")),
            lockout_duration_minutes=int(
                os.getenv("AUTH_LOCKOUT_DURATION_MINUTES", "15")
            ),
        )
