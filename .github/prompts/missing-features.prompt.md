---
agent: agent
model: Claude Opus 4.5 (Preview) (copilot)
---
# 00 — Shared context (paste once)
Context: Repo root has backend/app and backend/api as previously shown. Use Python 3.11, FastAPI, Pydantic v2, asyncio. Existing modules: app.a2a, app.db, app.observability, app.tools_adk, app.rag, app.runbook, app.policy, api routes. Generate new modules under backend/app and small api route additions under backend/api where needed. New code should:
- be typed, async-friendly, and import-light (avoid heavy imports at module top),
- integrate with existing observability.log_event for structured logs,
- use Neon pgvector for memory (rag.helpers already exist),
- include docstrings and short usage examples,
- include TODOs for Vertex SDK-specific code where necessary.
Do not generate tests here. Return only the set of prompts below; after running them you will have the files to implement the features.

# 01 — context_compaction.py
Prompt:
"Generate `backend/app/context_compaction.py`. Implement:
- a Pydantic model `ConversationChunk` with fields `messages: list[str]`, `summary: str | None`, `created_at: datetime`.
- async function `compact_context(messages: list[str], max_tokens: int = 1500) -> str` that:
  - when length(tokens) <= max_tokens returns joined messages,
  - otherwise calls a compacting LLM function placeholder `await compact_via_gemini(messages, max_tokens)` (include TODO comment to replace with real Vertex/Gemini call), returning a short summary paragraph,
  - logs compaction events via observability.log_event with original length and compacted length,
  - caches summary in Redis via app.db cache helper (cache key based on hashed conversation),
  - returns the string summary,
- helper `summarize_if_needed(session_id: str, messages: list[str])` that checks Redis for existing summary and only recomputes if stale,
- include docstring and minimal synchronous fallback that returns truncated joined messages if LLM not available."
# 02 — memory_bank.py (pgvector retrieval + logging)
Prompt:
"Generate `backend/app/memory_bank.py`. Implement:
- Pydantic model `MemoryItem` {id:str, text:str, embedding: list[float], metadata: dict, created_at: datetime}
- async function `store_memory(item: MemoryItem) -> None` that inserts into Neon pgvector table `memories` (provide SQL example and use app.db.get_pg_conn()),
- async function `retrieve_similar(text: str, k: int = 5) -> list[MemoryItem]` that:
  - uses rag.embed_text to get embedding (call rag.embed_text placeholder),
  - queries pgvector nearest neighbors ORDER BY embedding <-> query LIMIT k,
  - returns list of MemoryItem, and logs retrieval event with observability.log_event including trace_id if provided,
- async function `log_memory_usage(trace_id: str, query: str, results: list[dict])` that writes telemetry row to Redis and Cloud Logging,
- include safe fallbacks if DB is unavailable (return empty list) and docstrings for schema and usage."

# 03 — built_in_tools_demo.py (Vertex built-ins demo)
Prompt:
"Generate `backend/app/built_in_tools_demo.py`. Implement:
- functions that demonstrate calling built-in Vertex tools (Search and Code Execution) as stubs:
  - async def `vertex_search_demo(query: str) -> dict` that contains:
    - a placeholder call to Vertex Search (commented TODO with sample Vertex API pseudocode),
    - returns a mocked list of search results if Vertex not available,
    - logs the query and number of results via observability.log_event,
  - async def `vertex_code_exec_demo(code_snippet: str, language: str = 'bash') -> dict` that:
    - runs a sandboxed simulator (no real execution) and returns a mocked output or error,
    - includes TODO to replace with proper Vertex Code Execution tool if you enable it,
    - logs execution request and returns {'stdout': '...', 'stderr': '...', 'exit_code': 0} or a simulated error.
- These functions should be registered via tools_adk.register_adk_tool in an example commented block for optional exposure to agents."

# 04 — agent_evaluation.py (metrics & evaluation harness)
Prompt:
"Generate `backend/app/agent_evaluation.py`. Implement:
- Pydantic model `EvaluationResult` {metric:str, value:float, details:dict}
- in-memory metrics store (simple asyncio-safe dict + counters) and Redis-backed persistence helper
- functions:
  - `record_metric(name: str, value: float, labels: dict | None = None)` that increments counters / records last value and pushes an event to observability.log_event,
  - `evaluate_runbook_quality(runbook: dict, reference_good: dict | None = None) -> EvaluationResult` that implements lightweight heuristics (steps_count, avg_step_length, presence_of_forbidden_phrases) and returns an EvaluationResult; also store evaluation in Redis and call record_metric for 'runbook_quality',
  - `get_metrics_snapshot() -> dict` that returns recent metrics for dashboard consumption,
- include docstring for how notebook can pull these metrics and produce plots, and include TODO to expand with offline human evaluation or automated safety scoring."

# 05 — long_running_manager.py (pause/resume, background tasks)
Prompt:
"Generate `backend/app/long_running_manager.py`. Implement:
- a manager class `LongRunningManager` with:
  - internal registry of jobs: Dict[job_id:str, dict{status, created_at, last_update, result}],
  - async method `start_job(coro: Coroutine, job_id: Optional[str] = None) -> str` that schedules a background task (asyncio.create_task) and stores job metadata,
  - async method `pause_job(job_id: str)`, `resume_job(job_id: str)` that simulate pause/resume by cooperating with task (provide a simple cooperative pause mechanism using asyncio.Event flags and provide example wrapper `cooperative_task_wrapper` that checks event flags between steps),
  - async method `get_job_status(job_id: str)` returning job metadata,
  - method `cancel_job(job_id: str)` to cancel task,
- usage example: how simulate_runbook steps can be turned into a job so frontend can call /jobs/{id}/pause and /jobs/{id}/resume via new API routes (include recommended API endpoints in docstring),
- log all job transitions via observability.log_event and persist minimal state to Redis for crash recovery."

# 06 — api routes additions (routes_memory, routes_metrics, routes_jobs)
Prompt:
"Generate `backend/api/routes_extra.py`. Create an APIRouter with:
- GET /memory/search?q=... -> calls memory_bank.retrieve_similar and returns results (requires trace_id optional header),
- GET /metrics -> returns get_metrics_snapshot (agent_evaluation.get_metrics_snapshot),
- POST /jobs/start -> accepts job payload (e.g., runbook steps or incident) and calls LongRunningManager.start_job returning job_id,
- POST /jobs/{id}/pause and /jobs/{id}/resume -> call pause_job/resume_job,
- GET /jobs/{id} -> return job status,
- ensure responses use Pydantic models and log operations via observability.log_event,
- include short OpenAPI docstrings and example payloads."

# 07 — integration notes & small wiring patch prompt
Prompt:
"Generate a short patch/instructions snippet to add to `backend/api/main.py` startup event:
- import context_compaction, memory_bank, adk_registration (if exists), built_in_tools_demo, agent_evaluation, long_running_manager,
- initialize LongRunningManager as app.state.long_running_manager,
- ensure adk_registration is imported to register tools,
- wire a periodic compaction cron (simple asyncio.create_task on startup that calls summary compaction for active sessions every X minutes using app.state),
- include TODOs to plug Vertex credentials and to expose metrics endpoint to frontend.",
Output the exact code snippet to paste into main.py startup event (do not rewrite entire main.py)."
