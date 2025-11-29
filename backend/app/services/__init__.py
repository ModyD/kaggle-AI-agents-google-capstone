"""
Business logic services.

This package contains:
- LLM chain management
- RAG (Retrieval-Augmented Generation)
- Memory bank for vector storage
- Context compaction utilities
- Agent evaluation and metrics
"""

from .chains import (
    generate_explanation_chain,
    generate_runbook_chain,
    get_stub_explanation,
    get_stub_runbook,
    call_gemini_with_retry,
    call_gemini_genai,
)
from .rag import (
    embed_text,
    embed_texts,
    embed_text_vertex,
    embed_text_genai,
    get_similar_runbooks,
    get_similar_runbooks_with_conn,
    generate_stub_embedding,
    cosine_similarity,
    search_and_rerank,
)
from .memory_bank import (
    store_memory,
    retrieve_similar,
    MemoryItem,
    log_memory_usage,
    delete_memory,
    get_memory_by_id,
    count_memories,
)
from .context_compaction import (
    compact_context,
    summarize_if_needed,
    compact_via_gemini,
    estimate_tokens,
    estimate_messages_tokens,
    clear_summary_cache,
    get_compaction_stats,
    ConversationChunk,
)
from .agent_evaluation import (
    record_metric,
    evaluate_runbook_quality,
    evaluate_safety,
    get_metrics_snapshot,
    get_evaluation_history,
    persist_metrics_to_redis,
    restore_metrics_from_redis,
    EvaluationResult,
    MetricEntry,
    MetricsStore,
)

__all__ = [
    # Chains
    "generate_explanation_chain",
    "generate_runbook_chain",
    "get_stub_explanation",
    "get_stub_runbook",
    "call_gemini_with_retry",
    "call_gemini_genai",
    # RAG
    "embed_text",
    "embed_texts",
    "embed_text_vertex",
    "embed_text_genai",
    "get_similar_runbooks",
    "get_similar_runbooks_with_conn",
    "generate_stub_embedding",
    "cosine_similarity",
    "search_and_rerank",
    # Memory
    "store_memory",
    "retrieve_similar",
    "MemoryItem",
    "log_memory_usage",
    "delete_memory",
    "get_memory_by_id",
    "count_memories",
    # Context
    "compact_context",
    "summarize_if_needed",
    "compact_via_gemini",
    "estimate_tokens",
    "estimate_messages_tokens",
    "clear_summary_cache",
    "get_compaction_stats",
    "ConversationChunk",
    # Evaluation
    "record_metric",
    "evaluate_runbook_quality",
    "evaluate_safety",
    "get_metrics_snapshot",
    "get_evaluation_history",
    "persist_metrics_to_redis",
    "restore_metrics_from_redis",
    "EvaluationResult",
    "MetricEntry",
    "MetricsStore",
]
