"""
Built-in Vertex AI tools demonstration.

This module provides demo/stub implementations for Vertex AI built-in tools:
- Vertex AI Search (grounding with enterprise data)
- Vertex AI Code Execution (sandboxed code running)

These are placeholders that can be enabled when Vertex AI is configured.

Usage:
    from app.orchestration.built_in_tools_demo import vertex_search_demo, vertex_code_exec_demo
    
    # Search demo
    results = await vertex_search_demo("security incident response")
    
    # Code execution demo
    output = await vertex_code_exec_demo("print('Hello')", language="python")

Tool Registration (optional):
    from app.orchestration.tools_adk import register_adk_tool
    
    register_adk_tool(
        name="vertex_search",
        func=vertex_search_demo,
        description="Search enterprise knowledge base"
    )
"""

from datetime import datetime
from typing import Any, Optional


# =============================================================================
# Vertex AI Search Demo
# =============================================================================


async def vertex_search_demo(
    query: str,
    max_results: int = 5,
    data_store_id: Optional[str] = None,
    trace_id: Optional[str] = None,
) -> dict[str, Any]:
    """
    Demonstrate Vertex AI Search capability.

    TODO: Replace with real Vertex AI Search when enabled:
    
        from google.cloud import discoveryengine_v1 as discoveryengine
        
        client = discoveryengine.SearchServiceClient()
        serving_config = f"projects/{project}/locations/{location}/dataStores/{data_store}/servingConfigs/default_config"
        
        request = discoveryengine.SearchRequest(
            serving_config=serving_config,
            query=query,
            page_size=max_results,
        )
        response = await client.search(request=request)
        
        return {
            "query": query,
            "results": [{"id": r.id, "title": r.document.title, "snippet": r.document.snippet} for r in response.results],
            "total_size": response.total_size,
        }

    Args:
        query: Search query string
        max_results: Maximum number of results
        data_store_id: Vertex AI Search data store ID
        trace_id: Trace ID for logging

    Returns:
        Dict with query, results, and metadata
    """
    from app.core.observability import log_event

    log_event(
        "vertex_search_request",
        {
            "query": query,
            "max_results": max_results,
            "data_store_id": data_store_id,
            "mode": "demo",
        },
        trace_id=trace_id,
    )

    # Mock search results for demo
    mock_results = [
        {
            "id": "doc_001",
            "title": "Incident Response Playbook",
            "snippet": f"...relevant content for '{query}'...",
            "url": "https://docs.example.com/playbook",
            "relevance_score": 0.95,
        },
        {
            "id": "doc_002",
            "title": "Security Best Practices",
            "snippet": "Guidelines for handling security incidents...",
            "url": "https://docs.example.com/security",
            "relevance_score": 0.87,
        },
        {
            "id": "doc_003",
            "title": "Runbook: Malware Containment",
            "snippet": "Steps to isolate and contain malware...",
            "url": "https://docs.example.com/malware",
            "relevance_score": 0.82,
        },
    ][:max_results]

    log_event(
        "vertex_search_response",
        {
            "query": query,
            "results_count": len(mock_results),
            "mode": "demo",
        },
        trace_id=trace_id,
    )

    return {
        "query": query,
        "results": mock_results,
        "total_size": len(mock_results),
        "mode": "demo",
        "timestamp": datetime.utcnow().isoformat(),
        "note": "This is a demo response. Enable Vertex AI Search for real results.",
    }


# =============================================================================
# Vertex AI Code Execution Demo
# =============================================================================


async def vertex_code_exec_demo(
    code_snippet: str,
    language: str = "python",
    timeout_seconds: int = 30,
    trace_id: Optional[str] = None,
) -> dict[str, Any]:
    """
    Demonstrate Vertex AI Code Execution capability.

    TODO: Replace with real Vertex AI Code Execution when enabled:
    
        from vertexai.generative_models import GenerativeModel
        
        model = GenerativeModel(
            "gemini-1.5-pro",
            tools=[Tool(code_execution=ToolCodeExecution())]
        )
        
        response = await model.generate_content_async(
            f"Execute this code and return the result:\\n```{language}\\n{code_snippet}\\n```"
        )
        
        # Extract code execution result from response
        for part in response.candidates[0].content.parts:
            if hasattr(part, 'executable_code'):
                return {"stdout": part.code_execution_result.output, "exit_code": 0}

    SECURITY NOTE: This demo does NOT execute real code.
    Real implementation should use Vertex's sandboxed environment.

    Args:
        code_snippet: Code to execute
        language: Programming language (python, bash, javascript)
        timeout_seconds: Execution timeout
        trace_id: Trace ID for logging

    Returns:
        Dict with stdout, stderr, exit_code, and metadata
    """
    from app.core.observability import log_event

    log_event(
        "vertex_code_exec_request",
        {
            "language": language,
            "code_length": len(code_snippet),
            "timeout": timeout_seconds,
            "mode": "demo",
        },
        trace_id=trace_id,
    )

    # Simulate execution based on language
    if language == "python":
        mock_output = _simulate_python_output(code_snippet)
    elif language == "bash":
        mock_output = _simulate_bash_output(code_snippet)
    else:
        mock_output = {
            "stdout": f"[Simulated output for {language}]",
            "stderr": "",
            "exit_code": 0,
        }

    log_event(
        "vertex_code_exec_response",
        {
            "language": language,
            "exit_code": mock_output["exit_code"],
            "stdout_length": len(mock_output["stdout"]),
            "mode": "demo",
        },
        trace_id=trace_id,
    )

    return {
        **mock_output,
        "language": language,
        "mode": "demo",
        "timestamp": datetime.utcnow().isoformat(),
        "note": "This is a simulated response. Enable Vertex AI Code Execution for real execution.",
    }


def _simulate_python_output(code: str) -> dict[str, Any]:
    """Simulate Python code output (no real execution)."""
    # Check for common patterns and return mock output
    if "print(" in code:
        # Extract print content
        import re

        match = re.search(r'print\(["\'](.+?)["\']\)', code)
        if match:
            return {"stdout": match.group(1) + "\n", "stderr": "", "exit_code": 0}
        return {"stdout": "[print output]\n", "stderr": "", "exit_code": 0}

    if "import" in code:
        return {"stdout": "", "stderr": "", "exit_code": 0}

    if "def " in code:
        return {"stdout": "[function defined]\n", "stderr": "", "exit_code": 0}

    if "raise" in code or "error" in code.lower():
        return {
            "stdout": "",
            "stderr": "Simulated error occurred\n",
            "exit_code": 1,
        }

    return {"stdout": "[code executed successfully]\n", "stderr": "", "exit_code": 0}


def _simulate_bash_output(code: str) -> dict[str, Any]:
    """Simulate bash command output (no real execution)."""
    if code.startswith("echo "):
        content = code[5:].strip().strip('"').strip("'")
        return {"stdout": content + "\n", "stderr": "", "exit_code": 0}

    if code.startswith("ls"):
        return {"stdout": "file1.txt\nfile2.py\ndir/\n", "stderr": "", "exit_code": 0}

    if code.startswith("cat "):
        return {"stdout": "[file contents]\n", "stderr": "", "exit_code": 0}

    if "rm " in code or "sudo" in code:
        return {
            "stdout": "",
            "stderr": "Simulated: dangerous command blocked\n",
            "exit_code": 1,
        }

    return {"stdout": "[command executed]\n", "stderr": "", "exit_code": 0}


# =============================================================================
# Tool Registration Helper
# =============================================================================


def register_vertex_tools():
    """
    Register Vertex tools with ADK tool registry.

    Call this during app startup to expose these tools to agents.

    Example:
        # In main.py startup
        from app.orchestration.built_in_tools_demo import register_vertex_tools
        register_vertex_tools()
    """
    try:
        from app.orchestration.tools_adk import register_adk_tool

        register_adk_tool(
            name="vertex_search",
            func=vertex_search_demo,
            description="Search enterprise knowledge base using Vertex AI Search. "
            "Returns relevant documents and snippets.",
        )

        register_adk_tool(
            name="vertex_code_exec",
            func=vertex_code_exec_demo,
            description="Execute code in a sandboxed environment. "
            "Supports Python and Bash. Returns stdout, stderr, and exit code.",
        )

        print("Registered Vertex AI demo tools: vertex_search, vertex_code_exec")

    except ImportError:
        print("tools_adk not available, skipping Vertex tool registration")


# =============================================================================
# Grounding Configuration Helper
# =============================================================================


def get_grounding_config(
    data_store_id: Optional[str] = None,
    google_search_enabled: bool = False,
) -> dict[str, Any]:
    """
    Get grounding configuration for Vertex AI models.

    TODO: Use with GenerativeModel when configuring grounding:
    
        from vertexai.generative_models import GenerativeModel, grounding
        
        model = GenerativeModel(
            "gemini-1.5-pro",
            tools=[grounding.GoogleSearchRetrieval()],  # or Vertex AI Search
        )

    Args:
        data_store_id: Vertex AI Search data store ID for enterprise grounding
        google_search_enabled: Enable Google Search grounding

    Returns:
        Configuration dict for grounding setup
    """
    config = {
        "enabled": True,
        "sources": [],
    }

    if data_store_id:
        config["sources"].append({
            "type": "vertex_ai_search",
            "data_store_id": data_store_id,
        })

    if google_search_enabled:
        config["sources"].append({
            "type": "google_search",
        })

    return config
