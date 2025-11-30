---
agent: agent
model: Claude Opus 4.5 (Preview) (copilot)
---
You are generating a full Kaggle competition writeup notebook for the project in notebooks folder called same as below with .ipynb extension.:

**Enterprise Incident Triage & Runbook Synthesizer Agent**

This notebook must follow the structure and tone of the reference:
    notebooks/example-writeup/sentinels-multimodal-disaster-intelligence-agent.ipynb

But everything should be adapted to my actual project:  
    A multi-agent, MCP-powered, LLM-powered incident triage and runbook synthesis system 
    with Cloud Run backend, Next.js frontend (in progress), Neon Postgres, Upstash Redis,
    and Vertex AI (Gemini) for RAG+explanations.


========================================================
🎯  GENERATE A NEW NOTEBOOK AT:
    notebooks/incident-triage-ai-agent.ipynb
========================================================
The notebook must satisfy Kaggle writeup requirements:

TITLE, SUBTITLE, CARD IMAGE  
MEDIA GALLERY (optional placeholder)  
PROJECT DESCRIPTION (<1500 words)  
ATTACHMENTS: links to GitHub repo + project structure  
CODE CELLS: small, modular demos proving competency with ADK, MCP, multi-agent flows, RAG, memory, evaluation metrics.

project description:
========================================================
### Problem Statement -- the problem you're trying to solve, and why you think it's an important or interesting problem to solve

### Why agents? -- Why are agents the right solution to this problem

### What you created -- What's the overall architecture? 

### Demo -- Show your solution 

### The Build -- How you created it, what tools or technologies you used.

### If I had more time, this is what I'd do

========================================================
📌  NOTEBOOK STRUCTURE (FOLLOW EXACTLY)
========================================================

1. **Cover Page**
   - Big title cell: “Enterprise Incident Triage & Runbook Synthesizer Agent”
   - Subtitle: “A Multi-Agent, MCP-Driven AI System for Operational Incident Response”
   - Placeholder cell for hero image:
       (Markdown): “![PROJECT HERO IMAGE — insert later](PLACEHOLDER_IMAGE_URL)”
   - Short description (2–3 lines)

2. **Media Gallery Placeholder**
   - Markdown section with:  
     “Video Demo (optional)” and placeholder Markdown link
     “Images & Architecture Diagrams (to be added)”

3. **Problem Statement**
   - Clear explanation of:
        - noisy operational alerts
        - slow triage cycles
        - manual runbook creation
        - operational risk due to human fatigue
        - need for safe automated remediation steps
   - Keep <200 words

4. **Our Proposed Solution**
   - Describe the multi-agent system:
        - Triage Agent (heuristic)
        - Explain Agent (Gemini)
        - Runbook Agent (RAG + Gemini)
        - Safety/Policy Agent
        - Simulation Agent
        - Orchestrator (A2A sequential/parallel)
   - Mention MCP tools exposed
   - Mention ADK usage
   - Show a concise system diagram (ASCII or placeholder image)

5. **Architecture Overview**
   - Include diagram placeholders:
       - High-level system architecture
       - Backend architecture (FastAPI + MCP server)
       - RAG architecture with pgvector
       - Incident → Triage → Explain → Runbook → Safety → Simulate flow
   - Describe Cloud Run + Neon + Upstash integration

6. **Data Flow**
   - Step-by-step message flow for A2A:
        - MCP envelopes
        - Tool invocation
        - RAG searches
        - Multi-agent orchestration
   - Include a small flowchart using Markdown code block (ASCII)

7. **Demonstration of ADK Concepts**
   Create a section called:
   **“ADK Concepts Demonstrated in This Project”**
   Include:
   - Multi-agent orchestration (sequential + parallel + loop)
   - MCP custom tools
   - Memory Bank (RAG) demonstration
   - Observability/logging
   - Agent evaluation metrics
   - Context compaction

8. **Executable Code Snippets**
   Add code cells that demonstrate simplified, safe versions of:
   - A minimal MCP envelope construction:
        ```python
        envelope = {
            "id": "demo-001",
            "tool_name": "triage",
            "inputs": {"features": {"failed_logins": 23, "ip": "10.0.0.5"}},
            "trace_id": "demo-trace-1"
        }
        ```
   - A sample call to a local MCP handler function:
        ```python
        from backend_like.mcp_handler_demo import invoke_tool
        result = invoke_tool(envelope)
        result
        ```
   **Important:**  
   These code blocks are NOT the real backend code.  
   They must be small demo versions that show understanding.

9. **Backend API Demonstrations**
   Add real HTTP calls to your Cloud Run backend:
   - `GET /health`
   - `POST /triage`
   - `POST /runbook`
   - `POST /simulate_flow`
   - `POST /mcp/invoke`

   Use `requests` module:
   ```python
   import requests
   BASE = "https://<YOUR_CLOUD_RUN_URL>"
   res = requests.post(f"{BASE}/triage", json={"features": {...}})
   res.json()
