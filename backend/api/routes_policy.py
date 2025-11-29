"""
Policy API routes.

Provides endpoints for safety policy verification.
"""

from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from app.models import RunbookResponse, RunbookStep
from app.policy import policy_check, policy_is_safe, get_policy_rules, validate_custom_runbook

router = APIRouter(prefix="/policy", tags=["Agent Tools"])


class PolicyCheckRequest(BaseModel):
    """Request payload for policy check."""

    runbook: list[dict[str, Any]] = Field(
        ...,
        description="List of runbook steps to check",
        examples=[
            [
                {"step": "rm -rf /tmp/malware", "why": "Clean up", "risk": "high"},
                {"step": "Review logs", "why": "Investigation", "risk": "low"},
            ]
        ],
    )
    source: str = Field(
        default="api",
        description="Source of the runbook",
    )


class SafetyCheckRequest(BaseModel):
    """Request for quick safety check on text."""

    text: str = Field(
        ...,
        description="Text to check for safety",
        examples=["rm -rf /important/data"],
    )


class PolicyCheckResponse(BaseModel):
    """Response from policy check."""

    runbook: list[dict[str, Any]] = Field(
        ...,
        description="Sanitized runbook steps",
    )
    changes: list[dict[str, str]] = Field(
        ...,
        description="List of changes made",
    )
    violations_found: int = Field(
        ...,
        description="Number of policy violations found",
    )


@router.post(
    "/check",
    response_model=PolicyCheckResponse,
    summary="Check and sanitize runbook for policy violations",
    description="""
    Scan runbook steps for dangerous or forbidden commands and
    rewrite them to safe investigative alternatives.
    
    Detected patterns include:
    - Destructive commands (rm -rf, mkfs, dd)
    - System control (shutdown, reboot)
    - Dangerous network operations (curl to external URLs)
    - Database destruction (DROP TABLE)
    
    Returns the sanitized runbook and a list of changes made.
    """,
    responses={
        200: {
            "description": "Policy check result",
            "content": {
                "application/json": {
                    "example": {
                        "runbook": [
                            {
                                "step": "[POLICY REWRITTEN] Review files for deletion: ls -la",
                                "why": "Original action blocked by safety policy. Reason: contains 'rm -rf'.",
                                "risk": "low",
                            }
                        ],
                        "changes": [
                            {
                                "from": "rm -rf /tmp/malware",
                                "to": "[POLICY REWRITTEN] Review files for deletion: ls -la",
                                "reason": "Matched forbidden pattern: rm -rf",
                            }
                        ],
                        "violations_found": 1,
                    }
                }
            },
        }
    },
)
async def policy_check_endpoint(request: PolicyCheckRequest) -> PolicyCheckResponse:
    """
    Check runbook against safety policies.
    """
    try:
        # Convert to RunbookResponse model
        steps = [
            RunbookStep(
                step=s.get("step", ""),
                why=s.get("why", ""),
                risk=s.get("risk", "medium"),
            )
            for s in request.runbook
        ]
        runbook = RunbookResponse(runbook=steps, source=request.source)

        result = policy_check(runbook)

        return PolicyCheckResponse(
            runbook=[
                {"step": s.step, "why": s.why, "risk": s.risk}
                for s in result["runbook"]
            ],
            changes=result["changes"],
            violations_found=result["violations_found"],
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Policy check error: {str(e)}")


@router.post(
    "/is-safe",
    summary="Quick safety check on text",
    description="Check if a text string contains any forbidden patterns.",
)
async def is_safe_endpoint(request: SafetyCheckRequest) -> dict[str, Any]:
    """
    Quick check if text is safe.
    """
    is_safe = policy_is_safe(request.text)
    return {
        "text": request.text,
        "is_safe": is_safe,
        "message": "Text passes safety check" if is_safe else "Text contains forbidden patterns",
    }


@router.get(
    "/rules",
    summary="Get current policy rules",
    description="Returns all active policy rules for documentation.",
)
async def get_rules_endpoint() -> dict[str, Any]:
    """
    Get current policy rules.
    """
    return get_policy_rules()


@router.post(
    "/validate-steps",
    summary="Validate custom runbook steps",
    description="Validate a list of step strings and get suggestions.",
)
async def validate_steps_endpoint(steps: list[str]) -> list[dict[str, Any]]:
    """
    Validate custom runbook steps.
    """
    return validate_custom_runbook(steps)
