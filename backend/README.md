# Enterprise Security Incident Triage & Autonomous Runbook Agent

A sophisticated AI-powered security incident response system built for the **Kaggle 5-Day AI Agents Intensive Course Capstone** (Enterprise Agents track). This backend demonstrates multi-agent orchestration, automated runbook generation, and human-in-the-loop safety controls.

## 🎯 Competition Concepts Demonstrated

| Concept                | Implementation                                            |
| ---------------------- | --------------------------------------------------------- |
| **Multi-Agent System** | Orchestrated Triage → Explain → Runbook → Simulate agents |
| **Tool Use**           | LLM chains with structured Pydantic output parsing        |
| **MCP Protocol**       | Google ADK-style envelope format for tool invocation      |
| **Sessions & Memory**  | Redis-backed session state, A2A message timeline          |
| **Observability**      | Structured JSON logging, trace IDs, LangSmith-ready       |
| **A2A Protocol**       | Custom agent-to-agent JSON messaging format               |
| **Deployment**         | Docker + Cloud Run optimized configuration                |

## 🏗️ Architecture

```
   ┌───────────────────────────────────────────────────────────────────┐
   │                        Frontend (Next.js/Vercel)                  │
   └───────────────────────────────────────────────────────────────────┘
                                    │
                                    ▼
┌────────────────────────────────────────────────────────────────────────┐
│                     FastAPI Backend (Cloud Run)                        │
│  ┌─────────────┐   ┌─────────────┐   ┌─────────────┐   ┌─────────────┐ │
│  │   Triage    │─▶│   Explain   │─▶│   Runbook   │─▶│  Simulate   │ │
│  │   Agent     │   │   Agent     │   │   Agent     │   │   Agent     │ │
│  └─────────────┘   └─────────────┘   └─────────────┘   └─────────────┘ │
│         │                │                  │                │         │
│         ▼                ▼                  ▼                ▼         │
│  ┌─────────────────────────────────────────────────────────────────┐   │
│  │                    A2A Orchestrator                             │   │
│  │              (Timeline + Message Logging)                       │   │
│  └─────────────────────────────────────────────────────────────────┘   │
└────────────────────────────────────────────────────────────────────────┘
         │                                              │
         ▼                                              ▼
┌─────────────────────┐                    ┌─────────────────────────┐
│  Neon PostgreSQL    │                    │   Upstash Redis         │
│  (pgvector / RAG)   │                    │   (Sessions/Cache)      │
└─────────────────────┘                    └─────────────────────────┘
```

## 📁 Project Structure

```
backend/
├── app/                    # Core application modules
│   ├── __init__.py
│   ├── config.py          # Settings management (pydantic-settings)
│   ├── models.py          # Pydantic v2 data models
│   ├── triage.py          # Rule-based scoring engine
│   ├── explain.py         # LLM explanation generation
│   ├── runbook.py         # RAG-enhanced runbook generation
│   ├── rag.py             # Vector similarity search
│   ├── policy.py          # Safety verification & rewriting
│   ├── simulate.py        # Runbook execution simulation
│   ├── db.py              # Database connections (Neon + Redis)
│   ├── a2a.py             # Agent-to-agent orchestration
│   ├── chains.py          # LangChain Gemini integration
│   ├── observability.py   # Structured logging & metrics
│   ├── mcp_adk.py         # MCP envelope handler (ADK compatible)
│   ├── tools_adk.py       # Tool registry with @adk_tool decorator
│   └── main.py            # FastAPI application factory
├── api/                    # Route handlers
│   ├── __init__.py
│   ├── routes_triage.py   # POST /triage
│   ├── routes_explain.py  # POST /explain
│   ├── routes_runbook.py  # POST /runbook
│   ├── routes_policy.py   # POST /policy/check, POST /policy/rewrite
│   ├── routes_simulate.py # POST /simulate
│   ├── routes_flow.py     # POST /flow/simulate
│   ├── routes_mcp.py      # MCP endpoints (/mcp/invoke, /mcp/tools)
│   └── routes_health.py   # GET /health, GET /ready
├── tests/                  # Pytest test suite
│   ├── conftest.py
│   ├── test_triage_policy.py
│   ├── test_a2a_flow.py
│   ├── test_runbook_stub.py
│   └── test_mcp_adk.py    # MCP integration tests
├── Dockerfile             # Cloud Run optimized multi-stage build
├── cloudrun_deploy.sh     # Deployment script with smoke tests
├── pyproject.toml         # Project config & dependencies (uv)
├── requirements.txt       # Fallback pip dependencies
└── README.md              # This file
```

## 🚀 Quick Start

### Prerequisites

- Python 3.11+
- [uv](https://docs.astral.sh/uv/) (recommended) or pip
- Docker (for containerized deployment)
- Google Cloud SDK (for Cloud Run deployment)
- Access to Gemini API (or use stub mode)

### Local Development (using uv)

1. **Clone and navigate:**

   ```bash
   cd backend
   ```

2. **Install uv (if not already installed):**

   ```bash
   curl -LsSf https://astral.sh/uv/install.sh | sh
   ```

3. **Create venv and install dependencies:**

   ```bash
   uv sync
   ```

4. **Set environment variables:**

   ```bash
   cp .env.example .env
   # Edit .env with your configuration
   ```

5. **Run the development server:**

   ```bash
   # Stub mode (no external services required)
   USE_STUB_LLM=true uv run uvicorn app.main:app --reload --port 8080

   # Full mode (requires Vertex AI, Neon, Redis)
   uv run uvicorn app.main:app --reload --port 8080
   ```

6. **View API documentation:**
   - Swagger UI: http://localhost:8080/docs
   - ReDoc: http://localhost:8080/redoc

### Running Tests

```bash
# Run all tests
USE_STUB_LLM=true uv run pytest tests/ -v

# Run with coverage
USE_STUB_LLM=true uv run pytest tests/ -v --cov=app --cov=api --cov-report=term-missing

# Install dev dependencies first (if needed)
uv sync --dev
```

## 🔧 Configuration

### Environment Variables

| Variable                | Description                  | Default                 |
| ----------------------- | ---------------------------- | ----------------------- |
| `DEBUG`                 | Enable debug mode            | `false`                 |
| `USE_STUB_LLM`          | Use mock LLM responses       | `false`                 |
| `FRONTEND_URL`          | CORS allowed origin          | `http://localhost:3000` |
| `GOOGLE_CLOUD_PROJECT`  | GCP project ID               | -                       |
| `GOOGLE_CLOUD_LOCATION` | GCP region                   | `us-central1`           |
| `GEMINI_MODEL_NAME`     | Gemini model                 | `gemini-1.5-flash`      |
| `NEON_DATABASE_URL`     | PostgreSQL connection string | -                       |
| `UPSTASH_REDIS_URL`     | Redis connection URL         | -                       |
| `UPSTASH_REDIS_TOKEN`   | Redis auth token             | -                       |
| `LANGCHAIN_TRACING_V2`  | Enable LangSmith tracing     | `false`                 |
| `LANGCHAIN_API_KEY`     | LangSmith API key            | -                       |

### Stub Mode

For local development without external services, enable stub mode:

```bash
USE_STUB_LLM=true uvicorn app.main:app --reload
```

This provides:

- Mock LLM responses for explain/runbook generation
- Simulated triage scoring
- In-memory session storage
- Deterministic test outputs

## 📡 API Endpoints

### Core Endpoints

| Method | Endpoint         | Description                                      |
| ------ | ---------------- | ------------------------------------------------ |
| `POST` | `/triage`        | Analyze incident features, return severity score |
| `POST` | `/explain`       | Generate natural language explanation            |
| `POST` | `/runbook`       | Create remediation runbook steps                 |
| `POST` | `/simulate`      | Simulate runbook execution                       |
| `POST` | `/flow/simulate` | Full orchestrated workflow                       |

### Utility Endpoints

| Method | Endpoint          | Description             |
| ------ | ----------------- | ----------------------- |
| `GET`  | `/health`         | Health check            |
| `GET`  | `/ready`          | Readiness probe         |
| `POST` | `/policy/check`   | Verify runbook safety   |
| `POST` | `/policy/rewrite` | Rewrite unsafe commands |

### Example Requests

**Triage Incident:**

```bash
curl -X POST http://localhost:8080/triage \
  -H "Content-Type: application/json" \
  -d '{"features": {"failed_logins_last_hour": 100, "suspicious_file_activity": true}}'
```

**Full Flow Simulation:**

```bash
curl -X POST http://localhost:8080/flow/simulate \
  -H "Content-Type: application/json" \
  -d '{
    "incident_id": "INC-2024-001",
    "features": {
      "failed_logins_last_hour": 50,
      "process_spawn_count": 150,
      "bytes_exfiltrated_mb": 500
    }
  }'
```

## 🚢 Deployment

### Docker Build

```bash
# Build locally
docker build -t security-agent .

# Run container
docker run -p 8080:8080 \
  -e USE_STUB_LLM=true \
  -e DEBUG=true \
  security-agent
```

### Cloud Run Deployment

1. **Set up GCP credentials:**

   ```bash
   gcloud auth login
   gcloud config set project YOUR_PROJECT_ID
   ```

2. **Deploy using the script:**

   ```bash
   chmod +x cloudrun_deploy.sh
   PROJECT_ID=your-project-id ./cloudrun_deploy.sh
   ```

3. **Or deploy manually:**

   ```bash
   # Build and push
   gcloud builds submit --tag gcr.io/PROJECT_ID/security-agent

   # Deploy
   gcloud run deploy security-agent \
     --image gcr.io/PROJECT_ID/security-agent \
     --platform managed \
     --region us-central1 \
     --allow-unauthenticated
   ```

## 🔍 Observability

### Structured Logging

All logs are JSON-formatted for easy parsing:

```json
{
  "timestamp": "2024-01-15T10:30:00Z",
  "level": "INFO",
  "message": "Triage completed",
  "trace_id": "abc123",
  "incident_id": "INC-001",
  "severity": "CRITICAL",
  "score": 85.5
}
```

### LangSmith Integration

Enable tracing for LLM debugging:

```bash
LANGCHAIN_TRACING_V2=true \
LANGCHAIN_API_KEY=your-key \
uvicorn app.main:app
```

## 🛡️ Safety Features

### Policy Checking

The `/policy/check` endpoint validates runbook steps:

- **Forbidden patterns**: `rm -rf /`, `DROP DATABASE`, etc.
- **Dangerous commands**: Unrestricted `sudo`, wildcards
- **Data exfiltration**: Unauthorized `curl`, `wget` to external hosts

### Automatic Rewriting

Unsafe commands are automatically rewritten to safer alternatives:

```
rm -rf /var/log/*  →  rm -rf /var/log/*.tmp (with backup)
```

## 🧪 Testing Strategy

| Test Type   | Location                      | Coverage               |
| ----------- | ----------------------------- | ---------------------- |
| Unit Tests  | `tests/test_triage_policy.py` | Scoring, policy checks |
| Integration | `tests/test_a2a_flow.py`      | Agent orchestration    |
| Stub Tests  | `tests/test_runbook_stub.py`  | LLM mock responses     |

## 🔌 MCP (Google ADK Style)

### Overview

This backend implements the **Model Context Protocol (MCP)** envelope format, compatible with Google's Agent Development Kit (ADK). This matches the patterns demonstrated in the [Kaggle 5-Day AI Agents Course](https://www.kaggle.com/learn-guide/5-day-genai-intensive-course) (Day 2b) and the [Google Cloud ADK + MCP blog](https://cloud.google.com/blog/topics/developers-practitioners/use-google-adk-and-mcp-with-an-external-server).

**Why MCP?**

- Standardized tool invocation format for multi-agent systems
- Compatible with ADK's `MCPToolset.from_server()` for seamless integration
- Supports distributed tracing via `trace_id` propagation
- Automatic secret redaction in logs and responses

### MCP Endpoints

| Method | Endpoint            | Description                    |
| ------ | ------------------- | ------------------------------ |
| `POST` | `/mcp/invoke`       | Invoke a tool via MCP envelope |
| `POST` | `/mcp/invoke/batch` | Batch invoke multiple tools    |
| `GET`  | `/mcp/tools`        | List registered tools          |
| `GET`  | `/mcp/tool/{name}`  | Get specific tool info         |
| `GET`  | `/mcp/health`       | MCP subsystem health check     |

### MCP Envelope Format

**Request (what ADK would POST):**

```json
{
  "id": "550e8400-e29b-41d4-a716-446655440000",
  "tool_name": "triage",
  "inputs": {
    "features": {
      "failed_logins_last_hour": 50,
      "distinct_source_ips": 10,
      "after_hours": true,
      "is_privileged_account": true,
      "geo_anomaly_score": 0.9
    }
  },
  "from_agent": "orchestrator-agent",
  "to_agent": "triage-agent",
  "trace_id": "trace-abc-123",
  "metadata": {
    "priority": "high",
    "source": "security-monitor"
  },
  "timeout_ms": 30000
}
```

**Response:**

```json
{
  "id": "550e8400-e29b-41d4-a716-446655440000",
  "status": "ok",
  "result": {
    "label": "HIGH",
    "score": 7,
    "contribs": [
      ["failed_logins_last_hour", 3],
      ["geo_anomaly_score", 2],
      ["is_privileged_account", 2]
    ]
  },
  "error": null,
  "trace_id": "trace-abc-123",
  "elapsed_ms": 1.25
}
```

### Example curl Commands

```bash
# List available tools
curl -s http://localhost:8080/mcp/tools

# Check MCP health
curl -s http://localhost:8080/mcp/health

# Invoke triage tool
curl -s -X POST http://localhost:8080/mcp/invoke \
  -H "Content-Type: application/json" \
  -d '{"id":"test-1","tool_name":"triage","inputs":{"features":{"failed_logins_last_hour":50}}}'

# Invoke explain tool
curl -s -X POST http://localhost:8080/mcp/invoke \
  -H "Content-Type: application/json" \
  -d '{"id":"test-2","tool_name":"explain","inputs":{"features":{"failed_logins_last_hour":50},"triage_result":{"label":"MEDIUM","score":3}}}'
```

### Registered Tools

| Tool           | Input Key                             | Description                          |
| -------------- | ------------------------------------- | ------------------------------------ |
| `triage`       | `features`                            | Score incident severity (rule-based) |
| `explain`      | `features`, `triage_result`           | Generate explanation (LLM)           |
| `runbook`      | `features`, `explanation`, `severity` | Generate runbook (LLM+RAG)           |
| `policy_check` | `runbook`                             | Verify runbook safety                |
| `simulate`     | `runbook`                             | Simulate runbook execution           |

### Registering Custom Tools

```python
from app.tools_adk import adk_tool, register_adk_tool, wrap_sync

# Option 1: Decorator for async functions
@adk_tool("my_async_tool")
async def my_tool(inputs: dict, context: dict) -> dict:
    return {"result": inputs["value"] * 2}

# Option 2: Wrap sync functions
def my_sync_function(data: dict) -> dict:
    return {"processed": data["input"]}

register_adk_tool("my_sync_tool", wrap_sync(my_sync_function))
```

### Security Best Practices

#### Secret Redaction

The MCP layer automatically redacts sensitive keys from logs and responses:

- Keys containing: `token`, `secret`, `password`, `key`, `credential`, `auth`
- Redacted values appear as `[REDACTED]`

#### Production Recommendations

1. **Never expose service account JSON files** - Use workload identity or mounted secrets
2. **Use Google Secret Manager** for API keys and credentials:

   ```bash
   # Store secret
   echo -n "your-api-key" | gcloud secrets create gemini-api-key --data-file=-

   # Access in Cloud Run (auto-mounted)
   gcloud run services update security-agent \
     --set-secrets=GEMINI_API_KEY=gemini-api-key:latest
   ```

3. **Enable VPC Service Controls** for network isolation
4. **Set appropriate IAM roles** - Principle of least privilege
5. **Enable Cloud Audit Logs** for compliance tracking

#### Environment Variables (Production)

```bash
# Required for production
GOOGLE_CLOUD_PROJECT=your-project-id
GOOGLE_CLOUD_LOCATION=us-central1

# Use Secret Manager references (not plaintext)
# These are mounted automatically in Cloud Run
NEON_DATABASE_URL=projects/*/secrets/neon-db-url/versions/latest
UPSTASH_REDIS_URL=projects/*/secrets/redis-url/versions/latest
```

## 📚 Competition Submission

This project is submitted for the **Enterprise Agents** track:

- **Use Case**: Automated security incident triage and response
- **Agents**: Multi-agent pipeline with specialized roles
- **Human-in-the-Loop**: Policy verification before execution
- **Observability**: Full trace logging for audit compliance

## 📄 License

MIT License - See LICENSE file for details.

---

Built with ❤️ for the Kaggle 5-Day AI Agents Intensive Course with Google
