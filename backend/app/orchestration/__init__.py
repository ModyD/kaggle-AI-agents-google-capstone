"""
Orchestration and protocol handling.

This package contains:
- A2A (Agent-to-Agent) orchestration
- MCP (Model Context Protocol) envelope handling
- ADK tool registry
- Long-running job manager
- Vertex AI tools demo
"""

from .a2a import (
    orchestrate_flow,
    orchestrate_flow_full,
    create_a2a_message,
    create_timeline_entry,
    call_triage_agent,
    call_explain_agent,
    call_runbook_agent,
    call_policy_agent,
    call_simulator_agent,
)
from .mcp_adk import (
    handle_mcp_envelope,
    MCPEnvelopeRequest,
    MCPEnvelopeResponse,
    redact_secrets,
    sanitize_for_logging,
    ensure_json_serializable,
    create_error_response,
)
from .tools_adk import (
    register_adk_tool,
    get_adk_tool,
    list_adk_tools,
    is_tool_registered,
    adk_tool,
    wrap_sync,
    register_default_tools,
)
from .long_running_manager import (
    LongRunningManager,
    JobInfo,
    JobStatus,
    CooperativeTask,
    create_runbook_simulation_job,
)
from .built_in_tools_demo import (
    vertex_search_demo,
    vertex_code_exec_demo,
    register_vertex_tools,
    get_grounding_config,
)

__all__ = [
    # A2A
    "orchestrate_flow",
    "orchestrate_flow_full",
    "create_a2a_message",
    "create_timeline_entry",
    "call_triage_agent",
    "call_explain_agent",
    "call_runbook_agent",
    "call_policy_agent",
    "call_simulator_agent",
    # MCP
    "handle_mcp_envelope",
    "MCPEnvelopeRequest",
    "MCPEnvelopeResponse",
    "redact_secrets",
    "sanitize_for_logging",
    "ensure_json_serializable",
    "create_error_response",
    # Tools
    "register_adk_tool",
    "get_adk_tool",
    "list_adk_tools",
    "is_tool_registered",
    "adk_tool",
    "wrap_sync",
    "register_default_tools",
    # Jobs
    "LongRunningManager",
    "JobInfo",
    "JobStatus",
    "CooperativeTask",
    "create_runbook_simulation_job",
    # Vertex
    "vertex_search_demo",
    "vertex_code_exec_demo",
    "register_vertex_tools",
    "get_grounding_config",
]
