"""
Tests for MCP ADK Integration.

This module tests the MCP envelope handling and tool invocation via the ADK
integration layer. Tests cover:
    - Tool registration and discovery
    - MCP request/response envelope handling
    - Error handling and timeouts
    - Batch operations

Run with:
    cd backend && uv run pytest tests/test_mcp_adk.py -v
"""

import asyncio
import pytest
from unittest.mock import AsyncMock, patch

from app.mcp_adk import (
    MCPEnvelopeRequest,
    MCPEnvelopeResponse,
    handle_mcp_envelope,
    redact_secrets,
    sanitize_for_logging,
)
from app.tools_adk import (
    register_adk_tool,
    get_adk_tool,
    list_adk_tools,
    adk_tool,
    wrap_sync as tools_wrap_sync,
    is_tool_registered,
    ADK_TOOL_REGISTRY,
)


# =============================================================================
# Fixtures
# =============================================================================


@pytest.fixture(autouse=True)
def clear_registries():
    """Clear tool registries before each test."""
    # Save original state
    original_adk = dict(ADK_TOOL_REGISTRY)
    
    # Clear for test
    ADK_TOOL_REGISTRY.clear()
    
    yield
    
    # Restore original state
    ADK_TOOL_REGISTRY.clear()
    ADK_TOOL_REGISTRY.update(original_adk)


# =============================================================================
# Unit Tests: MCP Request/Response Models
# =============================================================================


class TestMCPModels:
    """Tests for MCP Pydantic models."""

    def test_mcp_request_minimal(self):
        """Test MCPEnvelopeRequest with minimal fields."""
        req = MCPEnvelopeRequest(tool_name="echo")
        assert req.tool_name == "echo"
        assert req.inputs == {}
        assert req.id is not None  # auto-generated

    def test_mcp_request_full(self):
        """Test MCPEnvelopeRequest with all fields."""
        req = MCPEnvelopeRequest(
            id="test-2",
            tool_name="triage",
            inputs={"features": {"failed_logins_last_hour": 50}},
            from_agent="agent-1",
            to_agent="agent-2",
            trace_id="trace-123",
            metadata={"priority": "high"},
        )
        assert req.id == "test-2"
        assert req.tool_name == "triage"
        assert req.inputs["features"]["failed_logins_last_hour"] == 50
        assert req.from_agent == "agent-1"
        assert req.trace_id == "trace-123"

    def test_mcp_response_success(self):
        """Test MCPEnvelopeResponse for success case."""
        resp = MCPEnvelopeResponse(
            id="test-1",
            status="ok",
            result={"label": "HIGH", "score": 8},
            trace_id="trace-123",
            elapsed_ms=42.5,
        )
        assert resp.status == "ok"
        assert resp.result["label"] == "HIGH"
        assert resp.error is None

    def test_mcp_response_error(self):
        """Test MCPEnvelopeResponse for error case."""
        resp = MCPEnvelopeResponse(
            id="test-2",
            status="error",
            error="Tool not found: unknown",
            elapsed_ms=1.5,
        )
        assert resp.status == "error"
        assert resp.result is None
        assert "Tool not found" in resp.error


# =============================================================================
# Unit Tests: Tool Registration (tools_adk.py)
# =============================================================================


class TestADKToolRegistration:
    """Tests for ADK tool registry."""

    def test_adk_tool_decorator(self):
        """Test @adk_tool decorator registers function."""
        @adk_tool("decorated_tool")
        async def my_tool(inputs, context):
            return {"result": "success"}
        
        assert "decorated_tool" in list_adk_tools()
        retrieved = get_adk_tool("decorated_tool")
        assert retrieved is my_tool

    def test_register_adk_tool_function(self):
        """Test register_adk_tool function."""
        async def another_tool(inputs, context):
            return {"data": inputs}
        
        register_adk_tool("another", another_tool)
        assert "another" in list_adk_tools()
        assert is_tool_registered("another")

    def test_get_adk_tool_not_found(self):
        """Test KeyError when tool not found."""
        with pytest.raises(KeyError, match="not found"):
            get_adk_tool("missing_tool")

    def test_is_tool_registered(self):
        """Test is_tool_registered function."""
        assert not is_tool_registered("nonexistent")
        
        @adk_tool("exists")
        async def existing_tool(inputs, context):
            return {}
        
        assert is_tool_registered("exists")

    def test_list_adk_tools_empty(self):
        """Test listing tools when registry is empty."""
        tools = list_adk_tools()
        assert tools == []

    def test_list_adk_tools_populated(self):
        """Test listing registered tools."""
        @adk_tool("tool_a")
        async def tool_a(inputs, context):
            return {}
        
        @adk_tool("tool_b")
        async def tool_b(inputs, context):
            return {}
        
        tools = list_adk_tools()
        assert "tool_a" in tools
        assert "tool_b" in tools


# =============================================================================
# Unit Tests: wrap_sync
# =============================================================================


class TestWrapSync:
    """Tests for sync-to-async wrapper."""

    @pytest.mark.asyncio
    async def test_wrap_sync_with_input_key(self):
        """Test wrapping sync function with input_key."""
        def multiply(features):
            return features["value"] * 2
        
        wrapped = tools_wrap_sync(multiply, input_key="features")
        result = await wrapped(
            {"features": {"value": 5}},
            {"trace_id": "test"},
        )
        # sync returning non-dict gets wrapped
        assert result == {"result": 10}

    @pytest.mark.asyncio
    async def test_wrap_sync_returns_dict(self):
        """Test wrapping sync function that returns dict."""
        def process(data):
            return {"processed": data["input"] + 1}
        
        wrapped = tools_wrap_sync(process)
        result = await wrapped(
            {"input": 10},
            {},
        )
        assert result == {"processed": 11}

    @pytest.mark.asyncio
    async def test_wrap_sync_tuple_return(self):
        """Test wrapping sync function that returns tuple."""
        def score(features):
            return ("HIGH", 8, [{"feature": "test", "contribution": 1.0}])
        
        wrapped = tools_wrap_sync(score, input_key="features")
        result = await wrapped(
            {"features": {}},
            {},
        )
        assert result["label"] == "HIGH"
        assert result["score"] == 8
        assert len(result["contribs"]) == 1

    @pytest.mark.asyncio
    async def test_wrap_sync_missing_input_key(self):
        """Test error when input_key is missing."""
        def process(data):
            return data
        
        wrapped = tools_wrap_sync(process, input_key="missing")
        
        with pytest.raises(ValueError, match="Expected 'missing' in inputs"):
            await wrapped({"other": "value"}, {})


# =============================================================================
# Unit Tests: handle_mcp_envelope
# =============================================================================


class TestHandleMCPEnvelope:
    """Tests for MCP envelope handling."""

    @pytest.mark.asyncio
    async def test_handle_envelope_success(self):
        """Test successful MCP envelope handling."""
        async def add(inputs, context):
            return {"sum": inputs["a"] + inputs["b"]}
        
        envelope = MCPEnvelopeRequest(
            id="req-1",
            tool_name="add",
            inputs={"a": 2, "b": 3},
            trace_id="trace-abc",
        )
        
        response = await handle_mcp_envelope(envelope, add)
        
        assert response.id == "req-1"
        assert response.status == "ok"
        assert response.result["sum"] == 5
        assert response.trace_id == "trace-abc"
        assert response.elapsed_ms > 0

    @pytest.mark.asyncio
    async def test_handle_envelope_tool_error(self):
        """Test MCP envelope when tool raises exception."""
        async def failing_tool(inputs, context):
            raise ValueError("Something went wrong")
        
        envelope = MCPEnvelopeRequest(
            id="req-3",
            tool_name="failing",
            inputs={},
        )
        
        response = await handle_mcp_envelope(envelope, failing_tool)
        
        assert response.id == "req-3"
        assert response.status == "error"
        assert "ValueError" in response.error

    @pytest.mark.asyncio
    async def test_handle_envelope_timeout(self):
        """Test MCP envelope timeout handling."""
        async def slow_tool(inputs, context):
            await asyncio.sleep(5)  # 5 seconds
            return {"result": "done"}
        
        envelope = MCPEnvelopeRequest(
            id="req-timeout",
            tool_name="slow",
            inputs={},
        )
        
        # Use 1 second timeout
        response = await handle_mcp_envelope(envelope, slow_tool, timeout=1)
        
        assert response.status == "error"
        assert "timed out" in response.error.lower()


# =============================================================================
# Unit Tests: Secret Redaction
# =============================================================================


class TestSecretRedaction:
    """Tests for PII/secret redaction."""

    def test_redact_secrets_api_key(self):
        """Test redaction of API keys."""
        data = {"api_key": "sk-12345", "message": "hello"}
        redacted = redact_secrets(data)
        
        assert redacted["api_key"] == "[REDACTED]"
        assert redacted["message"] == "hello"

    def test_redact_secrets_password(self):
        """Test redaction of passwords."""
        data = {"password": "secret123", "username": "user"}
        redacted = redact_secrets(data)
        
        assert redacted["password"] == "[REDACTED]"
        assert redacted["username"] == "user"

    def test_redact_secrets_token(self):
        """Test redaction of tokens."""
        data = {"access_token": "abc123", "endpoint": "https://api.example.com"}
        redacted = redact_secrets(data)
        
        assert redacted["access_token"] == "[REDACTED]"
        assert redacted["endpoint"] == "https://api.example.com"

    def test_redact_secrets_nested(self):
        """Test redaction in nested structures."""
        data = {
            "config": {
                "token": "abc123",
                "endpoint": "https://api.example.com",
            }
        }
        redacted = redact_secrets(data)
        
        assert redacted["config"]["token"] == "[REDACTED]"
        assert redacted["config"]["endpoint"] == "https://api.example.com"

    def test_redact_secrets_in_list(self):
        """Test redaction in lists."""
        data = {"items": [{"secret": "hidden"}, {"public": "visible"}]}
        redacted = redact_secrets(data)
        
        assert redacted["items"][0]["secret"] == "[REDACTED]"
        assert redacted["items"][1]["public"] == "visible"


# =============================================================================
# Unit Tests: sanitize_for_logging
# =============================================================================


class TestSanitizeForLogging:
    """Tests for logging sanitization."""

    def test_truncate_long_string(self):
        """Test truncation of long strings."""
        long_string = "x" * 1000
        sanitized = sanitize_for_logging(long_string, max_string_len=100)
        
        assert len(sanitized) < 200  # truncated + suffix
        assert "truncated" in sanitized

    def test_handle_binary(self):
        """Test handling of binary data."""
        data = {"binary": b"hello world"}
        sanitized = sanitize_for_logging(data)
        
        assert "[BINARY:" in sanitized["binary"]

    def test_preserve_normal_data(self):
        """Test that normal data is preserved."""
        data = {"number": 42, "string": "hello", "bool": True, "none": None}
        sanitized = sanitize_for_logging(data)
        
        assert sanitized == data


# =============================================================================
# Integration Tests: Full Flow
# =============================================================================


class TestMCPIntegration:
    """Integration tests for MCP flow."""

    @pytest.mark.asyncio
    async def test_register_and_invoke_tool(self):
        """Test registering and invoking a tool via MCP."""
        # Register tool using decorator
        @adk_tool("doubler")
        async def doubler(inputs, context):
            return {"doubled": inputs.get("value", 0) * 2}
        
        # Get the tool
        tool = get_adk_tool("doubler")
        
        # Create MCP envelope
        envelope = MCPEnvelopeRequest(
            id="int-1",
            tool_name="doubler",
            inputs={"value": 21},
            trace_id="integration-trace",
        )
        
        response = await handle_mcp_envelope(envelope, tool)
        
        assert response.status == "ok"
        assert response.result["doubled"] == 42
        assert response.trace_id == "integration-trace"

    @pytest.mark.asyncio
    async def test_triage_tool_mock(self):
        """Test triage tool via MCP with mocked response."""
        # Register a mock triage tool
        @adk_tool("mock_triage")
        async def mock_triage(inputs, context):
            features = inputs.get("features", {})
            failed = features.get("failed_logins_last_hour", 0)
            
            if failed > 20:
                return {"label": "CRITICAL", "score": 9, "contribs": []}
            elif failed > 10:
                return {"label": "HIGH", "score": 7, "contribs": []}
            else:
                return {"label": "LOW", "score": 2, "contribs": []}
        
        tool = get_adk_tool("mock_triage")
        
        # Create MCP request
        envelope = MCPEnvelopeRequest(
            id="int-2",
            tool_name="mock_triage",
            inputs={
                "features": {"failed_logins_last_hour": 50}
            },
            trace_id="triage-trace",
        )
        
        response = await handle_mcp_envelope(envelope, tool)
        
        assert response.status == "ok"
        assert response.result["label"] == "CRITICAL"
        assert response.result["score"] == 9

    @pytest.mark.asyncio
    async def test_chained_tools(self):
        """Test chaining multiple tools."""
        # Register tools
        @adk_tool("chain_a")
        async def tool_a(inputs, context):
            return {"intermediate": inputs["value"] * 2}
        
        @adk_tool("chain_b")
        async def tool_b(inputs, context):
            return {"final": inputs["intermediate"] + 10}
        
        # First call
        envelope1 = MCPEnvelopeRequest(
            id="chain-1",
            tool_name="chain_a",
            inputs={"value": 5},
        )
        resp1 = await handle_mcp_envelope(envelope1, get_adk_tool("chain_a"))
        assert resp1.result["intermediate"] == 10
        
        # Second call using first result
        envelope2 = MCPEnvelopeRequest(
            id="chain-2",
            tool_name="chain_b",
            inputs=resp1.result,
        )
        resp2 = await handle_mcp_envelope(envelope2, get_adk_tool("chain_b"))
        assert resp2.result["final"] == 20

    @pytest.mark.asyncio
    async def test_context_propagation(self):
        """Test that context is properly propagated to tools."""
        received_context = {}
        
        @adk_tool("context_checker")
        async def context_checker(inputs, context):
            received_context.update(context)
            return {"received": True}
        
        envelope = MCPEnvelopeRequest(
            id="ctx-1",
            tool_name="context_checker",
            inputs={},
            from_agent="agent-A",
            to_agent="agent-B",
            trace_id="trace-ctx",
            metadata={"custom": "value"},
        )
        
        await handle_mcp_envelope(envelope, get_adk_tool("context_checker"))
        
        assert received_context["trace_id"] == "trace-ctx"
        assert received_context["request_id"] == "ctx-1"
        assert received_context["from_agent"] == "agent-A"
        assert received_context["to_agent"] == "agent-B"
        assert received_context["metadata"]["custom"] == "value"


# =============================================================================
# Run Tests
# =============================================================================

if __name__ == "__main__":
    pytest.main([__file__, "-v"])
