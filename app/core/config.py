"""
Centralized, environment-driven configuration.

Everything the service needs to run lives here, grouped by concern. Values
are read from environment variables (or a local .env file in development),
see .env.example for the full list and sane defaults.
"""
from functools import lru_cache
from typing import List

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # ---- App ----
    app_env: str = Field(default="development", alias="APP_ENV")
    log_level: str = Field(default="INFO", alias="LOG_LEVEL")
    debug: bool = Field(default=True, alias="DEBUG")

    # ---- Database ----
    database_url: str = Field(
        default="postgresql+asyncpg://docusign:docusign@localhost:5432/docusign_master",
        alias="DATABASE_URL",
    )
    database_pool_size: int = Field(default=5, alias="DATABASE_POOL_SIZE")

    # ---- DocuSign API ----
    docusign_integration_key: str = Field(default="", alias="DOCUSIGN_INTEGRATION_KEY")
    docusign_user_id: str = Field(default="", alias="DOCUSIGN_USER_ID")
    docusign_private_key_path: str = Field(default="", alias="DOCUSIGN_PRIVATE_KEY_PATH")
    docusign_auth_server: str = Field(default="account-d.docusign.com", alias="DOCUSIGN_AUTH_SERVER")
    docusign_request_timeout_seconds: int = Field(default=30, alias="DOCUSIGN_REQUEST_TIMEOUT_SECONDS")

    # ---- Rate limiting ----
    docusign_max_retries_on_429: int = Field(default=10, alias="DOCUSIGN_MAX_RETRIES_ON_429")
    docusign_default_retry_after_seconds: int = Field(
        default=30, alias="DOCUSIGN_DEFAULT_RETRY_AFTER_SECONDS"
    )

    # ---- Pagination ----
    docusign_default_page_size: int = Field(default=100, alias="DOCUSIGN_DEFAULT_PAGE_SIZE")

    # ---- MinIO ----
    minio_endpoint: str = Field(default="localhost:9000", alias="MINIO_ENDPOINT")
    minio_access_key: str = Field(default="minioadmin", alias="MINIO_ACCESS_KEY")
    minio_secret_key: str = Field(default="minioadmin", alias="MINIO_SECRET_KEY")
    minio_bucket: str = Field(default="docusign", alias="MINIO_BUCKET")
    minio_secure: bool = Field(default=False, alias="MINIO_SECURE")

    # ---- Resilience ----
    external_call_max_retries: int = Field(default=3, alias="EXTERNAL_CALL_MAX_RETRIES")
    external_call_retry_delays: str = Field(default="1,2,5", alias="EXTERNAL_CALL_RETRY_DELAYS")
    external_call_jitter: float = Field(default=0.5, alias="EXTERNAL_CALL_JITTER")
    dlq_payload_max_bytes: int = Field(default=16384, alias="DLQ_PAYLOAD_MAX_BYTES")

    # ---- HMAC auth ----
    hmac_enabled: bool = Field(default=True, alias="HMAC_ENABLED")
    hmac_secret_key_core: str = Field(default="", alias="HMAC_SECRET_KEY_CORE")
    hmac_secret_key_engineer: str = Field(default="", alias="HMAC_SECRET_KEY_ENGINEER")
    hmac_signature_max_age: int = Field(default=300, alias="HMAC_SIGNATURE_MAX_AGE")

    @field_validator("external_call_retry_delays")
    @classmethod
    def _validate_delays(cls, v: str) -> str:
        # stored as a raw string, parsed via the property below -- validated here
        # so startup fails fast on a malformed value rather than at first retry.
        [float(x) for x in v.split(",") if x.strip()]
        return v

    @property
    def retry_delays(self) -> List[float]:
        return [float(x) for x in self.external_call_retry_delays.split(",") if x.strip()]

    def validate_for_environment(self) -> None:
        """
        Fail fast at startup if required secrets are missing/placeholder in a
        non-development environment. Call this once during app startup.
        """
        if self.app_env.lower() in ("staging", "production"):
            problems = []
            if self.debug:
                problems.append("DEBUG must be false outside development")
            if not self.hmac_enabled:
                problems.append("HMAC_ENABLED must be true outside development")
            placeholder_markers = ("changeme", "", "minioadmin")
            if self.hmac_secret_key_core.lower() in placeholder_markers:
                problems.append("HMAC_SECRET_KEY_CORE is missing or a placeholder")
            if self.hmac_secret_key_engineer.lower() in placeholder_markers:
                problems.append("HMAC_SECRET_KEY_ENGINEER is missing or a placeholder")
            if self.docusign_integration_key.lower() in placeholder_markers:
                problems.append("DOCUSIGN_INTEGRATION_KEY is missing or a placeholder")
            if problems:
                raise RuntimeError(
                    "Refusing to start in '%s' with invalid configuration:\n  - %s"
                    % (self.app_env, "\n  - ".join(problems))
                )


@lru_cache
def get_settings() -> Settings:
    """Settings are read once and cached; env vars won't be re-read after this."""
    return Settings()
