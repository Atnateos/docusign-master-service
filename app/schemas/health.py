from pydantic import BaseModel


class DependencyStatus(BaseModel):
    database: bool
    minio: bool


class HealthResponse(BaseModel):
    status: str  # "ok" | "degraded"
    dependencies: DependencyStatus
