"""
Runbook simulation engine.

This module simulates the execution of runbook steps, providing
a preview of what would happen without actually executing commands.
"""

import asyncio
import random
from datetime import datetime
from typing import Any

from app.models import RunbookStep


# =============================================================================
# Simulation Configuration
# =============================================================================

# Delay ranges for different risk levels (seconds)
SIMULATION_DELAYS = {
    "low": (0.1, 0.3),
    "medium": (0.2, 0.5),
    "high": (0.3, 0.8),
}

# Probability of warnings based on risk level
WARNING_PROBABILITIES = {
    "low": 0.05,
    "medium": 0.15,
    "high": 0.30,
}


# =============================================================================
# Simulation Functions
# =============================================================================


def determine_outcome(risk: str) -> str:
    """
    Determine simulation outcome based on risk level.

    Higher risk steps have higher probability of warnings.

    Args:
        risk: Risk level (low, medium, high)

    Returns:
        Outcome string: 'simulated_ok' or 'simulated_warn'
    """
    warn_prob = WARNING_PROBABILITIES.get(risk, 0.1)

    if random.random() < warn_prob:
        return "simulated_warn"
    return "simulated_ok"


def get_simulation_message(step: str, outcome: str) -> str:
    """
    Generate a human-readable simulation message.

    Args:
        step: The step being simulated
        outcome: The simulation outcome

    Returns:
        Descriptive message about the simulation
    """
    if outcome == "simulated_ok":
        return f"Step would execute successfully: {step[:50]}..."
    else:
        return f"Step may require attention: {step[:50]}... (review recommended)"


async def simulate_step(
    step: RunbookStep,
    step_index: int,
    trace_id: str,
) -> list[dict[str, Any]]:
    """
    Simulate execution of a single runbook step.

    Creates start and end events with appropriate delays.

    Args:
        step: The RunbookStep to simulate
        step_index: Index of the step in the runbook
        trace_id: Correlation ID for the simulation

    Returns:
        List containing start and end event dictionaries
    """
    events = []

    # Get delay range for risk level
    delay_range = SIMULATION_DELAYS.get(step.risk, (0.1, 0.3))
    delay = random.uniform(*delay_range)

    # Start event
    start_event = {
        "type": "simulation_step_start",
        "step_index": step_index,
        "step": step.step,
        "risk": step.risk,
        "timestamp": datetime.utcnow().isoformat(),
        "trace_id": trace_id,
    }
    events.append(start_event)

    # Simulate execution time
    await asyncio.sleep(delay)

    # Determine outcome
    outcome = determine_outcome(step.risk)
    message = get_simulation_message(step.step, outcome)

    # End event
    end_event = {
        "type": "simulation_step_end",
        "step_index": step_index,
        "step": step.step,
        "outcome": outcome,
        "message": message,
        "duration_ms": int(delay * 1000),
        "timestamp": datetime.utcnow().isoformat(),
        "trace_id": trace_id,
    }
    events.append(end_event)

    return events


async def simulate_runbook(
    runbook: dict[str, Any],
    trace_id: str | None = None,
) -> list[dict[str, Any]]:
    """
    Simulate execution of an entire runbook.

    Iterates through all steps, emitting start and end events
    for each step with appropriate delays based on risk level.

    Args:
        runbook: Dictionary containing 'runbook' key with list of step dicts
        trace_id: Optional correlation ID (generated if not provided)

    Returns:
        Ordered list of simulation events suitable for timeline entries

    Example:
        >>> runbook = {
        ...     "runbook": [
        ...         {"step": "Check logs", "why": "Initial investigation", "risk": "low"},
        ...         {"step": "Isolate host", "why": "Prevent spread", "risk": "medium"}
        ...     ],
        ...     "source": "rag"
        ... }
        >>> events = await simulate_runbook(runbook)
        >>> len(events)  # 2 steps * 2 events each = 4
        4
    """
    if trace_id is None:
        from uuid import uuid4
        trace_id = uuid4().hex

    events: list[dict[str, Any]] = []
    steps = runbook.get("runbook", [])

    # Simulation start event
    events.append(
        {
            "type": "simulation_start",
            "total_steps": len(steps),
            "timestamp": datetime.utcnow().isoformat(),
            "trace_id": trace_id,
        }
    )

    # Process each step
    for i, step_dict in enumerate(steps):
        step = RunbookStep(
            step=step_dict.get("step", "Unknown step"),
            why=step_dict.get("why", ""),
            risk=step_dict.get("risk", "medium"),
        )

        step_events = await simulate_step(step, i, trace_id)
        events.extend(step_events)

    # Calculate summary statistics
    ok_count = sum(1 for e in events if e.get("outcome") == "simulated_ok")
    warn_count = sum(1 for e in events if e.get("outcome") == "simulated_warn")

    # Simulation end event
    events.append(
        {
            "type": "simulation_end",
            "total_steps": len(steps),
            "successful_steps": ok_count,
            "warning_steps": warn_count,
            "timestamp": datetime.utcnow().isoformat(),
            "trace_id": trace_id,
        }
    )

    return events


async def simulate_runbook_steps(
    steps: list[RunbookStep],
    trace_id: str | None = None,
) -> list[dict[str, Any]]:
    """
    Simulate execution from a list of RunbookStep objects.

    Convenience wrapper that accepts Pydantic models directly.

    Args:
        steps: List of RunbookStep objects
        trace_id: Optional correlation ID

    Returns:
        Ordered list of simulation events
    """
    runbook_dict = {
        "runbook": [
            {"step": s.step, "why": s.why, "risk": s.risk} for s in steps
        ]
    }

    return await simulate_runbook(runbook_dict, trace_id)


# =============================================================================
# Dry Run Mode
# =============================================================================


def dry_run_step(step: RunbookStep) -> dict[str, Any]:
    """
    Perform a synchronous dry run check on a step.

    This is a lighter-weight check that doesn't simulate delays.

    Args:
        step: The RunbookStep to check

    Returns:
        Dictionary with dry run analysis
    """
    # Check for high-risk indicators
    high_risk_keywords = [
        "delete",
        "remove",
        "terminate",
        "shutdown",
        "disable",
        "drop",
        "reset",
    ]

    has_risk_keywords = any(kw in step.step.lower() for kw in high_risk_keywords)

    return {
        "step": step.step,
        "risk": step.risk,
        "has_risk_keywords": has_risk_keywords,
        "requires_approval": step.risk == "high" or has_risk_keywords,
        "estimated_impact": (
            "high" if (step.risk == "high" or has_risk_keywords) else "normal"
        ),
    }


def dry_run_runbook(steps: list[RunbookStep]) -> dict[str, Any]:
    """
    Perform dry run analysis on entire runbook.

    Args:
        steps: List of RunbookStep objects

    Returns:
        Summary of dry run analysis
    """
    analyses = [dry_run_step(step) for step in steps]

    return {
        "steps_analyzed": len(analyses),
        "steps_requiring_approval": sum(
            1 for a in analyses if a["requires_approval"]
        ),
        "high_impact_steps": sum(
            1 for a in analyses if a["estimated_impact"] == "high"
        ),
        "analysis": analyses,
    }
