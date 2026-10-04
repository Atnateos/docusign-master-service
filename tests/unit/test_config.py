"""
Tests for app/core/config.py.

Covers: settings parse from env vars, the staging/production fail fast check
rejects placeholder secrets, and .env.example itself never contains anything
that looks like a real credential.
"""
import json
from pathlib import Path

import pytest

from app.core.config import Settings, _looks_like_placeholder


def _settings(**overrides) -> Settings:
    """Build a Settings instance from explicit kwargs only (ignore local .env)."""
    base = dict(
        APP_ENV="development",
        DEBUG=True,
        HMAC_ENABLED=True,
        HMAC_SECRET_KEY_CORE="",
        HMAC_SECRET_KEY_ENGINEER="",
        DOCUSIGN_INTEGRATION_KEY="",
        DOCUSIGN_USER_ID="",
        DOCUSIGN_PRIVATE_KEY_PATH="",
        MINIO_ACCESS_KEY="minioadmin",
        MINIO_SECRET_KEY="minioadmin",
        HMAC_CLIENT_CONFIG="{}",
    )
    base.update(overrides)
    return Settings(_env_file=None, **base)


def test_defaults_are_safe_for_local_dev():
    settings = _settings()
    assert settings.app_env == "development"
    settings.validate_for_environment()  # must not raise in development


def test_retry_delays_parses_csv():
    settings = _settings(EXTERNAL_CALL_RETRY_DELAYS="1,2,5")
    assert settings.retry_delays == [1.0, 2.0, 5.0]


def test_hmac_client_config_parses_json():
    settings = _settings(HMAC_CLIENT_CONFIG=json.dumps({"coord": "core", "eng": "engineer"}))
    assert settings.hmac_client_config == {"coord": "core", "eng": "engineer"}


def test_hmac_client_config_rejects_invalid_role():
    with pytest.raises(ValueError):
        _settings(HMAC_CLIENT_CONFIG=json.dumps({"coord": "admin"}))


@pytest.mark.parametrize("env", ["staging", "production"])
def test_refuses_to_start_with_placeholder_secrets(env):
    settings = _settings(APP_ENV=env)  # all placeholders by default
    with pytest.raises(RuntimeError, match="Refusing to start"):
        settings.validate_for_environment()


@pytest.mark.parametrize("env", ["staging", "production"])
def test_starts_with_real_looking_secrets_present(env):
    settings = _settings(
        APP_ENV=env,
        DEBUG=False,
        HMAC_SECRET_KEY_CORE="a-real-random-core-secret",
        HMAC_SECRET_KEY_ENGINEER="a-real-random-engineer-secret",
        DOCUSIGN_INTEGRATION_KEY="11111111-2222-3333-4444-555555555555",
        DOCUSIGN_USER_ID="66666666-7777-8888-9999-000000000000",
        DOCUSIGN_PRIVATE_KEY_PATH="/run/secrets/docusign_private_key.pem",
        MINIO_ACCESS_KEY="real-minio-access-key",
        MINIO_SECRET_KEY="real-minio-secret-key",
        HMAC_CLIENT_CONFIG=json.dumps({"coordinator-prod": "core"}),
    )
    settings.validate_for_environment()  # must not raise


def test_settings_repr_never_leaks_secrets():
    settings = _settings(HMAC_SECRET_KEY_CORE="super-secret-value")
    assert "super-secret-value" not in repr(settings)
    assert "super-secret-value" not in str(settings)


def test_placeholder_detector():
    assert _looks_like_placeholder("changeme")
    assert _looks_like_placeholder("")
    assert _looks_like_placeholder("minioadmin")
    assert not _looks_like_placeholder("a-real-random-secret-value")


def test_env_example_contains_no_real_looking_secrets():
    """
    Guard against a future edit accidentally committing a real credential
    into .env.example: every *_KEY / *_SECRET-ish value in the file must be
    an obvious placeholder.
    """
    env_example = Path(__file__).resolve().parents[2] / ".env.example"
    assert env_example.exists(), ".env.example must exist at the repo root"

    suspicious_suffixes = ("KEY", "SECRET", "PASSWORD", "TOKEN")
    for line in env_example.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        if any(key.endswith(suffix) for suffix in suspicious_suffixes):
            # Allow the HMAC_CLIENT_CONFIG JSON line through. it's not a
            # secret value itself, just named *_CONFIG, so it won't match.
            assert _looks_like_placeholder(value) or value.startswith("changeme"), (
                f"{key} in .env.example looks like it might be a real credential: {value!r}"
            )
