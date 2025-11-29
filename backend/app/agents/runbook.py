"""
RAG-enhanced runbook generation using Gemini.

This module retrieves similar runbooks from the vector database
and uses them as context for generating incident-specific response steps.
"""

from typing import Any

from app.services.chains import generate_runbook_chain, get_stub_runbook
from app.config import is_db_available, is_llm_available
from app.models import RunbookResponse
from app.services.rag import get_similar_runbooks


async def generate_runbook(
    features: dict[str, Any],
    label: str,
    score: int,
    contribs: list[tuple[str, int]],
) -> RunbookResponse:
    """
    Generate an incident response runbook using RAG + LLM.

    Process:
    1. Construct a query from incident features
    2. Retrieve similar runbooks from pgvector
    3. Use retrieved runbooks as context for Gemini
    4. Generate and validate new runbook steps

    Args:
        features: Dictionary of incident features
        label: Severity classification (LOW, MEDIUM, HIGH)
        score: Numeric triage score
        contribs: List of (feature_name, points) tuples

    Returns:
        RunbookResponse with generated steps and source

    Example:
        >>> runbook = await generate_runbook(
        ...     features={"failed_logins_last_hour": 50, "source_ip": "10.0.0.1"},
        ...     label="HIGH",
        ...     score=8,
        ...     contribs=[("failed_logins_last_hour", 3)]
        ... )
        >>> for step in runbook.runbook:
        ...     print(f"[{step.risk}] {step.step}")
    """
    # Build query text from incident details
    query_text = build_retrieval_query(features, label, contribs)

    # Retrieve similar runbooks (if database is available)
    similar_runbooks = []
    if is_db_available():
        try:
            similar_runbooks = await get_similar_runbooks(query_text, k=5)
        except Exception as e:
            print(f"Runbook retrieval failed: {e}")

    # Generate runbook using LLM chain
    runbook = await generate_runbook_chain(
        features=features,
        label=label,
        score=score,
        contribs=contribs,
        similar_runbooks=similar_runbooks,
    )

    # Update source based on how it was generated
    if similar_runbooks:
        runbook = RunbookResponse(
            runbook=runbook.runbook,
            source="rag" if is_llm_available() else "rag_stub",
        )
    else:
        runbook = RunbookResponse(
            runbook=runbook.runbook,
            source="llm" if is_llm_available() else "stub",
        )

    return runbook


def build_retrieval_query(
    features: dict[str, Any],
    label: str,
    contribs: list[tuple[str, int]],
) -> str:
    """
    Build a semantic search query from incident details.

    Constructs a natural language query that will be embedded
    and used for similarity search.

    Args:
        features: Incident features
        label: Severity label
        contribs: Contributing factors

    Returns:
        Query string for embedding
    """
    # Start with severity and main indicators
    indicators = [feat for feat, _ in contribs[:3]]
    indicator_text = ", ".join(indicators) if indicators else "general anomaly"

    query_parts = [
        f"Security incident response runbook for {label} severity incident",
        f"Key indicators: {indicator_text}",
    ]

    # Add relevant feature context
    if features.get("suspicious_file_activity"):
        query_parts.append("File system anomaly response")
    if features.get("failed_logins_last_hour", 0) > 10:
        query_parts.append("Brute force attack mitigation")
    if features.get("rare_outgoing_connection"):
        query_parts.append("Command and control traffic investigation")
    if features.get("process_spawn_count", 0) > 50:
        query_parts.append("Malware process activity response")
    if features.get("known_malware_hash"):
        query_parts.append("Known malware remediation")
    if features.get("privilege_escalation_attempt"):
        query_parts.append("Privilege escalation response")

    return ". ".join(query_parts)


async def generate_runbook_from_description(
    description: str,
    severity: str = "MEDIUM",
) -> RunbookResponse:
    """
    Generate a runbook from a free-text incident description.

    Useful for ad-hoc runbook generation without structured features.

    Args:
        description: Natural language incident description
        severity: Severity level (LOW, MEDIUM, HIGH)

    Returns:
        RunbookResponse with generated steps
    """
    # Create synthetic features from description
    features = {
        "description": description,
        "source": "manual_input",
    }

    # Create synthetic contribs based on severity
    contribs = [("manual_classification", 5 if severity == "HIGH" else 3)]

    return await generate_runbook(
        features=features,
        label=severity,
        score=5 if severity == "HIGH" else 3,
        contribs=contribs,
    )


async def get_template_runbook(
    incident_type: str,
) -> RunbookResponse:
    """
    Get a pre-defined template runbook for common incident types.

    Args:
        incident_type: Type of incident (e.g., "brute_force", "malware", "data_exfil")

    Returns:
        Template RunbookResponse
    """
    from app.models import RunbookStep

    templates = {
        "brute_force": [
            RunbookStep(
                step="Review authentication logs for affected accounts",
                why="Identify scope and success of attack attempts",
                risk="low",
            ),
            RunbookStep(
                step="Block source IP addresses at perimeter firewall",
                why="Prevent ongoing attack attempts",
                risk="medium",
            ),
            RunbookStep(
                step="Force password reset for targeted accounts",
                why="Ensure compromised credentials cannot be used",
                risk="low",
            ),
            RunbookStep(
                step="Enable account lockout policies if not present",
                why="Prevent future brute force attacks",
                risk="medium",
            ),
        ],
        "malware": [
            RunbookStep(
                step="Isolate affected endpoint from network",
                why="Prevent lateral movement and C2 communication",
                risk="medium",
            ),
            RunbookStep(
                step="Collect forensic artifacts (memory, disk image)",
                why="Preserve evidence for investigation",
                risk="low",
            ),
            RunbookStep(
                step="Run full antivirus scan on isolated system",
                why="Identify all malicious files",
                risk="low",
            ),
            RunbookStep(
                step="Check for persistence mechanisms",
                why="Ensure malware cannot survive remediation",
                risk="low",
            ),
            RunbookStep(
                step="Reimage system from known good backup",
                why="Ensure complete remediation",
                risk="high",
            ),
        ],
        "data_exfil": [
            RunbookStep(
                step="Block outbound connections to identified destinations",
                why="Stop ongoing data exfiltration",
                risk="medium",
            ),
            RunbookStep(
                step="Identify scope of accessed/exfiltrated data",
                why="Determine breach impact and notification requirements",
                risk="low",
            ),
            RunbookStep(
                step="Review DLP logs for additional exfiltration attempts",
                why="Identify full scope of incident",
                risk="low",
            ),
            RunbookStep(
                step="Revoke access for compromised credentials",
                why="Prevent further unauthorized access",
                risk="low",
            ),
        ],
        "default": [
            RunbookStep(
                step="Document incident details and timeline",
                why="Maintain comprehensive incident record",
                risk="low",
            ),
            RunbookStep(
                step="Assess impact and scope of incident",
                why="Determine appropriate response level",
                risk="low",
            ),
            RunbookStep(
                step="Implement containment measures as needed",
                why="Limit potential damage",
                risk="medium",
            ),
        ],
    }

    steps = templates.get(incident_type, templates["default"])

    return RunbookResponse(runbook=steps, source="template")


def generate_runbook_sync(
    features: dict[str, Any],
    label: str,
    score: int,
    contribs: list[tuple[str, int]],
) -> RunbookResponse:
    """
    Synchronous version of generate_runbook.

    For use in non-async contexts.
    """
    import asyncio

    return asyncio.run(
        generate_runbook(features, label, score, contribs)
    )
