"""
Health check API routes.

Provides endpoints for monitoring application health and status.
"""

from typing import Any

from fastapi import APIRouter

from app.config import get_settings, is_db_available, is_llm_available, is_redis_available
from app.models import HealthResponse

router = APIRouter(tags=["Health"])


@router.get(
    "/health",
    response_model=HealthResponse,
    summary="Health check endpoint",
    description="Returns application health status and service availability.",
)
async def health_check() -> HealthResponse:
    """
    Check application health.
    
    Returns:
    - status: healthy/degraded/unhealthy
    - version: Application version
    - services: Status of dependent services
    """
    settings = get_settings()

    services = {
        "database": is_db_available(),
        "redis": is_redis_available(),
        "llm": is_llm_available(),
    }

    # Determine overall status
    if all(services.values()):
        status = "healthy"
    elif any(services.values()):
        status = "degraded"
    else:
        # Core functionality works without external services
        status = "healthy"

    return HealthResponse(
        status=status,
        version=settings.app_version,
        services=services,
    )


@router.get(
    "/",
    summary="Root endpoint",
    description="Returns basic API information.",
)
async def root() -> dict[str, Any]:
    """
    Root endpoint with API info.
    """
    settings = get_settings()

    return {
        "name": settings.app_name,
        "version": settings.app_version,
        "description": "Enterprise Security Incident Triage & Autonomous Runbook Agent API",
        "docs": "/docs",
        "openapi": "/openapi.json",
    }


@router.get(
    "/ready",
    summary="Readiness probe",
    description="Kubernetes readiness probe endpoint.",
)
async def readiness() -> dict[str, str]:
    """
    Readiness probe for Kubernetes/Cloud Run.
    """
    return {"status": "ready"}


@router.get(
    "/live",
    summary="Liveness probe",
    description="Kubernetes liveness probe endpoint.",
)
async def liveness() -> dict[str, str]:
    """
    Liveness probe for Kubernetes/Cloud Run.
    """
    return {"status": "alive"}
