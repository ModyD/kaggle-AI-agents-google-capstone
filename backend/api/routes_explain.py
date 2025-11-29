"""
Explain API routes.

Provides endpoints for LLM-powered incident explanations.
"""

from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from app.agents.explain import explain_incident
from app.models import TriageExplanation

router = APIRouter(prefix="/explain", tags=["Agent Tools"])


class ExplainRequest(BaseModel):
    """Request payload for explanation generation."""

    features: dict[str, Any] = Field(
        ...,
        description="Incident features",
        examples=[{"failed_logins_last_hour": 50, "suspicious_file_activity": True}],
    )
    label: str = Field(
        ...,
        description="Triage severity label",
        examples=["HIGH"],
    )
    score: int = Field(
        ...,
        description="Triage score",
        examples=[8],
    )
    contribs: list[tuple[str, int]] = Field(
        ...,
        description="Contributing factors",
        examples=[[("failed_logins_last_hour", 3), ("suspicious_file_activity", 2)]],
    )


@router.post(
    "",
    response_model=TriageExplanation,
    summary="Generate explanation for triage decision",
    description="""
    Use LLM (Gemini) to generate a natural language explanation
    of why an incident was classified at a particular severity level.
    
    Returns:
    - explanation: A 2-3 sentence description of the classification
    - reasons: Specific bullet points supporting the decision
    
    If LLM is unavailable, returns a template-based explanation.
    """,
    responses={
        200: {
            "description": "Successful explanation",
            "content": {
                "application/json": {
                    "example": {
                        "explanation": "This incident was classified as HIGH severity due to multiple indicators of a potential brute force attack combined with suspicious outbound connections.",
                        "reasons": [
                            "50 failed login attempts in the last hour indicates active credential stuffing",
                            "Rare outbound connection suggests potential command and control activity",
                        ],
                    }
                }
            },
        }
    },
)
async def explain_endpoint(request: ExplainRequest) -> dict[str, Any]:
    """
    Generate an LLM-powered explanation of triage results.
    """
    try:
        result = await explain_incident(
            features=request.features,
            label=request.label,
            score=request.score,
            contribs=request.contribs,
        )
        return result
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Explanation error: {str(e)}")
