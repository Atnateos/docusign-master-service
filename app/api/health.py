"""
Public, unauthenticated endpoints: /api/health and /api/stats.

No HMAC required here -- these back container orchestrator liveness/readiness
probes, which can't sign requests.
"""
from fastapi import APIRouter, Response, status

from app.db.database import check_database_connection
from app.schemas.health import DependencyStatus, HealthResponse
from app.storage.minio_client import check_minio_connection

router = APIRouter(tags=["health"])


@router.get("/health", response_model=HealthResponse)
async def health(response: Response) -> HealthResponse:
    db_ok = await check_database_connection()
    minio_ok = check_minio_connection()

    overall_ok = db_ok and minio_ok
    if not overall_ok:
        response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE

    return HealthResponse(
        status="ok" if overall_ok else "degraded",
        dependencies=DependencyStatus(database=db_ok, minio=minio_ok),
    )


@router.get("/stats")
async def service_stats() -> dict:
    # Placeholder until JobService exists (Week 1/2) -- will report job counts
    # by status, last run time, etc.
    return {"jobs_tracked": 0}
