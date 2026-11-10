"""Application settings — exact env var names per spec/architecture.md §Environment variables."""

from pydantic import Field, SecretStr, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

DEFAULT_DATABASE_URL = "sqlite:///data/workshop0.db"
DEFAULT_PORT = 8001
_LOG_LEVELS = {"DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"}


def _strip_inline_comment(value: str) -> str:
    return value.split("#", 1)[0].strip()


def normalize_database_url(url: str) -> str:
    """Route bare postgres:// / postgresql:// URLs to the psycopg 3 driver."""
    url = url.strip()
    for prefix in ("postgres://", "postgresql://"):
        if url.startswith(prefix):
            return "postgresql+psycopg://" + url[len(prefix) :]
    return url


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    database_url: str = Field(default=DEFAULT_DATABASE_URL)
    port: int = Field(default=DEFAULT_PORT)
    workshop0_db_pool_size: int = Field(default=3)
    workshop0_db_max_overflow: int = Field(default=2)
    workshop0_admin_key: str = Field(default="")
    workshop0_base_url: str = Field(default="")
    workshop0_log_level: str = Field(default="INFO")
    openrouter_api_key: str = Field(default="")
    workshop0_ai_model: str = Field(default="anthropic/claude-sonnet-4-6")
    workshop0_ai_confidence: float = Field(default=0.75)

    # Phase 11 — network identity (validation lives in auth/startup.py).
    workshop0_google_client_id: str = Field(default="")
    workshop0_google_client_secret: str = Field(default="")
    workshop0_oidc_issuer: str = Field(default="https://accounts.google.com")
    workshop0_session_secret: str = Field(default="")
    workshop0_admin_emails: str = Field(default="")
    # Phase 11 — CV storage.
    workshop0_blob_backend: str = Field(default="local")
    workshop0_gcs_bucket: str = Field(default="")
    # Phase 11 — network AI (Anthropic direct; spec/agent.md §Provider).
    anthropic_api_key: str = Field(default="")
    anthropic_workspace_id: str = Field(default="")
    workshop0_ai_network_model: str = Field(default="claude-sonnet-5-5")
    workshop0_ai_network_fast_model: str = Field(default="claude-haiku-5-5")

    # Phase 12 - transactional email over SMTP (all optional; production boots with every
    # field absent, in which case outbox rows are `recorded`, not sent).
    workshop0_smtp_host: str = Field(default="")
    workshop0_smtp_port: int = Field(default=587)
    workshop0_smtp_starttls: bool = Field(default=True)
    workshop0_smtp_user: str = Field(default="")
    workshop0_smtp_password: SecretStr = Field(default=SecretStr(""), repr=False)
    workshop0_smtp_from: str = Field(default="")
    workshop0_email_rate_per_recipient: int = Field(default=10)  # per rolling hour
    workshop0_email_rate_global: int = Field(default=100)  # per rolling hour

    # Phase 13 - optional shared key for POST /api/cron/weekly-digest (unset => endpoint 404s).
    workshop0_cron_key: SecretStr = Field(default=SecretStr(""), repr=False)

    @field_validator("database_url")
    @classmethod
    def _normalize_database_url(cls, value: str) -> str:
        return normalize_database_url(value)

    @property
    def resolved_admin_key(self) -> str:
        return self.workshop0_admin_key.strip()

    @property
    def smtp_configured(self) -> bool:
        """True only when host, user and password are all set."""
        return bool(
            self.workshop0_smtp_host.strip()
            and self.workshop0_smtp_user.strip()
            and self.workshop0_smtp_password.get_secret_value()
        )

    @property
    def cron_enabled(self) -> bool:
        return bool(self.workshop0_cron_key.get_secret_value().strip())

    @property
    def resolved_smtp_from(self) -> str:
        return self.workshop0_smtp_from.strip() or self.workshop0_smtp_user.strip()

    @property
    def resolved_base_url(self) -> str:
        return _strip_inline_comment(self.workshop0_base_url).rstrip("/")

    @property
    def resolved_log_level(self) -> str:
        level = _strip_inline_comment(self.workshop0_log_level).upper()
        return level if level in _LOG_LEVELS else "INFO"


_settings: Settings | None = None


def get_settings() -> Settings:
    global _settings
    if _settings is None:
        _settings = Settings()
    return _settings
