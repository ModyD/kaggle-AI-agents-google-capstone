"""
Flow API routes.

Provides the main orchestration endpoint that runs the complete
incident response flow through all agents.
"""

from typing import Any

from fastapi import APIRouter, HTTPException

from app.orchestration.a2a import orchestrate_flow, orchestrate_flow_full
from app.models import FlowRequest, FlowResponse, IncidentRequest, TimelineEntry

router = APIRouter(prefix="/flow", tags=["Agent Tools"])


@router.post(
    "/simulate",
    summary="Run complete incident response flow",
    description="""
    Execute the full incident response flow through all agents:
    
    1. **Triage Agent**: Scores incident using rule-based engine
    2. **Explain Agent**: Generates LLM explanation (parallel)
    3. **Runbook Agent**: Generates response steps with RAG (parallel)
    4. **Policy Agent**: Sanitizes runbook for safety
    5. **Simulator Agent**: Previews runbook execution
    
    Returns a timeline of all agent interactions and events.
    
    This endpoint demonstrates the A2A (Agent-to-Agent) protocol
    with trace IDs for observability.
    """,
    responses={
        200: {
            "description": "Flow timeline",
            "content": {
                "application/json": {
                    "example": [
                        {
                            "actor": "orchestrator",
                            "type": "flow_started",
                            "payload": {"incident_id": "INC-001"},
                            "trace_id": "abc123",
                            "timestamp": "2025-01-15T10:30:00.000Z",
                        },
                        {
                            "actor": "triage_agent",
                            "type": "triage_complete",
                            "payload": {"label": "HIGH", "score": 8},
                            "trace_id": "abc123",
                            "timestamp": "2025-01-15T10:30:00.050Z",
                        },
                    ]
                }
            },
        }
    },
)
async def simulate_flow_endpoint(request: IncidentRequest) -> list[dict[str, Any]]:
    """
    Run the complete incident response flow.
    
    This is the main entry point for processing an incident through
    the multi-agent system.
    """
    try:
        timeline = await orchestrate_flow(
            incident_id=request.incident_id,
            features=request.features,
        )
        # Convert to dict for JSON response
        return [entry.model_dump() for entry in timeline]
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Flow error: {str(e)}")


@router.post(
    "/full",
    response_model=FlowResponse,
    summary="Run flow and return all artifacts",
    description="""
    Execute the complete flow and return all generated artifacts:
    - Triage result with score and label
    - LLM explanation
    - Generated runbook (after policy check)
    - Policy changes made
    - Complete timeline
    
    Use this endpoint when you need all outputs, not just the timeline.
    """,
)
async def full_flow_endpoint(request: FlowRequest) -> FlowResponse:
    """
    Run flow and return complete response with all artifacts.
    """
    try:
        result = await orchestrate_flow_full(request.incident)
        return result
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Flow error: {str(e)}")


@router.post(
    "/triage-and-runbook",
    summary="Quick triage and runbook generation",
    description="Simplified endpoint that returns triage and runbook without full simulation.",
)
async def quick_flow_endpoint(request: IncidentRequest) -> dict[str, Any]:
    """
    Quick triage and runbook without full simulation.
    """
    from app.triage import score_incident
    from app.runbook import generate_runbook
    from app.policy import policy_check

    try:
        # Triage
        label, score, contribs = score_incident(request.features)

        # Generate runbook
        runbook = await generate_runbook(
            features=request.features,
            label=label,
            score=score,
            contribs=contribs,
        )

        # Policy check
        policy_result = policy_check(runbook)

        return {
            "incident_id": request.incident_id,
            "triage": {
                "label": label,
                "score": score,
                "contribs": contribs,
            },
            "runbook": [
                {"step": s.step, "why": s.why, "risk": s.risk}
                for s in policy_result["runbook"]
            ],
            "policy_changes": policy_result["changes"],
            "source": runbook.source,
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Quick flow error: {str(e)}")
