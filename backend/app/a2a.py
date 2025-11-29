"""
Agent-to-Agent (A2A) orchestrator for incident response flow.

This module implements the main orchestration logic that coordinates
multiple agents (triage, explain, runbook, policy, simulate) using
the A2A protocol for inter-agent communication.

Flow:
1. Receive incident → Triage agent scores it
2. Parallel: Explain agent + Runbook agent generate outputs
3. Policy agent sanitizes runbook
4. Simulator agent previews execution
5. Return complete timeline
"""

import asyncio
from datetime import datetime
from typing import Any, Optional
from uuid import uuid4

from app.models import (
    A2AMessage,
    FlowResponse,
    IncidentRequest,
    RunbookResponse,
    TimelineEntry,
    TriageResult,
)
from app.observability import get_logger, log_a2a_message, log_event, set_trace_id


logger = get_logger("a2a")


# =============================================================================
# A2A Message Helpers
# =============================================================================


def create_a2a_message(
    from_agent: str,
    to_agent: str,
    msg_type: str,
    payload: dict[str, Any],
    trace_id: str,
) -> A2AMessage:
    """
    Create a new A2A protocol message.

    Args:
        from_agent: Sending agent name
        to_agent: Receiving agent name
        msg_type: Message type (request, response, event, error)
        payload: Message payload
        trace_id: Correlation ID for the flow

    Returns:
        A2AMessage instance
    """
    message = A2AMessage(
        id=uuid4().hex,
        from_agent=from_agent,
        to_agent=to_agent,
        type=msg_type,
        payload=payload,
        trace_id=trace_id,
    )

    # Log the message
    log_a2a_message(
        message_id=message.id,
        from_agent=from_agent,
        to_agent=to_agent,
        message_type=msg_type,
        payload_summary=str(payload)[:200],
        trace_id=trace_id,
    )

    return message


def create_timeline_entry(
    actor: str,
    event_type: str,
    payload: dict[str, Any],
    trace_id: str,
) -> TimelineEntry:
    """
    Create a timeline entry for the incident flow.

    Args:
        actor: Agent or system that performed the action
        event_type: Category of the event
        payload: Event-specific data
        trace_id: Correlation ID

    Returns:
        TimelineEntry instance
    """
    return TimelineEntry(
        actor=actor,
        type=event_type,
        payload=payload,
        trace_id=trace_id,
        timestamp=datetime.utcnow(),
    )


# =============================================================================
# Agent Wrappers
# =============================================================================


async def call_triage_agent(
    features: dict[str, Any],
    trace_id: str,
) -> tuple[TriageResult, TimelineEntry]:
    """
    Call the triage agent to score an incident.

    Args:
        features: Incident features
        trace_id: Correlation ID

    Returns:
        Tuple of (TriageResult, TimelineEntry)
    """
    from app.triage import score_incident

    # Create request message
    create_a2a_message(
        from_agent="orchestrator",
        to_agent="triage_agent",
        msg_type="request",
        payload={"features": features},
        trace_id=trace_id,
    )

    # Call triage (synchronous)
    label, score, contribs = score_incident(features)

    result = TriageResult(label=label, score=score, contribs=contribs)

    # Create response message
    create_a2a_message(
        from_agent="triage_agent",
        to_agent="orchestrator",
        msg_type="response",
        payload=result.model_dump(),
        trace_id=trace_id,
    )

    # Create timeline entry
    entry = create_timeline_entry(
        actor="triage_agent",
        event_type="triage_complete",
        payload={"label": label, "score": score, "contributing_factors": len(contribs)},
        trace_id=trace_id,
    )

    return result, entry


async def call_explain_agent(
    features: dict[str, Any],
    triage: TriageResult,
    trace_id: str,
) -> tuple[dict[str, Any], TimelineEntry]:
    """
    Call the explain agent to generate incident explanation.

    Args:
        features: Incident features
        triage: Triage result
        trace_id: Correlation ID

    Returns:
        Tuple of (explanation dict, TimelineEntry)
    """
    from app.explain import explain_incident

    # Create request message
    create_a2a_message(
        from_agent="orchestrator",
        to_agent="explain_agent",
        msg_type="request",
        payload={"label": triage.label, "score": triage.score},
        trace_id=trace_id,
    )

    # Call explain agent
    explanation = await explain_incident(
        features=features,
        label=triage.label,
        score=triage.score,
        contribs=triage.contribs,
    )

    # Create response message
    create_a2a_message(
        from_agent="explain_agent",
        to_agent="orchestrator",
        msg_type="response",
        payload={"explanation_length": len(explanation.get("explanation", ""))},
        trace_id=trace_id,
    )

    # Create timeline entry
    entry = create_timeline_entry(
        actor="explain_agent",
        event_type="explanation_generated",
        payload={"reasons_count": len(explanation.get("reasons", []))},
        trace_id=trace_id,
    )

    return explanation, entry


async def call_runbook_agent(
    features: dict[str, Any],
    triage: TriageResult,
    trace_id: str,
) -> tuple[RunbookResponse, TimelineEntry]:
    """
    Call the runbook agent to generate response steps.

    Args:
        features: Incident features
        triage: Triage result
        trace_id: Correlation ID

    Returns:
        Tuple of (RunbookResponse, TimelineEntry)
    """
    from app.runbook import generate_runbook

    # Create request message
    create_a2a_message(
        from_agent="orchestrator",
        to_agent="runbook_agent",
        msg_type="request",
        payload={"label": triage.label, "score": triage.score},
        trace_id=trace_id,
    )

    # Call runbook agent
    runbook = await generate_runbook(
        features=features,
        label=triage.label,
        score=triage.score,
        contribs=triage.contribs,
    )

    # Create response message
    create_a2a_message(
        from_agent="runbook_agent",
        to_agent="orchestrator",
        msg_type="response",
        payload={"steps_count": len(runbook.runbook), "source": runbook.source},
        trace_id=trace_id,
    )

    # Create timeline entry
    entry = create_timeline_entry(
        actor="runbook_agent",
        event_type="runbook_generated",
        payload={"steps": len(runbook.runbook), "source": runbook.source},
        trace_id=trace_id,
    )

    return runbook, entry


async def call_policy_agent(
    runbook: RunbookResponse,
    trace_id: str,
) -> tuple[dict[str, Any], TimelineEntry]:
    """
    Call the policy agent to verify and sanitize runbook.

    Args:
        runbook: Generated runbook
        trace_id: Correlation ID

    Returns:
        Tuple of (policy result dict, TimelineEntry)
    """
    from app.policy import policy_check

    # Create request message
    create_a2a_message(
        from_agent="orchestrator",
        to_agent="policy_agent",
        msg_type="request",
        payload={"steps_count": len(runbook.runbook)},
        trace_id=trace_id,
    )

    # Call policy check (synchronous)
    policy_result = policy_check(runbook)

    # Create response message
    create_a2a_message(
        from_agent="policy_agent",
        to_agent="orchestrator",
        msg_type="response",
        payload={"violations_found": policy_result["violations_found"]},
        trace_id=trace_id,
    )

    # Create timeline entry
    entry = create_timeline_entry(
        actor="policy_agent",
        event_type="policy_check_complete",
        payload={
            "violations_found": policy_result["violations_found"],
            "changes": len(policy_result["changes"]),
        },
        trace_id=trace_id,
    )

    return policy_result, entry


async def call_simulator_agent(
    runbook_dict: dict[str, Any],
    trace_id: str,
) -> tuple[list[dict[str, Any]], list[TimelineEntry]]:
    """
    Call the simulator agent to preview runbook execution.

    Args:
        runbook_dict: Runbook as dictionary
        trace_id: Correlation ID

    Returns:
        Tuple of (simulation events, list of TimelineEntries)
    """
    from app.simulate import simulate_runbook

    # Create request message
    create_a2a_message(
        from_agent="orchestrator",
        to_agent="simulator_agent",
        msg_type="request",
        payload={"steps_count": len(runbook_dict.get("runbook", []))},
        trace_id=trace_id,
    )

    # Call simulator
    simulation_events = await simulate_runbook(runbook_dict, trace_id)

    # Create timeline entries for key simulation events
    entries = []

    # Add start entry
    entries.append(
        create_timeline_entry(
            actor="simulator_agent",
            event_type="simulation_started",
            payload={"total_steps": len(runbook_dict.get("runbook", []))},
            trace_id=trace_id,
        )
    )

    # Add completion entry
    ok_count = sum(1 for e in simulation_events if e.get("outcome") == "simulated_ok")
    warn_count = sum(1 for e in simulation_events if e.get("outcome") == "simulated_warn")

    entries.append(
        create_timeline_entry(
            actor="simulator_agent",
            event_type="simulation_complete",
            payload={"ok_steps": ok_count, "warn_steps": warn_count},
            trace_id=trace_id,
        )
    )

    # Create response message
    create_a2a_message(
        from_agent="simulator_agent",
        to_agent="orchestrator",
        msg_type="response",
        payload={"events_count": len(simulation_events)},
        trace_id=trace_id,
    )

    return simulation_events, entries


# =============================================================================
# Main Orchestration Flow
# =============================================================================


async def orchestrate_flow(
    incident_id: Optional[str],
    features: dict[str, Any],
) -> list[TimelineEntry]:
    """
    Orchestrate the complete incident response flow.

    This is the main entry point for processing an incident through
    all agents in the system.

    Flow:
    1. Triage agent scores the incident (sync)
    2. Explain + Runbook agents run in parallel (async)
    3. Policy agent sanitizes the runbook (sync)
    4. Simulator agent previews execution (async)

    Args:
        incident_id: Optional incident identifier
        features: Dictionary of incident features

    Returns:
        List of TimelineEntry objects documenting the flow

    Example:
        >>> entries = await orchestrate_flow(
        ...     incident_id="INC-001",
        ...     features={"failed_logins_last_hour": 50}
        ... )
        >>> for entry in entries:
        ...     print(f"{entry.actor}: {entry.type}")
    """
    # Generate trace ID for the entire flow
    trace_id = uuid4().hex
    set_trace_id(trace_id)

    timeline: list[TimelineEntry] = []

    # Log flow start
    log_event(
        "flow_started",
        {"incident_id": incident_id, "trace_id": trace_id},
        trace_id=trace_id,
    )

    # Add flow start entry
    timeline.append(
        create_timeline_entry(
            actor="orchestrator",
            event_type="flow_started",
            payload={"incident_id": incident_id},
            trace_id=trace_id,
        )
    )

    try:
        # Step 1: Triage (synchronous)
        triage_result, triage_entry = await call_triage_agent(features, trace_id)
        timeline.append(triage_entry)

        # Step 2: Parallel execution of explain and runbook
        explain_task = call_explain_agent(features, triage_result, trace_id)
        runbook_task = call_runbook_agent(features, triage_result, trace_id)

        (explanation, explain_entry), (runbook, runbook_entry) = await asyncio.gather(
            explain_task, runbook_task
        )

        timeline.append(explain_entry)
        timeline.append(runbook_entry)

        # Step 3: Policy check
        policy_result, policy_entry = await call_policy_agent(runbook, trace_id)
        timeline.append(policy_entry)

        # Convert sanitized runbook for simulation
        safe_runbook_dict = {
            "runbook": [
                {"step": s.step, "why": s.why, "risk": s.risk}
                for s in policy_result["runbook"]
            ],
            "source": runbook.source,
        }

        # Step 4: Simulation
        simulation_events, sim_entries = await call_simulator_agent(
            safe_runbook_dict, trace_id
        )
        timeline.extend(sim_entries)

        # Add flow completion entry
        timeline.append(
            create_timeline_entry(
                actor="orchestrator",
                event_type="flow_completed",
                payload={
                    "triage_label": triage_result.label,
                    "runbook_steps": len(policy_result["runbook"]),
                    "policy_changes": len(policy_result["changes"]),
                },
                trace_id=trace_id,
            )
        )

        log_event(
            "flow_completed",
            {"incident_id": incident_id, "label": triage_result.label},
            trace_id=trace_id,
        )

    except Exception as e:
        logger.exception(f"Flow error: {e}")

        # Add error entry
        timeline.append(
            create_timeline_entry(
                actor="orchestrator",
                event_type="flow_error",
                payload={"error": str(e)},
                trace_id=trace_id,
            )
        )

        log_event("flow_error", {"error": str(e)}, trace_id=trace_id)

    return timeline


async def orchestrate_flow_full(
    incident: IncidentRequest,
) -> FlowResponse:
    """
    Orchestrate flow and return complete FlowResponse.

    Enhanced version that returns all generated artifacts.

    Args:
        incident: IncidentRequest with features

    Returns:
        FlowResponse with triage, explanation, runbook, and timeline
    """
    trace_id = uuid4().hex
    set_trace_id(trace_id)

    from app.explain import explain_incident
    from app.policy import policy_check
    from app.runbook import generate_runbook
    from app.triage import score_incident

    # Triage
    label, score, contribs = score_incident(incident.features)
    triage = TriageResult(label=label, score=score, contribs=contribs)

    # Parallel explain + runbook
    explain_task = explain_incident(
        features=incident.features,
        label=label,
        score=score,
        contribs=contribs,
    )
    runbook_task = generate_runbook(
        features=incident.features,
        label=label,
        score=score,
        contribs=contribs,
    )

    explanation, runbook = await asyncio.gather(explain_task, runbook_task)

    # Policy check
    policy_result = policy_check(runbook)

    # Build timeline
    timeline = await orchestrate_flow(incident.incident_id, incident.features)

    return FlowResponse(
        incident_id=incident.incident_id or f"INC-{uuid4().hex[:8].upper()}",
        triage=triage,
        explanation=explanation,
        runbook=RunbookResponse(
            runbook=policy_result["runbook"],
            source=runbook.source,
        ),
        policy_changes=policy_result["changes"],
        timeline=timeline,
        trace_id=trace_id,
    )
