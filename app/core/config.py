"""
Centralized, environment-driven configuration (DESIGN.md §10.8).

Every setting is read from the process environment (or a local .env file in
development -- see .env.example for the full list with safe defaults).

Hard rule: nothing in this module, in .env.example, or in any committed file
ever holds a real secret. Real values live only in an untracked .env file,
in the environment the container is launched with, or in injected secrets
(see SecretRef / docusign_private_key below). validate_for_environment()
exists specifically to make the app refuse to boot in staging/production if
that rule has been violated.
"""
import json
import logging
from functools import lru_cache
from typing import Dict, List

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

logger = logging.getLogger(__name__)

# Values that must never be treated as a real secret, wherever they show up.
# Anything matching one of these (case-insensitive) is a placeholder, not a
# credential, and is what validate_for_environment() rejects outside dev.
_PLACEHOLDER_MARKERS = {"", "changeme", "change-me", "replace-me", "minioadmin", "example"}


def _looks_like_placeholder(value: str) -> bool:
    return value.strip().lower() in _PLACEHOLDER_MARKERS


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # ---- App metadata ----
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
    # DOCUSIGN_PRIVATE_KEY_PATH points at a file mounted into the container
    # (a Docker/K8s secret, or a Vault-templated path in staging/prod) -- the
    # key's *contents* are never an env var and never committed. See
    # docusign_private_key_path_is_set() below, used by the startup check.
    docusign_integration_key: str = Field(default="", alias="DOCUSIGN_INTEGRATION_KEY")
    docusign_user_id: str = Field(default="", alias="DOCUSIGN_USER_ID")
    docusign_private_key_path: str = Field(default="", alias="DOCUSIGN_PRIVATE_KEY_PATH")
    docusign_auth_server: str = Field(default="account-d.docusign.com", alias="DOCUSIGN_AUTH_SERVER")
    docusign_request_timeout_seconds: int = Field(
        default=30, alias="DOCUSIGN_REQUEST_TIMEOUT_SECONDS"
    )

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
    # JSON map of client_id -> role ("core" | "engineer"), e.g.
    #   {"coordinator-prod": "core", "eng-readonly": "engineer"}
    # Stored as a raw JSON string in the env (see .env.example); parsed via
    # hmac_client_config below. Client IDs are not secrets, only the keys are.
    hmac_client_config_raw: str = Field(default="{}", alias="HMAC_CLIENT_CONFIG")

    # ---- Health check ----
    health_check_timeout_seconds: int = Field(default=5, alias="HEALTH_CHECK_TIMEOUT_SECONDS")

    @field_validator("external_call_retry_delays")
    @classmethod
    def _validate_delays(cls, v: str) -> str:
        # Stored as a raw string, parsed via the `retry_delays` property below;
        # validated here so startup fails fast on a malformed value rather
        # than at first retry.
        [float(x) for x in v.split(",") if x.strip()]
        return v

    @field_validator("hmac_client_config_raw")
    @classmethod
    def _validate_client_config(cls, v: str) -> str:
        parsed = json.loads(v)  # raises -> fails fast at startup if malformed
        if not isinstance(parsed, dict):
            raise ValueError("HMAC_CLIENT_CONFIG must be a JSON object of {client_id: role}")
        for client_id, role in parsed.items():
            if role not in ("core", "engineer"):
                raise ValueError(
                    f"HMAC_CLIENT_CONFIG role for '{client_id}' must be 'core' or 'engineer', got '{role}'"
                )
        return v

    @property
    def retry_delays(self) -> List[float]:
        return [float(x) for x in self.external_call_retry_delays.split(",") if x.strip()]

    @property
    def hmac_client_config(self) -> Dict[str, str]:
        return json.loads(self.hmac_client_config_raw)

    def docusign_private_key_path_is_set(self) -> bool:
        """
        True only if a real file path was configured -- never checks file
        contents, since this process should never hold the key in memory as
        a settings value. The actual key is read from disk at auth time by
        DocuSignAuthClient, not stored here.
        """
        return bool(self.docusign_private_key_path.strip())

    def validate_for_environment(self) -> None:
        """
        Fail fast at startup if required secrets are missing/placeholder
        outside development. Call this once during app startup (see
        app/main.py's lifespan handler).
        """
        if self.app_env.lower() not in ("staging", "production"):
            return

        problems: List[str] = []

        if self.debug:
            problems.append("DEBUG must be false outside development")
        if not self.hmac_enabled:
            problems.append("HMAC_ENABLED must be true outside development")

        secret_fields = {
            "HMAC_SECRET_KEY_CORE": self.hmac_secret_key_core,
            "HMAC_SECRET_KEY_ENGINEER": self.hmac_secret_key_engineer,
            "DOCUSIGN_INTEGRATION_KEY": self.docusign_integration_key,
            "DOCUSIGN_USER_ID": self.docusign_user_id,
            "MINIO_ACCESS_KEY": self.minio_access_key,
            "MINIO_SECRET_KEY": self.minio_secret_key,
        }
        for name, value in secret_fields.items():
            if _looks_like_placeholder(value):
                problems.append(f"{name} is missing or still a placeholder value")

        if not self.docusign_private_key_path_is_set():
            problems.append("DOCUSIGN_PRIVATE_KEY_PATH is not set")

        if not self.hmac_client_config:
            problems.append("HMAC_CLIENT_CONFIG is empty -- no clients would be authorized")

        if problems:
            raise RuntimeError(
                "Refusing to start in '%s' with invalid configuration:\n  - %s"
                % (self.app_env, "\n  - ".join(problems))
            )

    def __repr__(self) -> str:
        # Prevent an accidental `print(settings)` / log line from leaking
        # secrets into logs or error trackers.
        return "Settings(app_env=%r, redacted=True)" % self.app_env

    __str__ = __repr__


@lru_cache
def get_settings() -> Settings:
    """Settings are read once and cached; env vars won't be re-read after this."""
    settings = Settings()
    if settings.app_env.lower() == "development":
        for name, value in {
            "HMAC_SECRET_KEY_CORE": settings.hmac_secret_key_core,
            "HMAC_SECRET_KEY_ENGINEER": settings.hmac_secret_key_engineer,
            "DOCUSIGN_INTEGRATION_KEY": settings.docusign_integration_key,
        }.items():
            if _looks_like_placeholder(value):
                logger.warning(
                    "%s is unset or a placeholder -- fine for local dev, "
                    "but this process would refuse to start in staging/production.",
                    name,
                )
    return settings
