"""Server settings, read from environment variables or a .env file."""
from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    app_name: str = "Reachwise"
    # Public HTTPS address of this server (the Cloudflare Tunnel URL)
    public_url: str = "http://localhost:8000"

    # MongoDB Atlas connection string: mongodb+srv://user:pass@cluster.xxxx.mongodb.net
    mongodb_uri: str = "mongodb://localhost:27017"
    mongodb_db: str = "profmail"

    # Secrets. Generate with: python -m app.keys
    jwt_secret: str = ""
    encryption_key: str = ""          # Fernet key used to encrypt app passwords
    jwt_days: int = 30

    # Google sign-in. Comma-separated OAuth client IDs whose ID tokens we accept
    # (Web client + Android client). The web client also needs its secret for the
    # browser/desktop redirect sign-in.
    google_client_ids: str = ""
    google_web_client_id: str = ""
    google_web_client_secret: str = ""
    # Where the web app lives, allowed as a sign-in return address (besides localhost)
    allowed_return_origins: str = ""

    # Testing only: lets POST /auth/dev sign in with any email. Never enable on the internet.
    dev_login: bool = False

    # Claude
    anthropic_api_key: str = ""
    claude_fast_model: str = "claude-haiku-5-5"

    # Sending
    min_gap_seconds: int = 70
    max_gap_seconds: int = 120
    daily_cap: int = 80                # per student per 24 hours
    max_attachments_mb: int = 20       # Gmail's hard limit is 25 MB
    reminder_after_days: int = 5
    send_workers: int = 8              # students whose emails can be sent at the same moment
    max_reminders: int = 2

    # Background jobs. Run uvicorn with ONE worker so jobs don't run twice.
    run_scheduler: bool = True
    nudge_check_minutes: int = 60

    # Optional Firebase push (path to a service account JSON). Empty = in-app + email nudges only.
    firebase_credentials: str = ""

    @property
    def client_ids(self) -> list[str]:
        ids = [c.strip() for c in self.google_client_ids.split(",") if c.strip()]
        if self.google_web_client_id and self.google_web_client_id not in ids:
            ids.append(self.google_web_client_id)
        return ids

    @property
    def return_origins(self) -> list[str]:
        return [o.strip().rstrip("/") for o in self.allowed_return_origins.split(",") if o.strip()]


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
