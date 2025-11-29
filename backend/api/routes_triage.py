"""
Triage API routes.

Provides endpoints for incident triage scoring.
"""

from typing import Any

from fastapi import APIRouter, HTTPException

from app.models import IncidentRequest, TriageResult
from app.agents.triage import score_incident, triage_incident, get_example_features

router = APIRouter(prefix="/triage", tags=["Agent Tools"])


@router.post(
    "",
    response_model=TriageResult,
    summary="Score an incident using rule-based triage",
    description="""
    Analyze incident features using a deterministic, weighted rule engine
    to produce an explainable severity classification.
    
    The triage engine evaluates features like:
    - failed_logins_last_hour
    - process_spawn_count
    - suspicious_file_activity
    - rare_outgoing_connection
    
    Returns a severity label (LOW/MEDIUM/HIGH), score, and contribution breakdown.
    """,
    responses={
        200: {
            "description": "Successful triage",
            "content": {
                "application/json": {
                    "example": {
                        "label": "HIGH",
                        "score": 8,
                        "contribs": [
                            ["failed_logins_last_hour", 3],
                            ["suspicious_file_activity", 2],
                            ["rare_outgoing_connection", 2],
                        ],
                    }
                }
            },
        }
    },
)
async def triage_endpoint(request: IncidentRequest) -> TriageResult:
    """
    Score an incident and return triage results.
    
    This endpoint runs the deterministic rule engine on the provided
    incident features and returns:
    - Severity label (LOW, MEDIUM, HIGH)
    - Numeric score
    - Contributing factors with their point values
    """
    try:
        label, score, contribs = score_incident(request.features)
        return TriageResult(label=label, score=score, contribs=contribs)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Triage error: {str(e)}")


@router.post(
    "/detailed",
    summary="Get detailed triage with explanations",
    description="Returns triage results with human-readable descriptions for each factor.",
)
async def triage_detailed_endpoint(request: IncidentRequest) -> dict[str, Any]:
    """
    Get detailed triage results with factor descriptions.
    """
    try:
        result = triage_incident(request.features)
        return result
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Triage error: {str(e)}")


@router.get(
    "/examples",
    summary="Get example incident features",
    description="Returns example feature sets for testing different severity levels.",
)
async def get_examples() -> dict[str, dict[str, Any]]:
    """
    Get example incident features for different scenarios.
    """
    return get_example_features()
