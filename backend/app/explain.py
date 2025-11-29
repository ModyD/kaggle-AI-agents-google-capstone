"""
LangChain + Gemini wrapper for incident explanation.

This module generates natural language explanations for triage
decisions using LLM-powered analysis.
"""

from typing import Any

from app.chains import generate_explanation_chain
from app.config import is_llm_available


async def explain_incident(
    features: dict[str, Any],
    label: str,
    score: int,
    contribs: list[tuple[str, int]],
) -> dict[str, Any]:
    """
    Generate an LLM-powered explanation of triage results.

    Uses LangChain with Vertex Gemini to create human-readable
    explanations of why an incident was classified at a particular
    severity level.

    Args:
        features: Dictionary of incident features
        label: Severity classification (LOW, MEDIUM, HIGH)
        score: Numeric triage score
        contribs: List of (feature_name, points) tuples

    Returns:
        Dictionary with:
            - explanation: str - Natural language explanation
            - reasons: list[str] - Specific reasons (2-3 items)

    Example:
        >>> result = await explain_incident(
        ...     features={"failed_logins_last_hour": 50},
        ...     label="HIGH",
        ...     score=8,
        ...     contribs=[("failed_logins_last_hour", 3)]
        ... )
        >>> print(result['explanation'])
        "This incident was classified as HIGH severity..."
    """
    return await generate_explanation_chain(
        features=features,
        label=label,
        score=score,
        contribs=contribs,
    )


async def explain_triage_decision(
    triage_result: dict[str, Any],
    features: dict[str, Any],
) -> dict[str, Any]:
    """
    Convenience wrapper that accepts triage result dict.

    Args:
        triage_result: Result from triage.triage_incident()
        features: Original incident features

    Returns:
        Explanation dictionary
    """
    return await explain_incident(
        features=features,
        label=triage_result.get("label", "MEDIUM"),
        score=triage_result.get("score", 0),
        contribs=triage_result.get("contribs", []),
    )


def explain_incident_sync(
    features: dict[str, Any],
    label: str,
    score: int,
    contribs: list[tuple[str, int]],
) -> dict[str, Any]:
    """
    Synchronous version of explain_incident.

    For use in non-async contexts. Runs the async function
    in an event loop.

    Args:
        features: Incident features
        label: Severity label
        score: Triage score
        contribs: Contributing factors

    Returns:
        Explanation dictionary
    """
    import asyncio

    return asyncio.run(
        explain_incident(features, label, score, contribs)
    )
