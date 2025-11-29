"""
Runbook API routes.

Provides endpoints for RAG-enhanced runbook generation.
"""

from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from app.models import RunbookResponse
from app.runbook import generate_runbook, generate_runbook_from_description, get_template_runbook

router = APIRouter(prefix="/runbook", tags=["Agent Tools"])


class RunbookRequest(BaseModel):
    """Request payload for runbook generation."""

    features: dict[str, Any] = Field(
        ...,
        description="Incident features",
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
        default_factory=list,
        description="Contributing factors",
    )


class DescriptionRequest(BaseModel):
    """Request for runbook from free-text description."""

    description: str = Field(
        ...,
        description="Natural language incident description",
        min_length=10,
        examples=["Suspected ransomware infection on finance server with encrypted files"],
    )
    severity: str = Field(
        default="MEDIUM",
        description="Severity level",
        examples=["HIGH", "MEDIUM", "LOW"],
    )


@router.post(
    "",
    response_model=RunbookResponse,
    summary="Generate incident response runbook",
    description="""
    Generate a structured runbook using RAG (Retrieval-Augmented Generation).
    
    Process:
    1. Retrieves similar runbooks from the vector database
    2. Uses retrieved context + LLM to generate specific response steps
    3. Returns steps with risk levels and justifications
    
    Each step includes:
    - step: The specific action to take
    - why: Justification for the step
    - risk: Risk level (low/medium/high)
    """,
    responses={
        200: {
            "description": "Generated runbook",
            "content": {
                "application/json": {
                    "example": {
                        "runbook": [
                            {
                                "step": "Isolate affected host from network",
                                "why": "Prevent lateral movement",
                                "risk": "medium",
                            },
                            {
                                "step": "Capture memory dump for forensics",
                                "why": "Preserve volatile evidence",
                                "risk": "low",
                            },
                        ],
                        "source": "rag",
                    }
                }
            },
        }
    },
)
async def generate_runbook_endpoint(request: RunbookRequest) -> RunbookResponse:
    """
    Generate an incident response runbook.
    """
    try:
        result = await generate_runbook(
            features=request.features,
            label=request.label,
            score=request.score,
            contribs=request.contribs,
        )
        return result
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Runbook generation error: {str(e)}")


@router.post(
    "/from-description",
    response_model=RunbookResponse,
    summary="Generate runbook from text description",
    description="Generate a runbook from a free-text incident description.",
)
async def generate_from_description_endpoint(request: DescriptionRequest) -> RunbookResponse:
    """
    Generate runbook from natural language description.
    """
    try:
        result = await generate_runbook_from_description(
            description=request.description,
            severity=request.severity.upper(),
        )
        return result
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Runbook generation error: {str(e)}")


@router.get(
    "/template/{incident_type}",
    response_model=RunbookResponse,
    summary="Get template runbook",
    description="Get a pre-defined template runbook for common incident types.",
)
async def get_template_endpoint(incident_type: str) -> RunbookResponse:
    """
    Get a template runbook for a specific incident type.
    
    Supported types:
    - brute_force
    - malware
    - data_exfil
    - default
    """
    try:
        result = await get_template_runbook(incident_type)
        return result
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Template retrieval error: {str(e)}")
