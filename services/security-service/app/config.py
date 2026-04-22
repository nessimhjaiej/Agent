import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv


_PROJECT_ROOT = Path(__file__).resolve().parents[3]
load_dotenv(_PROJECT_ROOT / ".env", override=True)
load_dotenv(_PROJECT_ROOT / ".env.local", override=True)


@dataclass(slots=True)
class Settings:
    app_name: str = "security-service"
    app_version: str = "0.1.0"
    recent_alert_limit: int = 25
    supabase_url: str = ""
    supabase_key: str = ""
    login_attempts_window_hours: int = 24
    login_attempts_max_rows: int = 2000

    @classmethod
    def from_env(cls) -> "Settings":
        defaults = cls()
        return cls(
            app_name=os.getenv("SECURITY_APP_NAME", defaults.app_name),
            app_version=os.getenv("SECURITY_APP_VERSION", defaults.app_version),
            recent_alert_limit=int(
                os.getenv("SECURITY_RECENT_ALERT_LIMIT", str(defaults.recent_alert_limit))
            ),
            supabase_url=os.getenv(
                "SECURITY_SUPABASE_URL",
                os.getenv("AUTH_SUPABASE_URL", defaults.supabase_url),
            ),
            supabase_key=os.getenv(
                "SECURITY_SUPABASE_KEY",
                os.getenv("AUTH_SUPABASE_KEY", defaults.supabase_key),
            ),
            login_attempts_window_hours=int(
                os.getenv(
                    "SECURITY_LOGIN_ATTEMPTS_WINDOW_HOURS",
                    str(defaults.login_attempts_window_hours),
                )
            ),
            login_attempts_max_rows=int(
                os.getenv(
                    "SECURITY_LOGIN_ATTEMPTS_MAX_ROWS",
                    str(defaults.login_attempts_max_rows),
                )
            ),
        )
