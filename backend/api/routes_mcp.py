"""
MCP API Routes for ADK Integration.

This module exposes FastAPI routes for the MCP (Model Context Protocol)
integration with Google ADK. It provides endpoints for:
    - Tool invocation via MCP envelope
    - Tool listing and discovery
    - Health/readiness probes for MCP subsystem

Protocol:
    MCP uses a JSON envelope for tool invocations:

    Request:
        POST /mcp/invoke
        {
            "id": "uuid",
            "tool_name": "triage",
            "inputs": {"features": {...}},
            "from_agent": "agent-id",
            "trace_id": "trace-uuid"
        }

    Response:
        {
            "id": "uuid",
            "status": "ok|error",
            "result": {...},
            "trace_id": "trace-uuid",
            "elapsed_ms": 42.5
        }

References:
    - MCP Specification: https://modelcontextprotocol.io/specification
    - Google ADK: https://google.github.io/adk-docs/
"""

import logging
import time
from typing import Any

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field

from app.mcp_adk import (
    MCPEnvelopeRequest,
    MCPEnvelopeResponse,
    handle_mcp_envelope,
)
from app.tools_adk import (
    get_adk_tool,
    list_adk_tools,
    register_default_tools,
    is_tool_registered,
)

# =============================================================================
# Router Setup
# =============================================================================

router = APIRouter(prefix="/mcp", tags=["MCP"])

_logger = logging.getLogger("routes_mcp")

# Track if tools have been registered
_tools_registered = False


# =============================================================================
# Startup Hook
# =============================================================================


def ensure_tools_registered() -> None:
    """Ensure default tools are registered (idempotent)."""
    global _tools_registered
    if not _tools_registered:
        register_default_tools()
        _tools_registered = True
        _logger.info("MCP tools registered on first request")


# =============================================================================
# Request/Response Models
# =============================================================================


class InvokeRequest(BaseModel):
    """Request model for MCP tool invocation."""

    id: str = Field(..., description="Unique request ID (UUID)")
    tool_name: str = Field(..., description="Name of tool to invoke")
    inputs: dict[str, Any] = Field(default_factory=dict, description="Tool inputs")
    from_agent: str | None = Field(None, description="Calling agent ID")
    to_agent: str | None = Field(None, description="Target agent ID")
    trace_id: str | None = Field(None, description="Distributed trace ID")
    metadata: dict[str, Any] = Field(default_factory=dict, description="Extra metadata")
    timeout_ms: int = Field(default=30000, ge=100, le=300000, description="Timeout in ms")


class InvokeResponse(BaseModel):
    """Response model for MCP tool invocation."""

    id: str = Field(..., description="Matching request ID")
    status: str = Field(..., description="ok or error")
    result: dict[str, Any] | None = Field(None, description="Tool result if success")
    error: str | None = Field(None, description="Error message if failed")
    trace_id: str | None = Field(None, description="Trace ID for correlation")
    elapsed_ms: float = Field(..., description="Execution time in milliseconds")


class ToolInfo(BaseModel):
    """Information about a registered tool."""

    name: str = Field(..., description="Tool name")
    description: str | None = Field(None, description="Tool description")
    registered: bool = Field(True, description="Whether tool is registered")


class ToolListResponse(BaseModel):
    """Response model for tool listing."""

    tools: list[ToolInfo] = Field(default_factory=list, description="Registered tools")
    count: int = Field(..., description="Total number of tools")


class MCPHealthResponse(BaseModel):
    """Health check response for MCP subsystem."""

    status: str = Field(..., description="Health status")
    tools_registered: int = Field(..., description="Number of registered tools")
    tools: list[str] = Field(default_factory=list, description="Registered tool names")


# =============================================================================
# API Endpoints
# =============================================================================


@router.post("/invoke", response_model=InvokeResponse)
async def invoke_tool(request: InvokeRequest, raw_request: Request) -> InvokeResponse:
    """
    Invoke a tool via MCP envelope.

    This endpoint receives MCP-formatted requests and routes them to the
    appropriate tool handler. It provides:
        - Automatic tool registration on first request
        - Timeout handling
        - Error wrapping with trace correlation
        - Execution time tracking

    Args:
        request: MCP invoke request with tool_name and inputs
        raw_request: FastAPI request for extracting client info

    Returns:
        MCP response with status, result, and timing info

    Raises:
        HTTPException: 404 if tool not found, 500 for internal errors

    Example Request:
        POST /mcp/invoke
        {
            "id": "550e8400-e29b-41d4-a716-446655440000",
            "tool_name": "triage",
            "inputs": {
                "features": {
                    "failed_logins_last_hour": 50,
                    "distinct_source_ips": 10,
                    "after_hours": true,
                    "is_privileged_account": true,
                    "geo_anomaly_score": 0.9,
                    "data_volume_mb": 1000,
                    "known_malicious_ip": true,
                    "prev_incidents_24h": 2,
                    "is_sensitive_system": true,
                    "event_type": "brute_force"
                }
            },
            "trace_id": "trace-123"
        }

    Example Response:
        {
            "id": "550e8400-e29b-41d4-a716-446655440000",
            "status": "ok",
            "result": {
                "label": "CRITICAL",
                "score": 9,
                "contribs": [
                    {"feature": "failed_logins_last_hour", "contribution": 2.0}
                ]
            },
            "trace_id": "trace-123",
            "elapsed_ms": 15.3
        }
    """
    start_time = time.monotonic()
    
    # Ensure tools are registered
    ensure_tools_registered()

    # Check if tool exists
    if not is_tool_registered(request.tool_name):
        tools = list_adk_tools()
        elapsed_ms = (time.monotonic() - start_time) * 1000
        return InvokeResponse(
            id=request.id,
            status="error",
            result=None,
            error=f"Tool '{request.tool_name}' not found. Available: {tools}",
            trace_id=request.trace_id,
            elapsed_ms=round(elapsed_ms, 2),
        )

    # Get the tool
    try:
        tool_callable = get_adk_tool(request.tool_name)
    except KeyError as e:
        elapsed_ms = (time.monotonic() - start_time) * 1000
        return InvokeResponse(
            id=request.id,
            status="error",
            result=None,
            error=str(e),
            trace_id=request.trace_id,
            elapsed_ms=round(elapsed_ms, 2),
        )

    # Create MCP envelope
    mcp_envelope = MCPEnvelopeRequest(
        id=request.id,
        tool_name=request.tool_name,
        inputs=request.inputs,
        from_agent=request.from_agent,
        to_agent=request.to_agent,
        trace_id=request.trace_id,
        metadata=request.metadata,
    )

    # Add client info to metadata
    client_host = raw_request.client.host if raw_request.client else "unknown"
    if mcp_envelope.metadata is None:
        mcp_envelope.metadata = {}
    mcp_envelope.metadata["client_host"] = client_host

    # Calculate timeout in seconds
    timeout_sec = request.timeout_ms / 1000

    # Handle the request
    mcp_response = await handle_mcp_envelope(
        envelope=mcp_envelope,
        tool_callable=tool_callable,
        timeout=int(timeout_sec),
        logger=_logger,
    )

    # Convert to API response
    return InvokeResponse(
        id=mcp_response.id,
        status=mcp_response.status,
        result=mcp_response.result,
        error=mcp_response.error,
        trace_id=mcp_response.trace_id,
        elapsed_ms=mcp_response.elapsed_ms or 0,
    )


@router.get("/tools", response_model=ToolListResponse)
async def list_tools() -> ToolListResponse:
    """
    List all registered MCP tools.

    Returns a list of all tools available for invocation via the MCP endpoint.

    Returns:
        ToolListResponse with list of tools and count

    Example Response:
        {
            "tools": [
                {"name": "triage", "description": null, "registered": true},
                {"name": "explain", "description": null, "registered": true},
                {"name": "runbook", "description": null, "registered": true}
            ],
            "count": 3
        }
    """
    # Ensure tools are registered
    ensure_tools_registered()

    tools = list_adk_tools()
    tool_infos = [ToolInfo(name=name) for name in tools]

    return ToolListResponse(tools=tool_infos, count=len(tools))


@router.get("/health", response_model=MCPHealthResponse)
async def mcp_health() -> MCPHealthResponse:
    """
    Health check for MCP subsystem.

    Returns the status of the MCP subsystem and registered tools.

    Returns:
        MCPHealthResponse with status and tool information

    Example Response:
        {
            "status": "healthy",
            "tools_registered": 5,
            "tools": ["triage", "explain", "runbook", "policy_check", "simulate"]
        }
    """
    # Ensure tools are registered
    ensure_tools_registered()

    tools = list_adk_tools()

    return MCPHealthResponse(
        status="healthy",
        tools_registered=len(tools),
        tools=tools,
    )


@router.get("/tool/{tool_name}")
async def get_tool_info(tool_name: str) -> ToolInfo:
    """
    Get information about a specific tool.

    Args:
        tool_name: Name of the tool to query

    Returns:
        ToolInfo with tool details

    Raises:
        HTTPException: 404 if tool not found

    Example:
        GET /mcp/tool/triage

        {
            "name": "triage",
            "description": null,
            "registered": true
        }
    """
    # Ensure tools are registered
    ensure_tools_registered()

    if not is_tool_registered(tool_name):
        tools = list_adk_tools()
        raise HTTPException(
            status_code=404,
            detail=f"Tool '{tool_name}' not found. Available: {tools}",
        )

    return ToolInfo(name=tool_name)


# =============================================================================
# Batch Operations
# =============================================================================


class BatchInvokeRequest(BaseModel):
    """Request model for batch tool invocation."""

    requests: list[InvokeRequest] = Field(..., description="List of invoke requests")


class BatchInvokeResponse(BaseModel):
    """Response model for batch tool invocation."""

    responses: list[InvokeResponse] = Field(..., description="List of responses")
    total: int = Field(..., description="Total requests processed")
    succeeded: int = Field(..., description="Number of successful requests")
    failed: int = Field(..., description="Number of failed requests")


@router.post("/invoke/batch", response_model=BatchInvokeResponse)
async def batch_invoke_tools(
    request: BatchInvokeRequest, raw_request: Request
) -> BatchInvokeResponse:
    """
    Invoke multiple tools in batch.

    Processes multiple MCP requests in parallel and returns all results.

    Args:
        request: Batch invoke request with list of tool invocations
        raw_request: FastAPI request for extracting client info

    Returns:
        BatchInvokeResponse with all results and summary

    Example Request:
        POST /mcp/invoke/batch
        {
            "requests": [
                {
                    "id": "req-1",
                    "tool_name": "triage",
                    "inputs": {"features": {...}}
                },
                {
                    "id": "req-2",
                    "tool_name": "policy_check",
                    "inputs": {"runbook": {...}}
                }
            ]
        }
    """
    import asyncio

    # Ensure tools are registered
    ensure_tools_registered()

    # Process all requests in parallel
    async def process_one(req: InvokeRequest) -> InvokeResponse:
        return await invoke_tool(req, raw_request)

    responses = await asyncio.gather(
        *[process_one(req) for req in request.requests],
        return_exceptions=True,
    )

    # Convert exceptions to error responses
    final_responses: list[InvokeResponse] = []
    for i, resp in enumerate(responses):
        if isinstance(resp, Exception):
            final_responses.append(
                InvokeResponse(
                    id=request.requests[i].id,
                    status="error",
                    result=None,
                    error=str(resp),
                    trace_id=request.requests[i].trace_id,
                    elapsed_ms=0,
                )
            )
        else:
            final_responses.append(resp)

    succeeded = sum(1 for r in final_responses if r.status == "ok")
    failed = len(final_responses) - succeeded

    return BatchInvokeResponse(
        responses=final_responses,
        total=len(final_responses),
        succeeded=succeeded,
        failed=failed,
    )
