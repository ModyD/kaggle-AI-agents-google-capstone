"""
API package initialization.

This module exports all route routers for mounting in the main app.
"""

from .routes_triage import router as triage_router
from .routes_explain import router as explain_router
from .routes_runbook import router as runbook_router
from .routes_policy import router as policy_router
from .routes_simulate import router as simulate_router
from .routes_flow import router as flow_router
from .routes_health import router as health_router

__all__ = [
    "triage_router",
    "explain_router",
    "runbook_router",
    "policy_router",
    "simulate_router",
    "flow_router",
    "health_router",
]
