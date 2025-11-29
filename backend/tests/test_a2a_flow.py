"""
Tests for A2A orchestration flow.
"""

import pytest
from typing import Any

from app.models import IncidentRequest, TimelineEntry


# =============================================================================
# Fixtures
# =============================================================================


@pytest.fixture
def sample_incident() -> IncidentRequest:
    """Sample incident for testing."""
    return IncidentRequest(
        incident_id="TEST-001",
        features={
            "failed_logins_last_hour": 25,
            "process_spawn_count": 50,
            "suspicious_file_activity": True,
            "rare_outgoing_connection": True,
        },
    )


@pytest.fixture
def low_severity_incident() -> IncidentRequest:
    """Low severity incident for testing."""
    return IncidentRequest(
        incident_id="TEST-002",
        features={
            "failed_logins_last_hour": 1,
            "process_spawn_count": 5,
        },
    )


# =============================================================================
# A2A Flow Tests
# =============================================================================


class TestOrchestration:
    """Tests for the A2A orchestration flow."""

    @pytest.mark.asyncio
    async def test_orchestrate_flow_returns_timeline(self, sample_incident):
        """Test that orchestration returns a timeline."""
        from app.orchestration.a2a import orchestrate_flow

        timeline = await orchestrate_flow(
            incident_id=sample_incident.incident_id,
            features=sample_incident.features,
        )

        assert isinstance(timeline, list)
        assert len(timeline) > 0
        assert all(isinstance(entry, TimelineEntry) for entry in timeline)

    @pytest.mark.asyncio
    async def test_orchestrate_flow_has_required_events(self, sample_incident):
        """Test that timeline contains required event types."""
        from app.orchestration.a2a import orchestrate_flow

        timeline = await orchestrate_flow(
            incident_id=sample_incident.incident_id,
            features=sample_incident.features,
        )

        event_types = [entry.type for entry in timeline]

        # Should have these key events
        assert "flow_started" in event_types
        assert "triage_complete" in event_types
        assert "flow_completed" in event_types or "flow_error" in event_types

    @pytest.mark.asyncio
    async def test_orchestrate_flow_trace_id_consistent(self, sample_incident):
        """Test that all timeline entries have the same trace ID."""
        from app.orchestration.a2a import orchestrate_flow

        timeline = await orchestrate_flow(
            incident_id=sample_incident.incident_id,
            features=sample_incident.features,
        )

        trace_ids = set(entry.trace_id for entry in timeline)
        assert len(trace_ids) == 1  # All should have same trace ID

    @pytest.mark.asyncio
    async def test_orchestrate_flow_actors(self, sample_incident):
        """Test that timeline includes all expected actors."""
        from app.orchestration.a2a import orchestrate_flow

        timeline = await orchestrate_flow(
            incident_id=sample_incident.incident_id,
            features=sample_incident.features,
        )

        actors = set(entry.actor for entry in timeline)

        # Should include orchestrator and at least triage agent
        assert "orchestrator" in actors
        assert "triage_agent" in actors

    @pytest.mark.asyncio
    async def test_orchestrate_flow_timestamps_ordered(self, sample_incident):
        """Test that timeline entries are in chronological order."""
        from app.orchestration.a2a import orchestrate_flow

        timeline = await orchestrate_flow(
            incident_id=sample_incident.incident_id,
            features=sample_incident.features,
        )

        timestamps = [entry.timestamp for entry in timeline]

        # Each timestamp should be >= previous
        for i in range(1, len(timestamps)):
            assert timestamps[i] >= timestamps[i - 1]


class TestA2AMessages:
    """Tests for A2A message creation."""

    def test_create_a2a_message(self):
        """Test A2A message creation."""
        from app.orchestration.a2a import create_a2a_message

        message = create_a2a_message(
            from_agent="triage_agent",
            to_agent="orchestrator",
            msg_type="response",
            payload={"label": "HIGH"},
            trace_id="test-trace",
        )

        assert message.from_agent == "triage_agent"
        assert message.to_agent == "orchestrator"
        assert message.type == "response"
        assert message.payload == {"label": "HIGH"}
        assert message.trace_id == "test-trace"

    def test_create_timeline_entry(self):
        """Test timeline entry creation."""
        from app.orchestration.a2a import create_timeline_entry

        entry = create_timeline_entry(
            actor="policy_agent",
            event_type="policy_check_complete",
            payload={"violations": 0},
            trace_id="test-trace",
        )

        assert entry.actor == "policy_agent"
        assert entry.type == "policy_check_complete"
        assert entry.payload == {"violations": 0}
        assert entry.trace_id == "test-trace"


class TestFullFlowResponse:
    """Tests for full flow response."""

    @pytest.mark.asyncio
    async def test_full_flow_returns_all_artifacts(self, sample_incident):
        """Test that full flow returns all expected artifacts."""
        from app.orchestration.a2a import orchestrate_flow_full
        from app.models import FlowRequest

        request = FlowRequest(incident=sample_incident)
        response = await orchestrate_flow_full(sample_incident)

        # Check all required fields
        assert response.incident_id is not None
        assert response.triage is not None
        assert response.triage.label in ["LOW", "MEDIUM", "HIGH"]
        assert response.timeline is not None
        assert len(response.timeline) > 0

    @pytest.mark.asyncio
    async def test_full_flow_triage_matches_standalone(self, sample_incident):
        """Test that flow triage matches standalone triage."""
        from app.orchestration.a2a import orchestrate_flow_full
        from app.agents.triage import score_incident

        # Standalone triage
        label, score, contribs = score_incident(sample_incident.features)

        # Flow triage
        response = await orchestrate_flow_full(sample_incident)

        assert response.triage.label == label
        assert response.triage.score == score
