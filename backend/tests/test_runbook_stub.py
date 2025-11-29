"""
Tests for runbook generation with stubs.
"""

import pytest
from typing import Any

from app.models import RunbookResponse, RunbookStep


# =============================================================================
# Fixtures
# =============================================================================


@pytest.fixture
def high_severity_context() -> dict[str, Any]:
    """Context for high severity incident."""
    return {
        "features": {
            "failed_logins_last_hour": 50,
            "suspicious_file_activity": True,
        },
        "label": "HIGH",
        "score": 8,
        "contribs": [
            ("failed_logins_last_hour", 3),
            ("suspicious_file_activity", 2),
        ],
    }


@pytest.fixture
def low_severity_context() -> dict[str, Any]:
    """Context for low severity incident."""
    return {
        "features": {"failed_logins_last_hour": 2},
        "label": "LOW",
        "score": 0,
        "contribs": [],
    }


# =============================================================================
# Stub Runbook Tests
# =============================================================================


class TestStubRunbook:
    """Tests for stub runbook generation."""

    def test_stub_runbook_high_severity(self, high_severity_context):
        """Test stub runbook for high severity."""
        from app.services.chains import get_stub_runbook

        runbook = get_stub_runbook(
            high_severity_context["label"],
            high_severity_context["contribs"],
        )

        assert isinstance(runbook, RunbookResponse)
        assert len(runbook.runbook) >= 3  # HIGH should have more steps
        assert runbook.source == "stub"

    def test_stub_runbook_low_severity(self, low_severity_context):
        """Test stub runbook for low severity."""
        from app.services.chains import get_stub_runbook

        runbook = get_stub_runbook(
            low_severity_context["label"],
            low_severity_context["contribs"],
        )

        assert isinstance(runbook, RunbookResponse)
        assert len(runbook.runbook) >= 1
        assert runbook.source == "stub"

    def test_stub_runbook_steps_valid(self, high_severity_context):
        """Test that stub runbook steps are valid."""
        from app.services.chains import get_stub_runbook

        runbook = get_stub_runbook(
            high_severity_context["label"],
            high_severity_context["contribs"],
        )

        for step in runbook.runbook:
            assert isinstance(step, RunbookStep)
            assert len(step.step) >= 5
            assert len(step.why) >= 5
            assert step.risk in ["low", "medium", "high"]


class TestStubExplanation:
    """Tests for stub explanation generation."""

    def test_stub_explanation_structure(self, high_severity_context):
        """Test stub explanation has correct structure."""
        from app.services.chains import get_stub_explanation

        explanation = get_stub_explanation(
            high_severity_context["label"],
            high_severity_context["score"],
            high_severity_context["contribs"],
        )

        assert "explanation" in explanation
        assert "reasons" in explanation
        assert isinstance(explanation["explanation"], str)
        assert isinstance(explanation["reasons"], list)
        assert len(explanation["reasons"]) >= 1

    def test_stub_explanation_mentions_severity(self, high_severity_context):
        """Test that explanation mentions the severity level."""
        from app.services.chains import get_stub_explanation

        explanation = get_stub_explanation(
            high_severity_context["label"],
            high_severity_context["score"],
            high_severity_context["contribs"],
        )

        assert "HIGH" in explanation["explanation"]


# =============================================================================
# Runbook Generation Tests
# =============================================================================


class TestRunbookGeneration:
    """Tests for runbook generation."""

    @pytest.mark.asyncio
    async def test_generate_runbook_returns_response(self, high_severity_context):
        """Test that generate_runbook returns a valid response."""
        from app.agents.runbook import generate_runbook

        runbook = await generate_runbook(
            features=high_severity_context["features"],
            label=high_severity_context["label"],
            score=high_severity_context["score"],
            contribs=high_severity_context["contribs"],
        )

        assert isinstance(runbook, RunbookResponse)
        assert len(runbook.runbook) > 0

    @pytest.mark.asyncio
    async def test_generate_runbook_from_description(self):
        """Test runbook generation from description."""
        from app.agents.runbook import generate_runbook_from_description

        runbook = await generate_runbook_from_description(
            description="Suspected ransomware infection with encrypted files",
            severity="HIGH",
        )

        assert isinstance(runbook, RunbookResponse)
        assert len(runbook.runbook) > 0

    @pytest.mark.asyncio
    async def test_template_runbook_brute_force(self):
        """Test template runbook for brute force."""
        from app.agents.runbook import get_template_runbook

        runbook = await get_template_runbook("brute_force")

        assert isinstance(runbook, RunbookResponse)
        assert runbook.source == "template"
        assert len(runbook.runbook) >= 3

    @pytest.mark.asyncio
    async def test_template_runbook_malware(self):
        """Test template runbook for malware."""
        from app.agents.runbook import get_template_runbook

        runbook = await get_template_runbook("malware")

        assert isinstance(runbook, RunbookResponse)
        assert len(runbook.runbook) >= 4

    @pytest.mark.asyncio
    async def test_template_runbook_default(self):
        """Test default template runbook."""
        from app.agents.runbook import get_template_runbook

        runbook = await get_template_runbook("unknown_type")

        assert isinstance(runbook, RunbookResponse)
        assert runbook.source == "template"


# =============================================================================
# Retrieval Query Building Tests
# =============================================================================


class TestRetrievalQuery:
    """Tests for retrieval query building."""

    def test_build_query_includes_severity(self, high_severity_context):
        """Test that query includes severity level."""
        from app.agents.runbook import build_retrieval_query

        query = build_retrieval_query(
            features=high_severity_context["features"],
            label=high_severity_context["label"],
            contribs=high_severity_context["contribs"],
        )

        assert "HIGH" in query

    def test_build_query_includes_indicators(self, high_severity_context):
        """Test that query includes contributing factors."""
        from app.agents.runbook import build_retrieval_query

        query = build_retrieval_query(
            features=high_severity_context["features"],
            label=high_severity_context["label"],
            contribs=high_severity_context["contribs"],
        )

        assert "failed_logins" in query.lower() or "brute" in query.lower()
