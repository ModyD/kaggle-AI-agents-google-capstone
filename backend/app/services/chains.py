"""
LangChain chains for structured LLM output with Pydantic validation.

This module provides robust LLM interaction patterns with:
- Vertex AI / Gemini integration via LangChain
- Output parsing with JSON schema enforcement
- Retry logic for malformed responses
- Fallback to stub responses when LLM is unavailable
"""

import json
from typing import Any, Optional, Type, TypeVar

from pydantic import BaseModel

from app.config import get_settings, is_llm_available
from app.models import RunbookResponse, RunbookStep, TriageExplanation

T = TypeVar("T", bound=BaseModel)


# =============================================================================
# Stub Responses (for development without LLM keys)
# =============================================================================


def get_stub_explanation(
    label: str,
    score: int,
    contribs: list[tuple[str, int]],
) -> dict[str, Any]:
    """Generate a stub explanation when LLM is unavailable."""
    contrib_text = ", ".join(f"{feat} (+{pts})" for feat, pts in contribs[:3])

    return {
        "explanation": f"This incident was classified as {label} severity with a score of {score}. "
        f"Key contributing factors: {contrib_text}.",
        "reasons": [
            f"Primary indicator: {contribs[0][0] if contribs else 'general anomaly'}",
            f"Cumulative risk score of {score} exceeds threshold for {label} classification",
        ],
    }


def get_stub_runbook(label: str, contribs: list[tuple[str, int]]) -> RunbookResponse:
    """Generate a stub runbook when LLM is unavailable."""
    steps = []

    # Generate steps based on severity
    if label == "HIGH":
        steps = [
            RunbookStep(
                step="Immediately isolate affected host from network",
                why="Prevent lateral movement and further compromise",
                risk="medium",
            ),
            RunbookStep(
                step="Capture memory dump and disk image for forensics",
                why="Preserve evidence before any remediation",
                risk="low",
            ),
            RunbookStep(
                step="Reset credentials for affected accounts",
                why="Prevent unauthorized access using compromised credentials",
                risk="medium",
            ),
            RunbookStep(
                step="Deploy EDR scan on affected and adjacent systems",
                why="Detect any persistence mechanisms or lateral movement",
                risk="low",
            ),
            RunbookStep(
                step="Review and update firewall rules to block identified IOCs",
                why="Prevent communication with known malicious infrastructure",
                risk="medium",
            ),
        ]
    elif label == "MEDIUM":
        steps = [
            RunbookStep(
                step="Enable enhanced logging on affected system",
                why="Gather additional telemetry for investigation",
                risk="low",
            ),
            RunbookStep(
                step="Review authentication logs for anomalies",
                why="Identify scope of potential compromise",
                risk="low",
            ),
            RunbookStep(
                step="Validate user activity with asset owner",
                why="Confirm whether activity is legitimate",
                risk="low",
            ),
            RunbookStep(
                step="Consider password reset for affected user",
                why="Precautionary measure if credentials may be compromised",
                risk="low",
            ),
        ]
    else:
        steps = [
            RunbookStep(
                step="Document incident details in ticketing system",
                why="Maintain audit trail and enable trend analysis",
                risk="low",
            ),
            RunbookStep(
                step="Monitor for similar events over next 24 hours",
                why="Detect if this is part of a larger pattern",
                risk="low",
            ),
        ]

    return RunbookResponse(runbook=steps, source="stub")


# =============================================================================
# LangChain Integration
# =============================================================================


async def call_gemini_with_retry(
    prompt: str,
    system_prompt: str,
    output_schema: Optional[Type[T]] = None,
    max_retries: int = 2,
) -> dict[str, Any]:
    """
    Call Gemini via LangChain with retry logic for JSON parsing.

    Args:
        prompt: User prompt
        system_prompt: System instructions
        output_schema: Optional Pydantic model for output validation
        max_retries: Number of retries on parse failure

    Returns:
        Parsed response dictionary
    """
    settings = get_settings()

    try:
        from langchain_google_vertexai import ChatVertexAI
        from langchain_core.messages import HumanMessage, SystemMessage
        from langchain_core.output_parsers import JsonOutputParser

        # Initialize model
        llm = ChatVertexAI(
            model=settings.vertex_ai_model,
            project=settings.google_cloud_project,
            location=settings.google_cloud_location,
            temperature=0.2,
            max_output_tokens=2048,
        )

        # Create parser
        parser = JsonOutputParser(pydantic_object=output_schema) if output_schema else JsonOutputParser()

        messages = [
            SystemMessage(content=system_prompt),
            HumanMessage(content=prompt),
        ]

        for attempt in range(max_retries + 1):
            try:
                # Call LLM
                response = await llm.ainvoke(messages)

                # Parse response
                result = parser.parse(response.content)

                # Validate with Pydantic if schema provided
                if output_schema:
                    validated = output_schema.model_validate(result)
                    return validated.model_dump()

                return result

            except Exception as parse_error:
                if attempt < max_retries:
                    # Add correction message
                    messages.append(
                        HumanMessage(
                            content=f"Your previous response was not valid JSON. Error: {parse_error}. "
                            "Please respond with ONLY valid JSON, no markdown formatting or explanation."
                        )
                    )
                    continue
                raise

    except ImportError:
        print("LangChain Vertex not installed, trying google-genai")
        return await call_gemini_genai(prompt, system_prompt, output_schema, max_retries)


async def call_gemini_genai(
    prompt: str,
    system_prompt: str,
    output_schema: Optional[Type[T]] = None,
    max_retries: int = 2,
) -> dict[str, Any]:
    """
    Call Gemini using google-genai library.

    Fallback when LangChain Vertex is not available.
    """
    settings = get_settings()

    try:
        from google import genai
        from google.genai import types

        client = genai.Client()

        full_prompt = f"{system_prompt}\n\n{prompt}"

        for attempt in range(max_retries + 1):
            try:
                response = client.models.generate_content(
                    model=f"models/{settings.vertex_ai_model}",
                    contents=full_prompt,
                    config=types.GenerateContentConfig(
                        temperature=0.2,
                        response_mime_type="application/json",
                    ),
                )

                # Parse JSON response
                result = json.loads(response.text)

                # Validate with Pydantic if schema provided
                if output_schema:
                    validated = output_schema.model_validate(result)
                    return validated.model_dump()

                return result

            except json.JSONDecodeError as e:
                if attempt < max_retries:
                    full_prompt = (
                        f"{system_prompt}\n\n{prompt}\n\n"
                        f"IMPORTANT: Your previous response was not valid JSON. "
                        f"Error: {e}. Respond with ONLY valid JSON."
                    )
                    continue
                raise

    except Exception as e:
        print(f"google-genai call failed: {e}")
        raise


# =============================================================================
# Specialized Chain Functions
# =============================================================================


async def generate_explanation_chain(
    features: dict[str, Any],
    label: str,
    score: int,
    contribs: list[tuple[str, int]],
) -> dict[str, Any]:
    """
    Generate an LLM explanation for triage results.

    Args:
        features: Original incident features
        label: Triage severity label
        score: Triage score
        contribs: Contributing factors

    Returns:
        Dictionary with 'explanation' and 'reasons' keys
    """
    if not is_llm_available():
        return get_stub_explanation(label, score, contribs)

    system_prompt = """You are a security analyst AI assistant. Your task is to explain 
security incident triage decisions in clear, professional language.

Always respond with valid JSON in this exact format:
{
    "explanation": "A clear 2-3 sentence explanation of why this incident was classified this way",
    "reasons": ["First specific reason", "Second specific reason"]
}

Do not include any text outside the JSON object."""

    contrib_text = "\n".join(f"- {feat}: +{pts} points" for feat, pts in contribs)
    features_text = "\n".join(f"- {k}: {v}" for k, v in list(features.items())[:10])

    prompt = f"""Explain why this security incident was classified as {label} severity.

Incident Features:
{features_text}

Triage Score: {score}

Contributing Factors:
{contrib_text}

Provide a clear explanation and two specific reasons for this classification."""

    try:
        return await call_gemini_with_retry(
            prompt=prompt,
            system_prompt=system_prompt,
            output_schema=TriageExplanation,
        )
    except Exception as e:
        print(f"LLM explanation failed, using stub: {e}")
        return get_stub_explanation(label, score, contribs)


async def generate_runbook_chain(
    features: dict[str, Any],
    label: str,
    score: int,
    contribs: list[tuple[str, int]],
    similar_runbooks: list[dict[str, Any]],
) -> RunbookResponse:
    """
    Generate a runbook using RAG-enhanced prompting.

    Args:
        features: Incident features
        label: Severity label
        score: Triage score
        contribs: Contributing factors
        similar_runbooks: Retrieved similar runbooks for context

    Returns:
        RunbookResponse with generated steps
    """
    if not is_llm_available():
        return get_stub_runbook(label, contribs)

    system_prompt = """You are a security incident response expert. Generate a structured 
runbook with specific, actionable steps to respond to the incident.

Always respond with valid JSON in this exact format:
{
    "runbook": [
        {
            "step": "Specific action to take",
            "why": "Reason this step is necessary",
            "risk": "low|medium|high"
        }
    ],
    "source": "rag"
}

Each step should be:
- Specific and actionable
- Include commands or tools when relevant
- Marked with appropriate risk level

Generate 3-7 steps appropriate for the severity level.
Do not include any text outside the JSON object."""

    # Format context from similar runbooks
    context_text = ""
    if similar_runbooks:
        context_text = "\n\nRelevant Reference Runbooks:\n"
        for i, rb in enumerate(similar_runbooks[:3], 1):
            context_text += f"\n--- Reference {i} (similarity: {rb.get('score', 0):.2f}) ---\n"
            context_text += rb.get("text", "")[:500]

    contrib_text = ", ".join(f"{feat} (+{pts})" for feat, pts in contribs[:5])
    features_text = "\n".join(f"- {k}: {v}" for k, v in list(features.items())[:8])

    prompt = f"""Generate a security incident response runbook.

Incident Severity: {label}
Triage Score: {score}

Key Indicators:
{contrib_text}

Incident Details:
{features_text}
{context_text}

Generate appropriate response steps for this {label} severity incident."""

    try:
        result = await call_gemini_with_retry(
            prompt=prompt,
            system_prompt=system_prompt,
            output_schema=RunbookResponse,
        )
        return RunbookResponse.model_validate(result)
    except Exception as e:
        print(f"LLM runbook generation failed, using stub: {e}")
        return get_stub_runbook(label, contribs)
