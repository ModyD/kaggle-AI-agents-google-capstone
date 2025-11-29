"""
Pydantic v2 models for the Security Incident Triage & Runbook Agent.

These models define the data structures for:
- Incident requests and triage results
- Runbook steps and responses
- Agent-to-Agent (A2A) protocol messages
- Timeline entries for observability
"""

from datetime import datetime
from typing import Any, Literal, Optional
from uuid import uuid4

from pydantic import BaseModel, Field, field_validator


# =============================================================================
# Incident & Triage Models
# =============================================================================


class IncidentRequest(BaseModel):
    """
    Request payload for incident triage.

    Attributes:
        incident_id: Optional unique identifier for the incident.
                    If not provided, one will be generated.
        features: Dictionary of incident features for triage scoring.
                 Expected keys include: failed_logins_last_hour,
                 process_spawn_count, suspicious_file_activity,
                 rare_outgoing_connection, etc.
    """

    incident_id: Optional[str] = Field(
        default=None,
        description="Unique identifier for the incident. Auto-generated if not provided.",
        examples=["INC-2025-001234"],
    )
    features: dict[str, Any] = Field(
        ...,
        description="Dictionary of incident features for triage analysis.",
        examples=[
            {
                "failed_logins_last_hour": 15,
                "process_spawn_count": 50,
                "suspicious_file_activity": True,
                "rare_outgoing_connection": True,
                "source_ip": "192.168.1.100",
                "affected_user": "admin",
            }
        ],
    )

    @field_validator("incident_id", mode="before")
    @classmethod
    def generate_id_if_missing(cls, v: Optional[str]) -> str:
        """Generate a unique ID if not provided."""
        if v is None or v == "":
            return f"INC-{datetime.utcnow().strftime('%Y%m%d')}-{uuid4().hex[:8].upper()}"
        return v


class TriageContribution(BaseModel):
    """A single feature contribution to the triage score."""

    feature: str = Field(..., description="Name of the contributing feature")
    points: int = Field(..., description="Points contributed to the total score")


class TriageResult(BaseModel):
    """
    Result of incident triage scoring.

    Attributes:
        label: Severity classification (LOW, MEDIUM, HIGH)
        score: Numeric score from the rule engine
        contribs: List of feature contributions to the score
    """

    label: Literal["LOW", "MEDIUM", "HIGH"] = Field(
        ...,
        description="Severity classification based on score thresholds",
        examples=["HIGH"],
    )
    score: int = Field(
        ...,
        ge=0,
        description="Total triage score from weighted rules",
        examples=[8],
    )
    contribs: list[tuple[str, int]] = Field(
        ...,
        description="List of (feature_name, points) tuples showing score breakdown",
        examples=[[("failed_logins_last_hour", 3), ("process_spawn_count", 2)]],
    )

    @field_validator("contribs", mode="before")
    @classmethod
    def validate_contribs(cls, v):
        """Ensure contribs is a list of tuples."""
        if isinstance(v, list):
            return [tuple(item) if isinstance(item, (list, tuple)) else item for item in v]
        return v


class TriageExplanation(BaseModel):
    """
    LLM-generated explanation of triage results.

    Used for validating Gemini's JSON output.
    """

    explanation: str = Field(
        ...,
        description="Natural language explanation of the triage decision",
        min_length=10,
    )
    reasons: list[str] = Field(
        ...,
        description="List of specific reasons for the classification",
        min_length=1,
        max_length=5,
    )


# =============================================================================
# Runbook Models
# =============================================================================


class RunbookStep(BaseModel):
    """
    A single step in a security response runbook.

    Attributes:
        step: The action to be performed
        why: Explanation of why this step is necessary
        risk: Risk level of performing this step
    """

    step: str = Field(
        ...,
        description="The action or command to execute",
        min_length=5,
        examples=["Isolate affected host from network"],
    )
    why: str = Field(
        ...,
        description="Justification for this step",
        min_length=5,
        examples=["Prevents lateral movement while investigation proceeds"],
    )
    risk: Literal["low", "medium", "high"] = Field(
        ...,
        description="Risk level of executing this step",
        examples=["medium"],
    )


class RunbookResponse(BaseModel):
    """
    Complete runbook response with all steps.

    Attributes:
        runbook: Ordered list of runbook steps
        source: Origin of the runbook (e.g., 'rag', 'template', 'llm')
    """

    runbook: list[RunbookStep] = Field(
        ...,
        description="Ordered list of response steps",
        min_length=1,
    )
    source: str = Field(
        ...,
        description="Source of the runbook generation",
        examples=["rag", "template", "llm"],
    )


# =============================================================================
# A2A Protocol Models
# =============================================================================


class A2AMessage(BaseModel):
    """
    Agent-to-Agent protocol message.

    Follows a standardized format for inter-agent communication.

    Attributes:
        id: Unique message identifier
        from_agent: Name of the sending agent
        to_agent: Name of the receiving agent
        type: Message type (request, response, event)
        timestamp: ISO 8601 timestamp of message creation
        payload: Message-specific data
        trace_id: Correlation ID for distributed tracing
    """

    id: str = Field(
        default_factory=lambda: uuid4().hex,
        description="Unique message identifier",
    )
    from_agent: str = Field(
        ...,
        description="Name of the sending agent",
        examples=["triage_agent", "runbook_agent", "orchestrator"],
    )
    to_agent: str = Field(
        ...,
        description="Name of the receiving agent",
        examples=["explain_agent", "policy_agent", "simulator"],
    )
    type: Literal["request", "response", "event", "error"] = Field(
        ...,
        description="Type of A2A message",
    )
    timestamp: datetime = Field(
        default_factory=datetime.utcnow,
        description="Message creation timestamp (ISO 8601)",
    )
    payload: dict[str, Any] = Field(
        default_factory=dict,
        description="Message-specific payload data",
    )
    trace_id: str = Field(
        default_factory=lambda: uuid4().hex,
        description="Distributed tracing correlation ID",
    )

    @field_validator("timestamp", mode="before")
    @classmethod
    def parse_timestamp(cls, v):
        """Parse ISO datetime strings."""
        if isinstance(v, str):
            return datetime.fromisoformat(v.replace("Z", "+00:00"))
        return v


class TimelineEntry(BaseModel):
    """
    An entry in the incident response timeline.

    Used for observability and audit trail.

    Attributes:
        actor: The agent or system that performed the action
        type: Category of the timeline event
        payload: Event-specific data
        trace_id: Correlation ID for the incident flow
        timestamp: When the event occurred
    """

    actor: str = Field(
        ...,
        description="Agent or system that performed the action",
        examples=["triage_agent", "policy_agent", "simulator"],
    )
    type: str = Field(
        ...,
        description="Event type category",
        examples=[
            "triage_complete",
            "runbook_generated",
            "policy_check",
            "simulation_start",
        ],
    )
    payload: dict[str, Any] = Field(
        default_factory=dict,
        description="Event-specific data",
    )
    trace_id: str = Field(
        ...,
        description="Correlation ID linking related events",
    )
    timestamp: datetime = Field(
        default_factory=datetime.utcnow,
        description="Event timestamp (ISO 8601)",
    )

    @field_validator("timestamp", mode="before")
    @classmethod
    def parse_timestamp(cls, v):
        """Parse ISO datetime strings."""
        if isinstance(v, str):
            return datetime.fromisoformat(v.replace("Z", "+00:00"))
        return v


# =============================================================================
# Flow & Orchestration Models
# =============================================================================


class FlowRequest(BaseModel):
    """Request to execute the full incident response flow."""

    incident: IncidentRequest = Field(
        ...,
        description="The incident to process through the flow",
    )


class FlowResponse(BaseModel):
    """Complete response from the incident flow."""

    incident_id: str = Field(..., description="Incident identifier")
    triage: TriageResult = Field(..., description="Triage results")
    explanation: Optional[dict[str, Any]] = Field(
        None, description="LLM explanation of triage"
    )
    runbook: Optional[RunbookResponse] = Field(
        None, description="Generated runbook"
    )
    policy_changes: list[dict[str, str]] = Field(
        default_factory=list, description="Policy modifications made"
    )
    timeline: list[TimelineEntry] = Field(
        default_factory=list, description="Complete event timeline"
    )
    trace_id: str = Field(..., description="Flow trace ID")


# =============================================================================
# Health & Status Models
# =============================================================================


class HealthResponse(BaseModel):
    """Health check response."""

    status: Literal["healthy", "degraded", "unhealthy"] = Field(
        ..., description="Overall health status"
    )
    version: str = Field(..., description="Application version")
    services: dict[str, bool] = Field(
        default_factory=dict,
        description="Status of dependent services",
    )
