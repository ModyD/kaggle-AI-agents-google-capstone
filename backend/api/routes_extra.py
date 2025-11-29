"""
Additional API routes for memory, metrics, and job management.

Endpoints:
- GET  /memory/search     - Search memory bank
- GET  /metrics           - Get metrics snapshot
- POST /jobs/start        - Start a new job
- GET  /jobs/{id}         - Get job status
- POST /jobs/{id}/pause   - Pause a job
- POST /jobs/{id}/resume  - Resume a job
- POST /jobs/{id}/cancel  - Cancel a job
- GET  /jobs              - List jobs
"""

from typing import Any, Optional

from fastapi import APIRouter, Header, HTTPException, Request
from pydantic import BaseModel, Field

router = APIRouter(tags=["extra"])


# =============================================================================
# Request/Response Models
# =============================================================================


class MemorySearchRequest(BaseModel):
    """Memory search request."""

    q: str = Field(..., description="Search query")
    k: int = Field(5, ge=1, le=50, description="Number of results")
    memory_type: Optional[str] = Field(None, description="Filter by memory type")
    session_id: Optional[str] = Field(None, description="Filter by session")


class MemorySearchResponse(BaseModel):
    """Memory search response."""

    query: str
    results: list[dict]
    count: int


class JobStartRequest(BaseModel):
    """Job start request."""

    job_type: str = Field(..., description="Type of job: runbook_simulation, etc.")
    payload: dict = Field(default_factory=dict, description="Job payload")


class JobStartResponse(BaseModel):
    """Job start response."""

    job_id: str
    status: str
    message: str


class JobStatusResponse(BaseModel):
    """Job status response."""

    job_id: str
    status: str
    progress: float
    created_at: str
    started_at: Optional[str]
    completed_at: Optional[str]
    result: Optional[Any]
    error: Optional[str]
    metadata: dict


class MetricsResponse(BaseModel):
    """Metrics snapshot response."""

    counters: dict
    gauges: dict
    histograms: dict
    timestamp: str


# =============================================================================
# Memory Search Endpoint
# =============================================================================


@router.get(
    "/memory/search",
    response_model=MemorySearchResponse,
    summary="Search memory bank",
    description="Search for similar memories using vector similarity.",
)
async def search_memory(
    q: str,
    k: int = 5,
    memory_type: Optional[str] = None,
    session_id: Optional[str] = None,
    x_trace_id: Optional[str] = Header(None, alias="X-Trace-ID"),
):
    """
    Search memory bank for similar content.

    Args:
        q: Search query text
        k: Number of results (1-50)
        memory_type: Optional filter by memory type
        session_id: Optional filter by session
        x_trace_id: Optional trace ID for correlation

    Returns:
        Search results with similarity scores
    """
    from app.services.memory_bank import retrieve_similar
    from app.core.observability import log_event

    log_event(
        "memory_search_request",
        {"query_length": len(q), "k": k, "filters": {"memory_type": memory_type, "session_id": session_id}},
        trace_id=x_trace_id,
    )

    results = await retrieve_similar(
        text=q,
        k=k,
        memory_type=memory_type,
        session_id=session_id,
        trace_id=x_trace_id,
    )

    return MemorySearchResponse(
        query=q,
        results=[r.model_dump() for r in results],
        count=len(results),
    )


# =============================================================================
# Metrics Endpoint
# =============================================================================


@router.get(
    "/metrics",
    response_model=MetricsResponse,
    summary="Get metrics snapshot",
    description="Get current metrics for dashboard consumption.",
)
async def get_metrics():
    """
    Get current metrics snapshot.

    Returns:
        Metrics including counters, gauges, histograms, and recent history.
    """
    from app.services.agent_evaluation import get_metrics_snapshot

    snapshot = await get_metrics_snapshot()

    return MetricsResponse(
        counters=snapshot.get("counters", {}),
        gauges=snapshot.get("gauges", {}),
        histograms=snapshot.get("histograms", {}),
        timestamp=snapshot.get("timestamp", ""),
    )


# =============================================================================
# Job Management Endpoints
# =============================================================================


def _get_manager(request: Request):
    """Get LongRunningManager from app state."""
    manager = getattr(request.app.state, "long_running_manager", None)
    if not manager:
        raise HTTPException(
            status_code=503,
            detail="Job manager not initialized",
        )
    return manager


@router.post(
    "/jobs/start",
    response_model=JobStartResponse,
    summary="Start a new job",
    description="Start a background job (e.g., runbook simulation).",
)
async def start_job(
    request: Request,
    body: JobStartRequest,
):
    """
    Start a new background job.

    Supported job types:
    - runbook_simulation: Simulate runbook step execution

    Example payload for runbook_simulation:
    {
        "job_type": "runbook_simulation",
        "payload": {
            "incident_id": "INC-001",
            "steps": [
                {"action": "isolate_host", "target": "192.168.1.100"},
                {"action": "block_ip", "target": "10.0.0.1"}
            ]
        }
    }
    """
    from app.orchestration.long_running_manager import create_runbook_simulation_job
    from app.core.observability import log_event

    manager = _get_manager(request)

    if body.job_type == "runbook_simulation":
        steps = body.payload.get("steps", [])
        incident_id = body.payload.get("incident_id", "unknown")

        if not steps:
            raise HTTPException(status_code=400, detail="No steps provided")

        job_id = await create_runbook_simulation_job(
            manager=manager,
            runbook_steps=steps,
            incident_id=incident_id,
        )

        log_event("job_started_via_api", {"job_id": job_id, "type": body.job_type})

        return JobStartResponse(
            job_id=job_id,
            status="pending",
            message=f"Job started with {len(steps)} steps",
        )

    else:
        raise HTTPException(
            status_code=400,
            detail=f"Unknown job type: {body.job_type}",
        )


@router.get(
    "/jobs/{job_id}",
    response_model=JobStatusResponse,
    summary="Get job status",
    description="Get the current status of a job.",
)
async def get_job_status(
    request: Request,
    job_id: str,
):
    """Get job status by ID."""
    manager = _get_manager(request)

    job = await manager.get_job_status(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")

    return JobStatusResponse(
        job_id=job.job_id,
        status=job.status.value,
        progress=job.progress,
        created_at=job.created_at.isoformat(),
        started_at=job.started_at.isoformat() if job.started_at else None,
        completed_at=job.completed_at.isoformat() if job.completed_at else None,
        result=job.result,
        error=job.error,
        metadata=job.metadata,
    )


@router.post(
    "/jobs/{job_id}/pause",
    summary="Pause a job",
    description="Pause a running job. Job will pause at next checkpoint.",
)
async def pause_job(
    request: Request,
    job_id: str,
):
    """Pause a running job."""
    from app.core.observability import log_event

    manager = _get_manager(request)

    success = await manager.pause_job(job_id)
    if not success:
        raise HTTPException(
            status_code=400,
            detail="Cannot pause job (not found or not running)",
        )

    log_event("job_paused_via_api", {"job_id": job_id})

    return {"job_id": job_id, "status": "paused"}


@router.post(
    "/jobs/{job_id}/resume",
    summary="Resume a job",
    description="Resume a paused job.",
)
async def resume_job(
    request: Request,
    job_id: str,
):
    """Resume a paused job."""
    from app.core.observability import log_event

    manager = _get_manager(request)

    success = await manager.resume_job(job_id)
    if not success:
        raise HTTPException(
            status_code=400,
            detail="Cannot resume job (not found or not paused)",
        )

    log_event("job_resumed_via_api", {"job_id": job_id})

    return {"job_id": job_id, "status": "running"}


@router.post(
    "/jobs/{job_id}/cancel",
    summary="Cancel a job",
    description="Cancel a running or paused job.",
)
async def cancel_job(
    request: Request,
    job_id: str,
):
    """Cancel a job."""
    from app.core.observability import log_event

    manager = _get_manager(request)

    success = await manager.cancel_job(job_id)
    if not success:
        raise HTTPException(
            status_code=400,
            detail="Cannot cancel job (not found or already finished)",
        )

    log_event("job_cancelled_via_api", {"job_id": job_id})

    return {"job_id": job_id, "status": "cancelled"}


@router.get(
    "/jobs",
    summary="List jobs",
    description="List all jobs with optional status filter.",
)
async def list_jobs(
    request: Request,
    status: Optional[str] = None,
    limit: int = 50,
):
    """
    List jobs with optional filters.

    Args:
        status: Filter by status (pending, running, paused, completed, failed, cancelled)
        limit: Maximum results (default 50)
    """
    from app.orchestration.long_running_manager import JobStatus

    manager = _get_manager(request)

    # Parse status filter
    status_filter = None
    if status:
        try:
            status_filter = JobStatus(status)
        except ValueError:
            raise HTTPException(
                status_code=400,
                detail=f"Invalid status: {status}. Valid values: {[s.value for s in JobStatus]}",
            )

    jobs = await manager.list_jobs(status=status_filter, limit=limit)

    return {
        "jobs": [
            {
                "job_id": j.job_id,
                "status": j.status.value,
                "progress": j.progress,
                "created_at": j.created_at.isoformat(),
                "metadata": j.metadata,
            }
            for j in jobs
        ],
        "count": len(jobs),
    }
