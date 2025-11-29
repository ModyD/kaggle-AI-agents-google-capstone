"""
FastAPI main application.

Enterprise Security Incident Triage & Autonomous Runbook Agent API.

This application provides:
- Incident triage using rule-based scoring
- LLM-powered explanations (Gemini via LangChain)
- RAG-enhanced runbook generation
- Safety policy verification
- Runbook simulation
- A2A protocol orchestration

All endpoints are designed as OpenAPI tools for Vertex Agent Builder integration.
"""

import os
import sys
from contextlib import asynccontextmanager
from typing import Any

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

# Add backend directory to path for imports
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.config import get_settings
from app.core.db import close_pg_pool, close_redis, init_pg_pool
from app.core.observability import (
    configure_logging,
    get_logger,
    log_event,
    set_trace_id,
    setup_cloud_logging,
)

# Import routers from api package
from api.routes_triage import router as triage_router
from api.routes_explain import router as explain_router
from api.routes_runbook import router as runbook_router
from api.routes_policy import router as policy_router
from api.routes_simulate import router as simulate_router
from api.routes_flow import router as flow_router
from api.routes_health import router as health_router
from api.routes_mcp import router as mcp_router
from api.routes_extra import router as extra_router


# =============================================================================
# Application Lifespan
# =============================================================================


@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    Application lifespan handler.

    Handles startup and shutdown events for:
    - Database connection pool
    - Redis client
    - Cloud Logging
    """
    logger = get_logger("main")

    # Startup
    logger.info("Starting application...")

    # Configure logging
    configure_logging()

    # Try to set up Cloud Logging
    setup_cloud_logging()

    # Initialize database pool
    try:
        await init_pg_pool()
        logger.info("Database pool initialized")
    except Exception as e:
        logger.warning(f"Database initialization failed: {e}")

    # Initialize LongRunningManager and store in app state
    try:
        from app.orchestration.long_running_manager import LongRunningManager
        app.state.long_running_manager = LongRunningManager()
        logger.info("LongRunningManager initialized")
    except Exception as e:
        logger.warning(f"LongRunningManager initialization failed: {e}")

    # Register Vertex AI demo tools (optional)
    try:
        from app.orchestration.built_in_tools_demo import register_vertex_tools
        register_vertex_tools()
        logger.info("Vertex demo tools registered")
    except Exception as e:
        logger.debug(f"Vertex tools registration skipped: {e}")

    # TODO: Start periodic context compaction task
    # async def periodic_compaction():
    #     while True:
    #         await asyncio.sleep(300)  # Every 5 minutes
    #         # Compact active sessions
    # asyncio.create_task(periodic_compaction())

    # TODO: Restore metrics from Redis on startup
    # from app.services.agent_evaluation import restore_metrics_from_redis
    # await restore_metrics_from_redis()

    logger.info("Application startup complete")

    yield

    # Shutdown
    logger.info("Shutting down application...")

    # Close database pool
    try:
        await close_pg_pool()
    except Exception as e:
        logger.warning(f"Database shutdown error: {e}")

    # Close Redis
    try:
        close_redis()
    except Exception as e:
        logger.warning(f"Redis shutdown error: {e}")

    logger.info("Application shutdown complete")


# =============================================================================
# Application Factory
# =============================================================================


def create_app() -> FastAPI:
    """
    Create and configure the FastAPI application.

    Returns:
        Configured FastAPI instance
    """
    settings = get_settings()

    app = FastAPI(
        title=settings.app_name,
        description="""
## Enterprise Security Incident Triage & Autonomous Runbook Agent

This API provides OpenAPI tools for the Vertex Agent Builder and frontend,
implementing a multi-agent system for security incident response.

### Agents

- **Triage Agent**: Rule-based incident scoring with explainable contributions
- **Explain Agent**: LLM-powered natural language explanations
- **Runbook Agent**: RAG-enhanced response step generation
- **Policy Agent**: Safety verification and sanitization
- **Simulator Agent**: Runbook execution preview

### Key Features

- A2A (Agent-to-Agent) protocol for inter-agent communication
- Distributed tracing with trace IDs
- Pydantic-validated LLM outputs
- Cloud Run deployment ready

### Getting Started

1. Try `/triage/examples` to see sample incident features
2. POST to `/triage` to score an incident
3. POST to `/flow/simulate` to run the full agent pipeline
        """,
        version=settings.app_version,
        lifespan=lifespan,
        docs_url="/docs",
        redoc_url="/redoc",
        openapi_url="/openapi.json",
    )

    # Configure CORS
    origins = [
        settings.frontend_url,
        "http://localhost:3000",
        "http://localhost:8080",
        "http://127.0.0.1:3000",
        "http://127.0.0.1:8080",
    ]

    app.add_middleware(
        CORSMiddleware,
        allow_origins=origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # Register routers
    app.include_router(health_router)
    app.include_router(triage_router)
    app.include_router(explain_router)
    app.include_router(runbook_router)
    app.include_router(policy_router)
    app.include_router(simulate_router)
    app.include_router(flow_router)
    app.include_router(mcp_router)
    app.include_router(extra_router)

    # Add middleware for trace ID propagation
    @app.middleware("http")
    async def trace_middleware(request: Request, call_next):
        """Propagate or generate trace ID for each request."""
        from uuid import uuid4

        # Get trace ID from header or generate new one
        trace_id = request.headers.get("X-Trace-ID", uuid4().hex)
        set_trace_id(trace_id)

        # Log request
        log_event(
            "request_start",
            {
                "method": request.method,
                "path": str(request.url.path),
                "query": str(request.query_params),
            },
            trace_id=trace_id,
        )

        response = await call_next(request)

        # Add trace ID to response headers
        response.headers["X-Trace-ID"] = trace_id

        return response

    # Global exception handler
    @app.exception_handler(Exception)
    async def global_exception_handler(request: Request, exc: Exception):
        """Handle uncaught exceptions."""
        logger = get_logger("main")
        logger.exception(f"Unhandled exception: {exc}")

        return JSONResponse(
            status_code=500,
            content={
                "detail": "Internal server error",
                "error_type": type(exc).__name__,
            },
        )

    return app


# =============================================================================
# Application Instance
# =============================================================================

app = create_app()


# =============================================================================
# Development Server
# =============================================================================

if __name__ == "__main__":
    import uvicorn

    settings = get_settings()

    uvicorn.run(
        "app.main:app",
        host=settings.host,
        port=settings.port,
        reload=settings.debug,
        log_level="info",
    )
