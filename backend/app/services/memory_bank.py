"""
Memory bank for persistent vector storage and retrieval.

This module provides a memory system using Neon pgvector for:
- Storing embeddings with metadata
- Semantic similarity search
- Memory usage logging and telemetry

Database Schema (app.memories table):
    CREATE TABLE IF NOT EXISTS app.memories (
        id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
        text TEXT NOT NULL,
        embedding vector(1536),
        metadata JSONB DEFAULT '{}'::jsonb,
        memory_type TEXT,
        session_id TEXT,
        created_at TIMESTAMPTZ DEFAULT now()
    );
    
    CREATE INDEX IF NOT EXISTS idx_memories_embedding 
    ON app.memories USING ivfflat (embedding vector_cosine_ops) WITH (lists = 100);
    
    CREATE INDEX IF NOT EXISTS idx_memories_session ON app.memories(session_id);
    CREATE INDEX IF NOT EXISTS idx_memories_type ON app.memories(memory_type);

Usage:
    from app.services.memory_bank import store_memory, retrieve_similar, MemoryItem
    
    # Store a memory
    item = MemoryItem(text="Incident resolved by isolating host", metadata={"incident_id": "INC-001"})
    await store_memory(item)
    
    # Retrieve similar memories
    results = await retrieve_similar("how to isolate compromised systems", k=5)
"""

import json
from datetime import datetime
from typing import Optional
from uuid import uuid4

from pydantic import BaseModel, Field


# =============================================================================
# Models
# =============================================================================


class MemoryItem(BaseModel):
    """A memory item with text, embedding, and metadata."""

    id: str = Field(default_factory=lambda: str(uuid4()))
    text: str = Field(..., description="Memory content text")
    embedding: list[float] = Field(default_factory=list, description="Vector embedding")
    metadata: dict = Field(default_factory=dict, description="Additional metadata")
    memory_type: Optional[str] = Field(None, description="Type: incident, runbook, etc.")
    session_id: Optional[str] = Field(None, description="Associated session ID")
    created_at: datetime = Field(default_factory=datetime.utcnow)

    model_config = {"extra": "ignore"}


# =============================================================================
# In-Memory Fallback Store
# =============================================================================

_memory_store: dict[str, MemoryItem] = {}


# =============================================================================
# Storage Functions
# =============================================================================


async def store_memory(item: MemoryItem) -> Optional[str]:
    """
    Store a memory item in pgvector.

    If embedding is not provided, generates it using rag.embed_text.

    Args:
        item: MemoryItem to store

    Returns:
        ID of stored memory, or None on failure

    Example:
        >>> item = MemoryItem(text="Block IP 192.168.1.100 in firewall")
        >>> memory_id = await store_memory(item)
    """
    from app.core.db import get_pg_connection
    from app.core.observability import log_event

    # Generate embedding if not provided
    if not item.embedding:
        try:
            from app.services.rag import embed_text

            item.embedding = await embed_text(item.text)
        except Exception as e:
            log_event(
                "memory_embedding_error",
                {"error": str(e), "text_length": len(item.text)},
                level="WARNING",
            )
            # Store without embedding (text search still possible)
            item.embedding = []

    async with get_pg_connection() as conn:
        if conn is None:
            # Fallback to in-memory store
            _memory_store[item.id] = item
            log_event(
                "memory_stored_inmemory",
                {"id": item.id, "has_embedding": bool(item.embedding)},
            )
            return item.id

        try:
            metadata_json = json.dumps(item.metadata)
            embedding_str = (
                f"[{','.join(str(x) for x in item.embedding)}]" if item.embedding else None
            )

            await conn.execute(
                """
                INSERT INTO app.memories (id, text, embedding, metadata, memory_type, session_id, created_at)
                VALUES ($1::uuid, $2, $3::vector, $4::jsonb, $5, $6, $7)
                ON CONFLICT (id) DO UPDATE SET
                    text = EXCLUDED.text,
                    embedding = EXCLUDED.embedding,
                    metadata = app.memories.metadata || EXCLUDED.metadata
                """,
                item.id,
                item.text,
                embedding_str,
                metadata_json,
                item.memory_type,
                item.session_id,
                item.created_at,
            )

            log_event(
                "memory_stored",
                {
                    "id": item.id,
                    "type": item.memory_type,
                    "has_embedding": bool(item.embedding),
                },
            )
            return item.id

        except Exception as e:
            log_event(
                "memory_store_error",
                {"error": str(e), "id": item.id},
                level="ERROR",
            )
            # Fallback to memory
            _memory_store[item.id] = item
            return item.id


async def retrieve_similar(
    text: str,
    k: int = 5,
    memory_type: Optional[str] = None,
    session_id: Optional[str] = None,
    trace_id: Optional[str] = None,
) -> list[MemoryItem]:
    """
    Retrieve similar memories using vector similarity search.

    Uses pgvector cosine distance for semantic search.

    Args:
        text: Query text to find similar memories
        k: Number of results to return
        memory_type: Filter by memory type (optional)
        session_id: Filter by session (optional)
        trace_id: Trace ID for logging

    Returns:
        List of similar MemoryItem objects

    Example:
        >>> results = await retrieve_similar("firewall blocking rules", k=3)
        >>> for item in results:
        ...     print(f"{item.text[:50]}... (similarity: {item.metadata.get('score')})")
    """
    from app.core.db import get_pg_connection
    from app.core.observability import log_event

    # Generate query embedding
    try:
        from app.services.rag import embed_text

        query_embedding = await embed_text(text)
    except Exception as e:
        log_event(
            "memory_retrieval_embedding_error",
            {"error": str(e)},
            trace_id=trace_id,
            level="WARNING",
        )
        return []

    async with get_pg_connection() as conn:
        if conn is None:
            # Fallback: return from in-memory store (no similarity)
            results = list(_memory_store.values())[:k]
            await log_memory_usage(trace_id or "", text, [r.model_dump() for r in results])
            return results

        try:
            embedding_str = f"[{','.join(str(x) for x in query_embedding)}]"

            # Build query with optional filters
            where_clauses = ["embedding IS NOT NULL"]
            params = [embedding_str, k]
            param_idx = 3

            if memory_type:
                where_clauses.append(f"memory_type = ${param_idx}")
                params.append(memory_type)
                param_idx += 1

            if session_id:
                where_clauses.append(f"session_id = ${param_idx}")
                params.append(session_id)
                param_idx += 1

            where_sql = " AND ".join(where_clauses)

            rows = await conn.fetch(
                f"""
                SELECT 
                    id, text, metadata, memory_type, session_id, created_at,
                    1 - (embedding <=> $1::vector) as similarity
                FROM app.memories
                WHERE {where_sql}
                ORDER BY embedding <=> $1::vector
                LIMIT $2
                """,
                *params,
            )

            results = []
            for row in rows:
                metadata = json.loads(row["metadata"]) if row["metadata"] else {}
                metadata["score"] = float(row["similarity"])

                results.append(
                    MemoryItem(
                        id=str(row["id"]),
                        text=row["text"],
                        embedding=[],  # Don't return full embedding
                        metadata=metadata,
                        memory_type=row["memory_type"],
                        session_id=row["session_id"],
                        created_at=row["created_at"],
                    )
                )

            log_event(
                "memory_retrieval",
                {
                    "query_length": len(text),
                    "k": k,
                    "results_count": len(results),
                    "filters": {"memory_type": memory_type, "session_id": session_id},
                },
                trace_id=trace_id,
            )

            await log_memory_usage(
                trace_id or "",
                text,
                [{"id": r.id, "score": r.metadata.get("score")} for r in results],
            )

            return results

        except Exception as e:
            log_event(
                "memory_retrieval_error",
                {"error": str(e)},
                trace_id=trace_id,
                level="ERROR",
            )
            return []


# =============================================================================
# Telemetry and Usage Logging
# =============================================================================


async def log_memory_usage(
    trace_id: str,
    query: str,
    results: list[dict],
) -> None:
    """
    Log memory usage for telemetry.

    Writes to Redis for quick access and observability for structured logging.

    Args:
        trace_id: Trace ID for correlation
        query: Query text
        results: List of result summaries
    """
    from app.core.db import cache_set
    from app.core.observability import log_event

    usage_entry = {
        "trace_id": trace_id,
        "query": query[:200],  # Truncate for storage
        "results_count": len(results),
        "result_ids": [r.get("id") for r in results[:10]],
        "timestamp": datetime.utcnow().isoformat(),
    }

    # Store in Redis for quick access
    await cache_set(
        f"memory_usage:{trace_id}",
        usage_entry,
        ttl=86400,  # 24 hours
    )

    # Log to observability
    log_event(
        "memory_usage",
        usage_entry,
        trace_id=trace_id,
    )


# =============================================================================
# Utility Functions
# =============================================================================


async def delete_memory(memory_id: str) -> bool:
    """Delete a memory by ID."""
    from app.core.db import get_pg_connection
    from app.core.observability import log_event

    async with get_pg_connection() as conn:
        if conn is None:
            if memory_id in _memory_store:
                del _memory_store[memory_id]
                return True
            return False

        try:
            result = await conn.execute(
                "DELETE FROM app.memories WHERE id = $1::uuid",
                memory_id,
            )
            deleted = "DELETE 1" in result
            log_event("memory_deleted", {"id": memory_id, "success": deleted})
            return deleted
        except Exception as e:
            log_event("memory_delete_error", {"id": memory_id, "error": str(e)}, level="ERROR")
            return False


async def get_memory_by_id(memory_id: str) -> Optional[MemoryItem]:
    """Get a specific memory by ID."""
    from app.core.db import get_pg_connection

    async with get_pg_connection() as conn:
        if conn is None:
            return _memory_store.get(memory_id)

        try:
            row = await conn.fetchrow(
                """
                SELECT id, text, metadata, memory_type, session_id, created_at
                FROM app.memories WHERE id = $1::uuid
                """,
                memory_id,
            )
            if row:
                return MemoryItem(
                    id=str(row["id"]),
                    text=row["text"],
                    metadata=json.loads(row["metadata"]) if row["metadata"] else {},
                    memory_type=row["memory_type"],
                    session_id=row["session_id"],
                    created_at=row["created_at"],
                )
            return None
        except Exception:
            return None


async def count_memories(
    memory_type: Optional[str] = None,
    session_id: Optional[str] = None,
) -> int:
    """Count memories with optional filters."""
    from app.core.db import get_pg_connection

    async with get_pg_connection() as conn:
        if conn is None:
            return len(_memory_store)

        try:
            where_clauses = []
            params = []
            param_idx = 1

            if memory_type:
                where_clauses.append(f"memory_type = ${param_idx}")
                params.append(memory_type)
                param_idx += 1

            if session_id:
                where_clauses.append(f"session_id = ${param_idx}")
                params.append(session_id)

            where_sql = " WHERE " + " AND ".join(where_clauses) if where_clauses else ""

            count = await conn.fetchval(f"SELECT COUNT(*) FROM app.memories{where_sql}", *params)
            return count or 0
        except Exception:
            return 0
