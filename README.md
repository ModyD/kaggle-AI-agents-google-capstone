# 🛡️ Enterprise Security Incident Triage & Autonomous Runbook Agent

[![Cloud Run](https://img.shields.io/badge/Cloud%20Run-Live-green?logo=google-cloud)](https://incident-triage-agent-226861216522.us-central1.run.app)
[![API Docs](https://img.shields.io/badge/API-Docs-blue?logo=swagger)](https://incident-triage-agent-226861216522.us-central1.run.app/docs)

A sophisticated AI-powered security incident response system built for the **Kaggle 5-Day AI Agents Intensive Course Capstone** (Enterprise Agents track).

## 🌐 Live Deployment

| Service               | URL                                                                   |
| --------------------- | --------------------------------------------------------------------- |
| **Backend API**       | https://incident-triage-agent-226861216522.us-central1.run.app        |
| **API Documentation** | https://incident-triage-agent-226861216522.us-central1.run.app/docs   |
| **Health Check**      | https://incident-triage-agent-226861216522.us-central1.run.app/health |

## 📋 Kaggle Capstone Feature Checklist

**Requirement:** At least 3 features must be implemented ✅ **We have 10!**

| #   | Feature                                  | Status | Implementation                                          |
| --- | ---------------------------------------- | ------ | ------------------------------------------------------- |
| 1   | **Multi-Agent Orchestration**            | ✅     | Triage → Explain → Runbook → Policy → Simulate pipeline |
| 2   | **Tool Use / Function Calling**          | ✅     | `@adk_tool` decorator, structured tool registry         |
| 3   | **MCP Protocol**                         | ✅     | Google ADK-style envelope format                        |
| 4   | **Sessions & Memory**                    | ✅     | Redis-backed session state, A2A message timeline        |
| 5   | **RAG (Retrieval Augmented Generation)** | ✅     | pgvector similarity search for runbooks                 |
| 6   | **Agentic Loops**                        | ✅     | Iterative agent pipeline with flow control              |
| 7   | **Agent Evaluation**                     | ✅     | Metrics & evaluation framework                          |
| 8   | **Observability / Tracing**              | ✅     | Structured JSON logging, trace IDs, LangSmith-ready     |
| 9   | **Human-in-the-Loop**                    | ✅     | Safety checks, command rewriting, approval gates        |
| 10  | **Deployment**                           | ✅     | Live on Google Cloud Run                                |

## 🎯 What It Does

This multi-agent system automates security incident response:

1. **Triage Agent** - Scores incident severity (LOW/MEDIUM/HIGH/CRITICAL)
2. **Explain Agent** - Generates human-readable explanations via Gemini LLM
3. **Runbook Agent** - Creates step-by-step remediation runbooks using RAG
4. **Policy Agent** - Validates commands against security policies
5. **Simulate Agent** - Dry-runs remediation steps safely

## 🏗️ Architecture

```
┌─────────────────────────────────────────────────────────────────────┐
│                        Frontend (Next.js/Vercel)                    │
└─────────────────────────────────────────────────────────────────────┘
                                    │
                                    ▼
┌─────────────────────────────────────────────────────────────────────┐
│                     FastAPI Backend (Cloud Run)                     │
│  ┌─────────────┐   ┌─────────────┐   ┌─────────────┐   ┌──────────┐ │
│  │   Triage    │─▶│   Explain   │─▶│   Runbook   │─▶│ Simulate │ │
│  │   Agent     │   │   Agent     │   │   Agent     │   │  Agent   │ │
│  └─────────────┘   └─────────────┘   └─────────────┘   └──────────┘ │
│         │                │                 │                │       │
│         │                │       ┌─────────┴────────┐       │       │
│         │                │       │   Policy Agent   │       │       │
│         │                │       │  (Safety Check)  │       │       │
│         │                │       └──────────────────┘       │       │
│         ▼                ▼                 ▼                ▼       │
│  ┌─────────────────────────────────────────────────────────────┐    │
│  │                      A2A Orchestrator                       │    │
│  │              (Timeline + Message Logging)                   │    │
│  └─────────────────────────────────────────────────────────────┘    │
└─────────────────────────────────────────────────────────────────────┘
         │                                              │
         ▼                                              ▼
┌─────────────────────┐                    ┌─────────────────────────┐
│  Neon PostgreSQL    │                    │   Upstash Redis         │
│  (pgvector / RAG)   │                    │   (Sessions/Cache)      │
└─────────────────────┘                    └─────────────────────────┘
```

## 🚀 Quick Start

### Try the API

```bash
# Health check
curl https://incident-triage-agent-226861216522.us-central1.run.app/health

# Triage an incident
curl -X POST https://incident-triage-agent-226861216522.us-central1.run.app/triage \
  -H "Content-Type: application/json" \
  -d '{"features": {"failed_logins_last_hour": 50, "suspicious_file_activity": true}}'
```

### Local Development

```bash
cd backend
uv sync
uv run uvicorn app.main:app --reload --port 8080
```

See [backend/README.md](backend/README.md) for full documentation.

## 📁 Project Structure

```
├── backend/          # FastAPI backend (Python 3.11+)
│   ├── app/          # Core application
│   ├── api/          # Route handlers
│   ├── tests/        # 75+ pytest tests
│   └── Dockerfile    # Cloud Run deployment
├── frontend/         # Next.js frontend (coming soon)
├── notebooks/        # Jupyter notebooks for experimentation
└── infra/            # Database migrations
```

## 🛠️ Tech Stack

- **Backend:** FastAPI, Pydantic v2, LangChain
- **LLM:** Google Gemini (Vertex AI) (default: gemini-3-pro-preview)
- **Agent Orchestration:** Google ADK
- **Database:** Neon PostgreSQL + pgvector
- **Cache:** Upstash Redis
- **Deployment:** Google Cloud Run
- **Package Manager:** uv



## 📄 License

MIT License - see LICENSE file for details.
