"""
MCP (Model Context Protocol) Envelope Handler for Google ADK Integration.

This module implements an MCP HTTP envelope handler compatible with Google ADK
and Kaggle AI Agents examples. It provides a standardized way for agents to
invoke tools via HTTP POST requests.

ADK POST Envelope Format (Request):
{
    "id": "req-uuid-123",
    "tool_name": "triage",
    "inputs": {
        "features": {
            "failed_logins_last_hour": 100,
            "suspicious_file_activity": true
        }
    },
    "from_agent": "orchestrator",
    "to_agent": "triage_agent",
    "trace_id": "trace-abc-456",
    "metadata": {
        "priority": "high",
        "source": "security-monitor"
    }
}

ADK Response Envelope Format:
{
    "id": "req-uuid-123",
    "status": "ok",
    "result": {
        "label": "HIGH",
        "score": 8,
        "contribs": [["failed_logins_last_hour", 3]]
    },
    "error": null,
    "trace_id": "trace-abc-456",
    "elapsed_ms": 12.5
}

Error Response:
{
    "id": "req-uuid-123",
    "status": "error",
    "result": null,
    "error": "Tool execution failed: timeout exceeded",
    "trace_id": "trace-abc-456",
    "elapsed_ms": 20000.0
}

References:
- https://cloud.google.com/blog/topics/developers-practitioners/use-google-adk-and-mcp-with-an-external-server
- https://modelcontextprotocol.io/specification/2025-03-26/basic/transports
- Kaggle 5-Day AI Agents Course: Day 2b - Agent Tools Best Practices

Usage:
    from app.orchestration.mcp_adk import handle_mcp_envelope, MCPEnvelopeRequest
    from app.orchestration.tools_adk import get_adk_tool

    envelope = MCPEnvelopeRequest(
        id="req-1",
        tool_name="triage",
        inputs={"features": {"failed_logins_last_hour": 50}},
        trace_id="trace-123"
    )
    tool = get_adk_tool("triage")
    response = await handle_mcp_envelope(envelope, tool)
"""

import asyncio
import json
import logging
import time
import uuid
from typing import Any, Awaitable, Callable, Literal, Optional

from pydantic import BaseModel, Field

# =============================================================================
# Pydantic Models for MCP Envelope
# =============================================================================


class MCPEnvelopeRequest(BaseModel):
    """
    MCP Request Envelope matching Google ADK format.

    Attributes:
        id: Unique request identifier (auto-generated if not provided)
        tool_name: Name of the tool to invoke
        inputs: Dictionary of inputs to pass to the tool
        from_agent: Optional identifier of the calling agent
        to_agent: Optional identifier of the target agent
        trace_id: Optional trace ID for distributed tracing
        metadata: Optional additional metadata
    """

    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    tool_name: str = Field(..., min_length=1, max_length=100)
    inputs: dict[str, Any] = Field(default_factory=dict)
    from_agent: Optional[str] = None
    to_agent: Optional[str] = None
    trace_id: Optional[str] = None
    metadata: Optional[dict[str, Any]] = None


class MCPEnvelopeResponse(BaseModel):
    """
    MCP Response Envelope matching Google ADK format.

    Attributes:
        id: Request ID (echoed from request)
        status: 'ok' for success, 'error' for failure
        result: Tool result dictionary (None on error)
        error: Error message (None on success)
        trace_id: Trace ID (echoed from request)
        elapsed_ms: Execution time in milliseconds
    """

    id: str
    status: Literal["ok", "error"]
    result: Optional[dict[str, Any]] = None
    error: Optional[str] = None
    trace_id: Optional[str] = None
    elapsed_ms: Optional[float] = None


# =============================================================================
# Secret Redaction
# =============================================================================

# Keys containing these substrings will be redacted
SENSITIVE_KEY_PATTERNS = ["token", "secret", "password", "key", "credential", "auth"]


def redact_secrets(obj: Any, _depth: int = 0) -> Any:
    """
    Recursively redact sensitive keys from dictionaries.

    Keys containing 'token', 'secret', 'password', 'key', 'credential', or 'auth'
    (case-insensitive) will have their values replaced with '[REDACTED]'.

    Args:
        obj: The object to sanitize (dict, list, or primitive)
        _depth: Current recursion depth (internal, prevents infinite recursion)

    Returns:
        Sanitized copy of the object

    Example:
        >>> redact_secrets({"api_key": "sk-123", "data": "safe"})
        {"api_key": "[REDACTED]", "data": "safe"}

        >>> redact_secrets({"auth": {"token": "abc", "user": "john"}})
        {"auth": {"token": "[REDACTED]", "user": "john"}}
    """
    if _depth > 50:
        return "[MAX_DEPTH_EXCEEDED]"

    if isinstance(obj, dict):
        result = {}
        for key, value in obj.items():
            key_lower = str(key).lower()
            if any(pattern in key_lower for pattern in SENSITIVE_KEY_PATTERNS):
                result[key] = "[REDACTED]"
            else:
                result[key] = redact_secrets(value, _depth + 1)
        return result
    elif isinstance(obj, list):
        return [redact_secrets(item, _depth + 1) for item in obj]
    else:
        return obj


def sanitize_for_logging(obj: Any, max_string_len: int = 500) -> Any:
    """
    Sanitize an object for safe logging.

    - Truncates long strings
    - Removes binary content
    - Converts non-JSON-serializable types to strings

    Args:
        obj: Object to sanitize
        max_string_len: Maximum length for string values

    Returns:
        Sanitized copy safe for logging
    """
    if isinstance(obj, dict):
        return {k: sanitize_for_logging(v, max_string_len) for k, v in obj.items()}
    elif isinstance(obj, list):
        return [sanitize_for_logging(item, max_string_len) for item in obj[:100]]
    elif isinstance(obj, str):
        if len(obj) > max_string_len:
            return obj[:max_string_len] + f"... [truncated, total {len(obj)} chars]"
        return obj
    elif isinstance(obj, bytes):
        return f"[BINARY: {len(obj)} bytes]"
    elif isinstance(obj, (int, float, bool, type(None))):
        return obj
    else:
        try:
            return str(obj)[:max_string_len]
        except Exception:
            return "[UNSERIALIZABLE]"


def ensure_json_serializable(obj: Any) -> Any:
    """
    Ensure an object is JSON-serializable.

    Converts non-serializable types to strings.

    Args:
        obj: Object to convert

    Returns:
        JSON-serializable version of the object
    """
    try:
        json.dumps(obj)
        return obj
    except (TypeError, ValueError):
        pass

    if isinstance(obj, dict):
        return {str(k): ensure_json_serializable(v) for k, v in obj.items()}
    elif isinstance(obj, (list, tuple)):
        return [ensure_json_serializable(item) for item in obj]
    elif isinstance(obj, bytes):
        return f"[BINARY: {len(obj)} bytes]"
    elif hasattr(obj, "__dict__"):
        return ensure_json_serializable(obj.__dict__)
    else:
        return str(obj)


# =============================================================================
# MCP Envelope Handler
# =============================================================================

# Type alias for tool callable
ToolCallable = Callable[[dict[str, Any], dict[str, Any]], Awaitable[dict[str, Any]]]


async def handle_mcp_envelope(
    envelope: MCPEnvelopeRequest,
    tool_callable: ToolCallable,
    timeout: int = 20,
    logger: Optional[logging.Logger] = None,
) -> MCPEnvelopeResponse:
    """
    Handle an MCP envelope request by invoking the specified tool.

    This function:
    1. Logs the invocation start (via observability or standard logging)
    2. Calls the tool with timeout protection
    3. Redacts secrets from the result
    4. Returns a typed MCPEnvelopeResponse

    Args:
        envelope: The MCP request envelope
        tool_callable: Async function with signature (inputs, context) -> dict
        timeout: Maximum execution time in seconds
        logger: Optional logger instance

    Returns:
        MCPEnvelopeResponse with status 'ok' or 'error'

    Example:
        >>> async def my_tool(inputs, context):
        ...     return {"result": inputs["value"] * 2}
        >>> envelope = MCPEnvelopeRequest(
        ...     id="req-1",
        ...     tool_name="double",
        ...     inputs={"value": 5}
        ... )
        >>> response = await handle_mcp_envelope(envelope, my_tool)
        >>> response.status
        'ok'
        >>> response.result
        {'result': 10}
    """
    if logger is None:
        logger = logging.getLogger("mcp_adk")

    start_time = time.monotonic()
    trace_id = envelope.trace_id or str(uuid.uuid4())

    # Build context for tool
    context = {
        "trace_id": trace_id,
        "request_id": envelope.id,
        "from_agent": envelope.from_agent,
        "to_agent": envelope.to_agent,
        "metadata": envelope.metadata or {},
    }

    # Log start event
    # ADK hook: google.adk.telemetry.start_span() would be called here
    _log_event(
        logger,
        "mcp.invoke.start",
        {
            "request_id": envelope.id,
            "tool_name": envelope.tool_name,
            "trace_id": trace_id,
            "from_agent": envelope.from_agent,
            "inputs_keys": list(envelope.inputs.keys()),
        },
    )

    try:
        # Execute tool with timeout
        result = await asyncio.wait_for(
            tool_callable(envelope.inputs, context),
            timeout=timeout,
        )

        # Ensure result is a dict
        if not isinstance(result, dict):
            result = {"value": result}

        # Sanitize result
        result = ensure_json_serializable(result)
        result = redact_secrets(result)

        elapsed_ms = (time.monotonic() - start_time) * 1000

        # Log success
        # ADK hook: google.adk.telemetry.end_span(status='ok') would be called here
        _log_event(
            logger,
            "mcp.invoke.success",
            {
                "request_id": envelope.id,
                "tool_name": envelope.tool_name,
                "trace_id": trace_id,
                "elapsed_ms": elapsed_ms,
                "result_keys": list(result.keys()) if isinstance(result, dict) else None,
            },
        )

        return MCPEnvelopeResponse(
            id=envelope.id,
            status="ok",
            result=result,
            error=None,
            trace_id=trace_id,
            elapsed_ms=round(elapsed_ms, 2),
        )

    except asyncio.TimeoutError:
        elapsed_ms = (time.monotonic() - start_time) * 1000
        error_msg = f"Tool '{envelope.tool_name}' timed out after {timeout}s"

        _log_event(
            logger,
            "mcp.invoke.timeout",
            {
                "request_id": envelope.id,
                "tool_name": envelope.tool_name,
                "trace_id": trace_id,
                "elapsed_ms": elapsed_ms,
                "timeout": timeout,
            },
            level="error",
        )

        return MCPEnvelopeResponse(
            id=envelope.id,
            status="error",
            result=None,
            error=error_msg,
            trace_id=trace_id,
            elapsed_ms=round(elapsed_ms, 2),
        )

    except Exception as e:
        elapsed_ms = (time.monotonic() - start_time) * 1000
        # Safe error message - no stack traces or internal details
        error_msg = f"Tool '{envelope.tool_name}' failed: {type(e).__name__}"

        # Log full error for debugging (redacted)
        # ADK hook: google.adk.telemetry.end_span(status='error') would be called here
        _log_event(
            logger,
            "mcp.invoke.error",
            {
                "request_id": envelope.id,
                "tool_name": envelope.tool_name,
                "trace_id": trace_id,
                "elapsed_ms": elapsed_ms,
                "error_type": type(e).__name__,
                "error_message": sanitize_for_logging(str(e), max_string_len=200),
            },
            level="error",
        )

        return MCPEnvelopeResponse(
            id=envelope.id,
            status="error",
            result=None,
            error=error_msg,
            trace_id=trace_id,
            elapsed_ms=round(elapsed_ms, 2),
        )


def _log_event(
    logger: logging.Logger,
    event_type: str,
    data: dict[str, Any],
    level: str = "info",
) -> None:
    """
    Log an MCP event.

    Tries to use observability.log_event if available, otherwise uses standard logging.

    Args:
        logger: Logger instance
        event_type: Event type identifier
        data: Event data dictionary
        level: Log level ('info', 'warning', 'error')
    """
    try:
        # Try to use observability module if available
        from app.core.observability import log_event

        log_event(event_type, data)
    except ImportError:
        # Fall back to standard logging
        log_func = getattr(logger, level, logger.info)
        log_func(f"{event_type}: {json.dumps(sanitize_for_logging(data))}")


# =============================================================================
# Convenience Functions
# =============================================================================


def create_error_response(
    request_id: str,
    error_message: str,
    trace_id: Optional[str] = None,
) -> MCPEnvelopeResponse:
    """
    Create an error response envelope.

    Args:
        request_id: Original request ID
        error_message: Error message to include
        trace_id: Optional trace ID

    Returns:
        MCPEnvelopeResponse with status 'error'
    """
    return MCPEnvelopeResponse(
        id=request_id,
        status="error",
        result=None,
        error=error_message,
        trace_id=trace_id,
        elapsed_ms=None,
    )


# =============================================================================
# Usage Example
# =============================================================================

if __name__ == "__main__":
    # Example usage
    import asyncio

    async def example_tool(inputs: dict, context: dict) -> dict:
        """Example tool that doubles a value."""
        return {"doubled": inputs.get("value", 0) * 2}

    async def main():
        envelope = MCPEnvelopeRequest(
            id="test-req-1",
            tool_name="double",
            inputs={"value": 21},
            trace_id="trace-example",
        )

        response = await handle_mcp_envelope(envelope, example_tool)
        print(f"Status: {response.status}")
        print(f"Result: {response.result}")
        print(f"Elapsed: {response.elapsed_ms}ms")

    asyncio.run(main())
