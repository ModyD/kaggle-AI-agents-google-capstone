---
agent: agent
model: Claude Opus 4.5 (Preview) (copilot)
---
# 00 — Shared project context (paste once)
Context: Repo root contains backend/ with FastAPI app under backend/app and API router under backend/api. Use Python 3.11, FastAPI, Pydantic v2, asyncio, LangChain/Vertex (Gemini) may be used later. We must produce two files:
1) backend/app/mcp_adk.py — a single MCP HTTP-envelope handler and invoker that matches the Google ADK / Kaggle example envelope format (tool_name, inputs, trace_id, metadata). It should validate requests, redact secrets, call a tool callable with timeout via asyncio.wait_for, integrate with observability.log_event (or standard logging), and return a typed MCPEnvelopeResponse. Include docstrings showing expected ADK POST envelope and response shape. Keep ADK-specific placeholders/comments where `google.adk` hooks would be used.
2) backend/app/tools_adk.py — a single tool registry module with register/get functions and a decorator @adk_tool to register async tools of signature async def tool(inputs: dict, context: dict) -> dict. Provide a helper wrap_sync(fn) for adapting sync functions (like triage.score_incident) into the async tool signature. Add a few commented example registrations for triage, runbook, policy, simulate that use wrap_sync to avoid heavy imports on module load.
Generated code must be safe to import at FastAPI startup, fully typed, include docstrings, and include small usage examples at the bottom. Tests and extra files are not required in this step.

# 01 — Prompt to generate backend/app/mcp_adk.py
Prompt:
"Generate the file `backend/app/mcp_adk.py`. Requirements:
- Use Pydantic v2 models:
  - MCPEnvelopeRequest: { id: str, tool_name: str, inputs: dict[str, Any], from_agent: str | None, to_agent: str | None, trace_id: str | None, metadata: dict | None }
  - MCPEnvelopeResponse: { id: str, status: Literal['ok','error'], result: dict | None, error: str | None, trace_id: str | None, elapsed_ms: float | None }
- Implement async function `async def handle_mcp_envelope(envelope: MCPEnvelopeRequest, tool_callable: Callable[[dict, dict], Any], timeout: int = 20) -> MCPEnvelopeResponse` that:
  - logs start via observability.log_event('mcp.invoke.start', {...}) where available, else use standard logging,
  - calls `await asyncio.wait_for(tool_callable(envelope.inputs, {'trace_id': envelope.trace_id}), timeout)`,
  - on success: sanitize the returned dict with `redact_secrets` (redact keys containing substrings ['token','secret','password','key']), measure elapsed ms, and return status 'ok' plus sanitized result,
  - on exception: catch, log exception, and return status 'error' with safe error message (no stack traces or secrets),
  - ensure JSON-serializable result (convert non-serializables to str),
  - include small helper `redact_secrets(obj: Any) -> Any` that recursively redacts nested sensitive keys,
  - include helper `sanitize_for_logging(obj: Any) -> Any` that truncates very large strings and removes binary content,
  - include module-level docstring demonstrating the exact POST envelope JSON example (matching google ADK syntax:   https://www.kaggle.com/code/kaggle5daysofai/day-2b-agent-tools-best-practices?scriptVersionId=275613972&cellId=17 

  https://cloud.google.com/blog/topics/developers-practitioners/use-google-adk-and-mcp-with-an-external-server

  https://www.kaggle.com/code/kaggle5daysofai/day-2b-agent-tools-best-practices?scriptVersionId=275613972&cellId=18  ) and expected MCPEnvelopeResponse JSON.
- Use typing, asyncio, time.monotonic for timing, and robust type annotations. Keep ADK-specific comments/placeholders to show where to plug `google.adk` tracing hooks.
Return only the Python code for the file."

# 02 — Prompt to generate backend/app/tools_adk.py
Prompt:
"Generate the file `backend/app/tools_adk.py`. Requirements:
- Implement a tool registry and adapter for ADK tools:
  - global ADK_TOOL_REGISTRY: Dict[str, Callable[[dict, dict], Awaitable[dict]]]
  - function `register_adk_tool(name: str, func: Callable[[dict, dict], Awaitable[dict]]) -> None`
  - function `get_adk_tool(name: str) -> Callable[[dict, dict], Awaitable[dict]]` that raises a clear KeyError if missing
  - decorator `def adk_tool(name: str)` that registers the decorated async function
  - helper `def wrap_sync(fn: Callable[..., Any]) -> Callable[[dict, dict], Awaitable[dict]]` that returns an async wrapper which maps inputs dict to the underlying sync function parameters (document mapping), catches exceptions, and returns a dict result
- Provide examples at bottom (commented) showing:
  - how to register triage via `register_adk_tool('triage', wrap_sync(triage.score_incident))`
  - how to register runbook via `@adk_tool('runbook') async def runbook_tool(inputs, context): ...`
- Add docstrings describing expected `inputs` shape for common tools (triage expects {'features': {...}}, runbook expects {'features':..., 'explanation':...}, policy expects {'runbook': ...}).
- Keep imports minimal and avoid heavy imports at module top to keep startup cheap (use local imports inside wrapper if necessary).
Return only the Python code for the file."

# ------------------------------
# 03 - tests/test_mcp_adk.py (pytest adjusted to Kaggle style)
# ------------------------------
Prompt:
"Generate `backend/tests/test_mcp_adk.py` (pytest-asyncio). Tests required:
- validate MCPEnvelopeRequest parses valid envelope and rejects invalid shapes,
- register a mock tool named 'mock_tool' via tools_adk.register_adk_tool and assert /mcp/invoke returns status 'ok' and expected result,
- test error path where a tool raises an exception and /mcp/invoke returns status 'error' with safe message,
- test that redaction removes nested 'auth.token' fields,
- monkeypatch observability.log_event to no-op."

# ------------------------------
# 07 - update api/main.py inclusion & startup
# ------------------------------
Prompt:
"Generate a small patch for `backend/api/main.py` instructions:
- import adk_registration to register tools on startup (or call it in startup event),
- include router from routes_mcp_adk.py using `app.include_router(mcp_router, prefix='/mcp')`,
- ensure startup/shutdown events initialize DB and observability and import adk_registration (safe import pattern). Provide code snippet to paste into main.py."


# ------------------------------
# 04 - README update (MCP ADK usage examples)
# ------------------------------
Prompt:
"Append to `backend/README.md` a section titled 'MCP (Google ADK style)'. Include:
- short explanation and why it matches Kaggle ADK examples,
- sample MCP envelope JSON that ADK would POST,
- example curl command to call /mcp/invoke,
- notes on registering tools and on secret redaction and production best practices (Secret Manager, don't expose service-account JSON)."
