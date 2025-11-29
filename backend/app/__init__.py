"""
Enterprise Security Incident Triage & Autonomous Runbook Agent - Backend App

This package contains the core business logic for the security incident
triage and runbook generation system.

Package Structure:
    app/
    ├── core/           - Infrastructure (db, observability)
    ├── agents/         - Agent modules (triage, explain, runbook, policy, simulate)
    ├── services/       - Business logic (chains, rag, memory, evaluation)
    ├── orchestration/  - Orchestration & protocols (a2a, mcp, tools)
    ├── config.py       - Settings management
    ├── models.py       - Pydantic data models
    └── main.py         - FastAPI application

Import Paths:
    Use new paths like:
    - from app.agents.triage import score_incident
    - from app.services.chains import get_stub_runbook
    - from app.orchestration.a2a import orchestrate_flow
    - from app.core.db import init_pg_pool
"""

__version__ = "0.1.0"

# Subpackages available for import
from app import core, agents, services, orchestration
from app import config, models
