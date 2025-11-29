"""
ADK Tool Registry for MCP Integration.

This module provides a registry pattern for registering and retrieving
async tool functions compatible with Google ADK / MCP protocol.

Key Features:
- @adk_tool decorator for easy tool registration
- wrap_sync() helper for adapting sync functions to async
- Lazy imports to keep startup cheap
- Type-safe tool signatures

Tool Signature:
    async def tool(inputs: dict[str, Any], context: dict[str, Any]) -> dict[str, Any]

    Args:
        inputs: Tool-specific input parameters
        context: Execution context with trace_id, request_id, etc.

    Returns:
        Dictionary with tool results

Expected Input Shapes by Tool:
    - triage: {"features": {"failed_logins_last_hour": 10, ...}}
    - explain: {"features": {...}, "triage_result": {"label": "HIGH", ...}}
    - runbook: {"features": {...}, "explanation": "...", "severity": "HIGH"}
    - policy: {"runbook": {"steps": [...], "source": "..."}}
    - simulate: {"runbook": {...}, "dry_run": true}

Usage:
    # Register with decorator
    @adk_tool("my_tool")
    async def my_tool(inputs: dict, context: dict) -> dict:
        return {"result": inputs["value"] * 2}

    # Register sync function
    from app.agents.triage import score_incident
    register_adk_tool("triage", wrap_sync(score_incident, input_key="features"))

    # Get and invoke tool
    tool = get_adk_tool("triage")
    result = await tool({"features": {...}}, {"trace_id": "abc"})

References:
    - Google ADK: https://google.github.io/adk-docs/
    - Kaggle AI Agents Course Day 2b
"""

import asyncio
import functools
import logging
from typing import Any, Awaitable, Callable, Optional

# =============================================================================
# Type Aliases
# =============================================================================

# Tool callable signature: (inputs, context) -> result dict
AsyncToolCallable = Callable[[dict[str, Any], dict[str, Any]], Awaitable[dict[str, Any]]]
SyncCallable = Callable[..., Any]

# =============================================================================
# Global Tool Registry
# =============================================================================

ADK_TOOL_REGISTRY: dict[str, AsyncToolCallable] = {}

_logger = logging.getLogger("tools_adk")


# =============================================================================
# Registry Functions
# =============================================================================


def register_adk_tool(name: str, func: AsyncToolCallable) -> None:
    """
    Register an async tool function in the ADK tool registry.

    Args:
        name: Unique tool name (e.g., 'triage', 'runbook')
        func: Async function with signature (inputs, context) -> dict

    Raises:
        ValueError: If a tool with the same name is already registered

    Example:
        async def my_tool(inputs, context):
            return {"result": "done"}

        register_adk_tool("my_tool", my_tool)
    """
    if name in ADK_TOOL_REGISTRY:
        _logger.warning(f"Overwriting existing tool registration: {name}")

    ADK_TOOL_REGISTRY[name] = func
    _logger.debug(f"Registered ADK tool: {name}")


def get_adk_tool(name: str) -> AsyncToolCallable:
    """
    Retrieve a registered tool by name.

    Args:
        name: Tool name to look up

    Returns:
        The registered async tool function

    Raises:
        KeyError: If tool is not registered (with helpful message)

    Example:
        tool = get_adk_tool("triage")
        result = await tool({"features": {...}}, {"trace_id": "abc"})
    """
    if name not in ADK_TOOL_REGISTRY:
        available = list(ADK_TOOL_REGISTRY.keys())
        raise KeyError(
            f"Tool '{name}' not found in registry. "
            f"Available tools: {available or 'none registered'}"
        )
    return ADK_TOOL_REGISTRY[name]


def list_adk_tools() -> list[str]:
    """
    List all registered tool names.

    Returns:
        List of registered tool names
    """
    return list(ADK_TOOL_REGISTRY.keys())


def is_tool_registered(name: str) -> bool:
    """
    Check if a tool is registered.

    Args:
        name: Tool name to check

    Returns:
        True if tool is registered
    """
    return name in ADK_TOOL_REGISTRY


# =============================================================================
# Tool Decorator
# =============================================================================


def adk_tool(name: str) -> Callable[[AsyncToolCallable], AsyncToolCallable]:
    """
    Decorator to register an async function as an ADK tool.

    Args:
        name: Unique tool name

    Returns:
        Decorator function

    Example:
        @adk_tool("my_tool")
        async def my_tool(inputs: dict, context: dict) -> dict:
            value = inputs.get("value", 0)
            return {"doubled": value * 2}

        # Tool is now registered and can be retrieved:
        tool = get_adk_tool("my_tool")
    """

    def decorator(func: AsyncToolCallable) -> AsyncToolCallable:
        register_adk_tool(name, func)
        return func

    return decorator


# =============================================================================
# Sync-to-Async Wrapper
# =============================================================================


def wrap_sync(
    fn: SyncCallable,
    input_key: Optional[str] = None,
    result_key: Optional[str] = None,
) -> AsyncToolCallable:
    """
    Wrap a synchronous function to match the async ADK tool signature.

    This adapter:
    1. Extracts the appropriate input from the inputs dict
    2. Calls the sync function (in executor to avoid blocking)
    3. Wraps the result in a dict if needed

    Args:
        fn: Synchronous function to wrap
        input_key: If provided, passes inputs[input_key] as the first arg.
                   If None, passes the entire inputs dict.
        result_key: If provided, wraps result as {result_key: result}.
                    If None and result is not a dict, wraps as {"result": result}.

    Returns:
        Async function with signature (inputs, context) -> dict

    Mapping Examples:
        # Pass inputs["features"] to score_incident(features)
        wrap_sync(score_incident, input_key="features")

        # Pass entire inputs dict to process_data(data)
        wrap_sync(process_data)

        # Wrap result as {"output": result}
        wrap_sync(compute, result_key="output")

    Example:
        from app.triage import score_incident

        # score_incident expects a features dict, returns (label, score, contribs)
        triage_tool = wrap_sync(score_incident, input_key="features")

        result = await triage_tool(
            {"features": {"failed_logins_last_hour": 50}},
            {"trace_id": "abc"}
        )
        # Returns: {"label": "HIGH", "score": 8, "contribs": [...]}
    """

    @functools.wraps(fn)
    async def async_wrapper(
        inputs: dict[str, Any], context: dict[str, Any]
    ) -> dict[str, Any]:
        # Extract input based on input_key
        if input_key:
            if input_key not in inputs:
                raise ValueError(
                    f"Expected '{input_key}' in inputs. Got keys: {list(inputs.keys())}"
                )
            fn_input = inputs[input_key]
        else:
            fn_input = inputs

        # Run sync function in executor to avoid blocking
        loop = asyncio.get_event_loop()
        try:
            result = await loop.run_in_executor(None, lambda: fn(fn_input))
        except Exception as e:
            # Re-raise with context
            raise RuntimeError(f"Tool execution failed: {e}") from e

        # Normalize result to dict
        if isinstance(result, dict):
            return result
        elif isinstance(result, tuple):
            # Handle common tuple returns like (label, score, contribs)
            if len(result) == 3:
                # Assume triage-style return
                return {"label": result[0], "score": result[1], "contribs": result[2]}
            elif len(result) == 2:
                return {"first": result[0], "second": result[1]}
            else:
                return {"values": list(result)}
        elif result_key:
            return {result_key: result}
        else:
            return {"result": result}

    return async_wrapper


# =============================================================================
# Tool Registration (Lazy Loading)
# =============================================================================


def register_default_tools() -> None:
    """
    Register default tools from the app modules.

    This function uses lazy imports to avoid loading heavy modules at startup.
    Call this during application initialization.

    Registers:
        - triage: Score incident severity
        - explain: Generate explanation
        - runbook: Generate runbook steps
        - policy_check: Check policy compliance
        - simulate: Simulate runbook execution
    """
    _logger.info("Registering default ADK tools...")

    # Triage tool - sync function wrapped
    try:
        from app.agents.triage import score_incident

        register_adk_tool("triage", wrap_sync(score_incident, input_key="features"))
        _logger.debug("Registered: triage")
    except ImportError as e:
        _logger.warning(f"Could not register triage tool: {e}")

    # Policy check tool - sync function wrapped
    try:
        from app.agents.policy import policy_check_dict

        register_adk_tool("policy_check", wrap_sync(policy_check_dict, input_key="runbook"))
        _logger.debug("Registered: policy_check")
    except ImportError as e:
        _logger.warning(f"Could not register policy_check tool: {e}")

    # Explain tool - async function
    @adk_tool("explain")
    async def explain_tool(inputs: dict, context: dict) -> dict:
        """Generate explanation for triage result."""
        from app.agents.explain import generate_explanation

        features = inputs.get("features", {})
        triage_result = inputs.get("triage_result", {})

        explanation = await generate_explanation(
            features=features,
            triage_label=triage_result.get("label", "UNKNOWN"),
            triage_score=triage_result.get("score", 0),
            contributing_factors=triage_result.get("contribs", []),
        )
        return {"explanation": explanation}

    # Runbook tool - async function
    @adk_tool("runbook")
    async def runbook_tool(inputs: dict, context: dict) -> dict:
        """Generate runbook steps for incident response."""
        from app.agents.runbook import generate_runbook

        features = inputs.get("features", {})
        explanation = inputs.get("explanation", "")
        severity = inputs.get("severity", "MEDIUM")

        runbook = await generate_runbook(
            features=features,
            explanation=explanation,
            severity=severity,
        )
        return runbook

    # Simulate tool - async function
    @adk_tool("simulate")
    async def simulate_tool(inputs: dict, context: dict) -> dict:
        """Simulate runbook execution."""
        from app.agents.simulate import simulate_runbook

        runbook = inputs.get("runbook", {})
        trace_id = context.get("trace_id")

        events = await simulate_runbook(runbook, trace_id=trace_id)
        return {"events": events, "total_steps": len(runbook.get("runbook", []))}

    _logger.info(f"Registered {len(ADK_TOOL_REGISTRY)} ADK tools: {list_adk_tools()}")


# =============================================================================
# Example Registrations (Commented)
# =============================================================================

# Example 1: Register triage using wrap_sync
# from app.triage import score_incident
# register_adk_tool('triage', wrap_sync(score_incident, input_key='features'))

# Example 2: Register runbook using decorator
# @adk_tool('runbook')
# async def runbook_tool(inputs: dict, context: dict) -> dict:
#     from app.runbook import generate_runbook
#     return await generate_runbook(
#         features=inputs['features'],
#         explanation=inputs['explanation'],
#         severity=inputs['severity']
#     )

# Example 3: Register policy check
# from app.policy import check_runbook
# register_adk_tool('policy_check', wrap_sync(check_runbook, input_key='runbook'))


# =============================================================================
# Usage Example
# =============================================================================

if __name__ == "__main__":
    import asyncio

    # Example: Register and use a simple tool
    @adk_tool("echo")
    async def echo_tool(inputs: dict, context: dict) -> dict:
        return {"echo": inputs, "trace_id": context.get("trace_id")}

    async def main():
        # List tools
        print(f"Registered tools: {list_adk_tools()}")

        # Get and invoke
        tool = get_adk_tool("echo")
        result = await tool(
            {"message": "Hello ADK!"},
            {"trace_id": "test-123"},
        )
        print(f"Result: {result}")

    asyncio.run(main())
