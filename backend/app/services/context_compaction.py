"""
Context compaction for conversation history management.

This module provides utilities to compact long conversation histories
into summaries to stay within LLM token limits while preserving context.

Features:
- Token-aware truncation
- LLM-based summarization (with Gemini placeholder)
- Redis caching for summaries
- Stale summary detection

Usage:
    from app.services.context_compaction import compact_context, summarize_if_needed
    
    # Compact a long conversation
    summary = await compact_context(messages, max_tokens=1500)
    
    # Check if summary exists or needs refresh
    summary = await summarize_if_needed(session_id, messages)
"""

import hashlib
from datetime import datetime
from typing import Optional

from pydantic import BaseModel, Field


# =============================================================================
# Models
# =============================================================================


class ConversationChunk(BaseModel):
    """A chunk of conversation messages with optional summary."""

    messages: list[str] = Field(default_factory=list, description="Raw messages")
    summary: Optional[str] = Field(None, description="Compacted summary if available")
    created_at: datetime = Field(default_factory=datetime.utcnow)

    model_config = {"extra": "ignore"}


# =============================================================================
# Token Estimation
# =============================================================================


def estimate_tokens(text: str) -> int:
    """
    Estimate token count for text.

    Uses simple word-based approximation (1 token ≈ 0.75 words).
    For production, use tiktoken or model-specific tokenizer.

    Args:
        text: Input text

    Returns:
        Estimated token count
    """
    # Simple approximation: ~4 chars per token for English
    return len(text) // 4


def estimate_messages_tokens(messages: list[str]) -> int:
    """Estimate total tokens across all messages."""
    return sum(estimate_tokens(msg) for msg in messages)


# =============================================================================
# LLM Compaction Placeholder
# =============================================================================


async def compact_via_gemini(messages: list[str], max_tokens: int) -> str:
    """
    Compact messages using Gemini LLM.

    TODO: Replace with real Vertex AI / Gemini call:
    
        from google.cloud import aiplatform
        from vertexai.generative_models import GenerativeModel
        
        model = GenerativeModel("gemini-1.5-flash")
        prompt = f'''Summarize this conversation in {max_tokens} tokens or less.
        Keep key facts, decisions, and action items.
        
        Conversation:
        {chr(10).join(messages)}
        '''
        response = await model.generate_content_async(prompt)
        return response.text

    Args:
        messages: List of conversation messages
        max_tokens: Target maximum token count

    Returns:
        Compacted summary string
    """
    # Stub implementation: return truncated join
    joined = "\n".join(messages)

    # Try to import LLM chain for real summarization
    try:
        from app.llm import get_llm_chain

        chain = get_llm_chain()
        if chain:
            prompt = f"""Summarize the following conversation concisely. 
Keep key facts, decisions, and any action items. Target length: {max_tokens} tokens.

Conversation:
{joined[:8000]}  # Limit input

Summary:"""
            result = await chain.ainvoke({"input": prompt})
            if result and "output" in result:
                return result["output"]
    except Exception:
        pass

    # Fallback: truncate to approximate token limit
    char_limit = max_tokens * 4
    if len(joined) > char_limit:
        return joined[:char_limit] + "... [truncated]"
    return joined


# =============================================================================
# Main Compaction Functions
# =============================================================================


async def compact_context(
    messages: list[str],
    max_tokens: int = 1500,
) -> str:
    """
    Compact conversation context to fit within token limits.

    If messages fit within max_tokens, returns joined messages.
    Otherwise, uses LLM to generate a summary.

    Args:
        messages: List of conversation messages
        max_tokens: Maximum token count for output

    Returns:
        Compacted context string (either joined or summarized)

    Example:
        >>> messages = ["User: Help with incident", "Agent: What's the severity?", ...]
        >>> context = await compact_context(messages, max_tokens=1000)
    """
    from app.core.observability import log_event

    if not messages:
        return ""

    joined = "\n".join(messages)
    original_tokens = estimate_tokens(joined)

    # If already within limits, return as-is
    if original_tokens <= max_tokens:
        return joined

    # Need compaction
    log_event(
        "context_compaction_start",
        {
            "message_count": len(messages),
            "original_tokens": original_tokens,
            "max_tokens": max_tokens,
        },
    )

    try:
        summary = await compact_via_gemini(messages, max_tokens)
        compacted_tokens = estimate_tokens(summary)

        log_event(
            "context_compaction_complete",
            {
                "original_tokens": original_tokens,
                "compacted_tokens": compacted_tokens,
                "compression_ratio": round(original_tokens / max(compacted_tokens, 1), 2),
            },
        )

        return summary

    except Exception as e:
        log_event(
            "context_compaction_error",
            {"error": str(e), "fallback": "truncation"},
            level="WARNING",
        )
        # Fallback: simple truncation
        return _sync_fallback_truncate(messages, max_tokens)


def _sync_fallback_truncate(messages: list[str], max_tokens: int) -> str:
    """
    Synchronous fallback that truncates messages to fit token limit.

    Takes most recent messages up to token limit.
    """
    char_limit = max_tokens * 4
    result = []
    current_chars = 0

    # Take from end (most recent) first
    for msg in reversed(messages):
        if current_chars + len(msg) + 1 > char_limit:
            break
        result.append(msg)
        current_chars += len(msg) + 1

    result.reverse()
    return "\n".join(result)


# =============================================================================
# Caching and Staleness Detection
# =============================================================================


def _hash_messages(messages: list[str]) -> str:
    """Generate hash of messages for cache key."""
    content = "\n".join(messages)
    return hashlib.sha256(content.encode()).hexdigest()[:16]


async def summarize_if_needed(
    session_id: str,
    messages: list[str],
    max_tokens: int = 1500,
    stale_threshold_messages: int = 10,
) -> str:
    """
    Get or compute summary for session, using cache if valid.

    Checks Redis for existing summary. Recomputes if:
    - No cached summary exists
    - Messages have changed significantly (based on hash)
    - More than stale_threshold_messages new messages since last summary

    Args:
        session_id: Unique session identifier
        messages: Current conversation messages
        max_tokens: Max tokens for summary
        stale_threshold_messages: Recompute if this many new messages

    Returns:
        Summary string (cached or freshly computed)

    Example:
        >>> summary = await summarize_if_needed("session_123", messages)
    """
    from app.core.db import cache_get, cache_set
    from app.core.observability import log_event

    cache_key = f"summary:{session_id}"
    messages_hash = _hash_messages(messages)

    # Try to get cached summary
    cached = await cache_get(cache_key)
    if cached:
        cached_hash = cached.get("hash", "")
        cached_count = cached.get("message_count", 0)

        # Check if still valid
        if cached_hash == messages_hash:
            log_event("summary_cache_hit", {"session_id": session_id})
            return cached.get("summary", "")

        # Check if only a few new messages (not stale yet)
        new_messages = len(messages) - cached_count
        if new_messages < stale_threshold_messages and cached.get("summary"):
            # Append new messages to existing summary
            new_content = "\n".join(messages[cached_count:])
            combined = cached["summary"] + "\n\n[Recent]:\n" + new_content
            if estimate_tokens(combined) <= max_tokens:
                log_event(
                    "summary_cache_extended",
                    {"session_id": session_id, "new_messages": new_messages},
                )
                return combined

    # Need to recompute
    log_event(
        "summary_cache_miss",
        {"session_id": session_id, "message_count": len(messages)},
    )

    summary = await compact_context(messages, max_tokens)

    # Cache the new summary
    await cache_set(
        cache_key,
        {
            "summary": summary,
            "hash": messages_hash,
            "message_count": len(messages),
            "created_at": datetime.utcnow().isoformat(),
        },
        ttl=3600,  # 1 hour
    )

    return summary


# =============================================================================
# Utility Functions
# =============================================================================


async def clear_summary_cache(session_id: str) -> bool:
    """Clear cached summary for a session."""
    from app.core.db import cache_delete

    return await cache_delete(f"summary:{session_id}")


async def get_compaction_stats(session_id: str) -> Optional[dict]:
    """Get compaction statistics for a session."""
    from app.core.db import cache_get

    return await cache_get(f"summary:{session_id}")
