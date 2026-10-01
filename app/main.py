"""
DocuSign Master Service -- FastAPI entrypoint.

Day 1 scope: app bootstrap, config, logging, health endpoint, and the
DB/MinIO plumbing the health check depends on. Scan/normalization/
credentials/maintenance/audit routers are added as their respective
services land in later milestones (see DESIGN.md).
"""
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.api import health
from app.core.config import get_settings
from app.core.logging import configure_logging
from app.db.database import dispose_engine

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    configure_logging()
    settings = get_settings()
    settings.validate_for_environment()
    logger.info("Starting docusign-master-service (env=%s)", settings.app_env)

    yield

    logger.info("Shutting down docusign-master-service")
    await dispose_engine()


def create_app() -> FastAPI:
    app = FastAPI(
        title="DocuSign Master Service",
        description="Pulls, normalizes, and publishes DocuSign envelope data on demand.",
        version="0.1.0",
        lifespan=lifespan,
    )

    # Public, unauthenticated routes
    app.include_router(health.router, prefix="/api")

    # Authenticated routers (scan, normalization, credentials, maintenance, audit)
    # are wired in here as they're implemented:
    #
    # from app.api import scan, normalization, credentials, maintenance, audit
    # app.include_router(scan.router, prefix="/api/scan", tags=["scan"])
    # app.include_router(normalization.router, prefix="/api/normalization", tags=["normalization"])
    # app.include_router(credentials.router, prefix="/api", tags=["credentials"])
    # app.include_router(maintenance.router, prefix="/api/maintenance", tags=["maintenance"])
    # app.include_router(audit.router, prefix="/api/audit", tags=["audit"])

    return app


app = create_app()
