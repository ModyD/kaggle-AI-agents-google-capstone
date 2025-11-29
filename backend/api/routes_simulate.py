"""
Simulate API routes.

Provides endpoints for runbook simulation and dry-run.
"""

from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from app.models import RunbookStep
from app.agents.simulate import simulate_runbook, simulate_runbook_steps, dry_run_runbook

router = APIRouter(prefix="/simulate", tags=["Agent Tools"])


class SimulateRequest(BaseModel):
    """Request payload for simulation."""

    runbook: list[dict[str, Any]] = Field(
        ...,
        description="List of runbook steps to simulate",
        examples=[
            [
                {"step": "Isolate host", "why": "Containment", "risk": "medium"},
                {"step": "Review logs", "why": "Investigation", "risk": "low"},
            ]
        ],
    )
    source: str = Field(
        default="api",
        description="Source of the runbook",
    )
    trace_id: str | None = Field(
        default=None,
        description="Optional trace ID for correlation",
    )


class SimulationEvent(BaseModel):
    """A single simulation event."""

    type: str = Field(..., description="Event type")
    step_index: int | None = Field(None, description="Step index if applicable")
    step: str | None = Field(None, description="Step text if applicable")
    outcome: str | None = Field(None, description="Simulation outcome")
    message: str | None = Field(None, description="Human-readable message")
    timestamp: str = Field(..., description="ISO timestamp")
    trace_id: str = Field(..., description="Trace ID")


class DryRunRequest(BaseModel):
    """Request for dry run analysis."""

    steps: list[dict[str, Any]] = Field(
        ...,
        description="Runbook steps to analyze",
    )


@router.post(
    "",
    summary="Simulate runbook execution",
    description="""
    Simulate execution of a runbook without actually running commands.
    
    For each step, emits:
    - Start event when simulation begins
    - End event with outcome (simulated_ok or simulated_warn)
    
    Higher risk steps have higher probability of warnings.
    Includes timing information and trace IDs for observability.
    """,
    responses={
        200: {
            "description": "Simulation events",
            "content": {
                "application/json": {
                    "example": [
                        {
                            "type": "simulation_start",
                            "total_steps": 2,
                            "timestamp": "2025-01-15T10:30:00.000Z",
                            "trace_id": "abc123",
                        },
                        {
                            "type": "simulation_step_start",
                            "step_index": 0,
                            "step": "Isolate host",
                            "risk": "medium",
                            "timestamp": "2025-01-15T10:30:00.100Z",
                            "trace_id": "abc123",
                        },
                        {
                            "type": "simulation_step_end",
                            "step_index": 0,
                            "outcome": "simulated_ok",
                            "message": "Step would execute successfully",
                            "duration_ms": 250,
                            "timestamp": "2025-01-15T10:30:00.350Z",
                            "trace_id": "abc123",
                        },
                    ]
                }
            },
        }
    },
)
async def simulate_endpoint(request: SimulateRequest) -> list[dict[str, Any]]:
    """
    Simulate runbook execution.
    """
    try:
        runbook_dict = {
            "runbook": request.runbook,
            "source": request.source,
        }
        events = await simulate_runbook(runbook_dict, request.trace_id)
        return events
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Simulation error: {str(e)}")


@router.post(
    "/dry-run",
    summary="Dry run analysis of runbook",
    description="""
    Perform a quick dry-run analysis without simulating delays.
    
    Identifies:
    - Steps requiring manual approval
    - High-impact steps
    - Risk keyword detection
    """,
)
async def dry_run_endpoint(request: DryRunRequest) -> dict[str, Any]:
    """
    Perform dry run analysis.
    """
    try:
        steps = [
            RunbookStep(
                step=s.get("step", ""),
                why=s.get("why", ""),
                risk=s.get("risk", "medium"),
            )
            for s in request.steps
        ]
        result = dry_run_runbook(steps)
        return result
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Dry run error: {str(e)}")
