"""
Thin wrapper around the MinIO SDK.

Day 1 scope: connectivity + bucket-ensure, used by the health endpoint.
upload_normalized_data() (writing the partitioned Parquet layout described
in DESIGN.md) is added alongside the normalization step in Week 3/4.
"""
import logging
from functools import lru_cache

from minio import Minio
from minio.error import S3Error

from app.core.config import get_settings

logger = logging.getLogger(__name__)


@lru_cache
def get_minio_client() -> Minio:
    settings = get_settings()
    return Minio(
        settings.minio_endpoint,
        access_key=settings.minio_access_key,
        secret_key=settings.minio_secret_key,
        secure=settings.minio_secure,
    )


def ensure_bucket_exists() -> None:
    settings = get_settings()
    client = get_minio_client()
    if not client.bucket_exists(settings.minio_bucket):
        client.make_bucket(settings.minio_bucket)
        logger.info("Created MinIO bucket '%s'", settings.minio_bucket)


def check_minio_connection() -> bool:
    """Used by /api/health -- returns True if the bucket is reachable (creating it if absent)."""
    try:
        ensure_bucket_exists()
        return True
    except S3Error:
        logger.exception("MinIO health check failed")
        return False
    except Exception:
        logger.exception("MinIO health check failed (connection error)")
        return False
