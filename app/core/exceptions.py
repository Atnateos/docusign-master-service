"""
Shared application exceptions.

Kept deliberately small for Day 1 -- grows as auth, rate-limiting, and
job-orchestration logic land in later weeks.
"""


class ServiceError(Exception):
    """Base class for all application-raised errors."""


class ConfigurationError(ServiceError):
    """Raised when required configuration is missing or invalid at startup."""


class DependencyUnavailableError(ServiceError):
    """Raised when a required dependency (DB, MinIO, DocuSign) is unreachable."""

    def __init__(self, dependency: str, detail: str = ""):
        self.dependency = dependency
        self.detail = detail
        super().__init__(f"{dependency} unavailable: {detail}" if detail else f"{dependency} unavailable")
