"""
RAG (Retrieval-Augmented Generation) helpers for pgvector.

This module provides embedding generation and similarity search
functionality for the runbook retrieval system.

Uses Vertex AI embeddings (text-embedding-004) for vector generation.
"""

import os
from typing import Any, Optional

from app.config import get_settings, is_llm_available

# =============================================================================
# Embedding Configuration
# =============================================================================

EMBEDDING_MODEL = "text-embedding-004"
EMBEDDING_DIMENSION = 768


# =============================================================================
# Stub Embeddings (for development without Vertex AI)
# =============================================================================


def generate_stub_embedding(text: str) -> list[float]:
    """
    Generate a deterministic stub embedding for development.

    Creates a simple hash-based embedding when Vertex AI is not available.

    Args:
        text: Text to embed

    Returns:
        List of floats representing the embedding
    """
    import hashlib

    # Create deterministic hash
    text_hash = hashlib.sha256(text.encode()).hexdigest()

    # Convert hash to list of floats
    embedding = []
    for i in range(0, min(len(text_hash), EMBEDDING_DIMENSION * 2), 2):
        byte_val = int(text_hash[i : i + 2], 16)
        # Normalize to [-1, 1]
        embedding.append((byte_val - 128) / 128)

    # Pad to full dimension
    while len(embedding) < EMBEDDING_DIMENSION:
        embedding.append(0.0)

    return embedding[:EMBEDDING_DIMENSION]


# =============================================================================
# Vertex AI Embeddings
# =============================================================================


async def embed_text_vertex(text: str) -> list[float]:
    """
    Generate text embedding using Vertex AI.

    Args:
        text: Text to embed

    Returns:
        List of floats representing the embedding

    Raises:
        Exception if Vertex AI call fails
    """
    settings = get_settings()

    try:
        from vertexai.language_models import TextEmbeddingModel

        # Initialize model
        model = TextEmbeddingModel.from_pretrained(settings.vertex_embedding_model)

        # Generate embedding
        embeddings = model.get_embeddings([text])

        if embeddings and len(embeddings) > 0:
            return embeddings[0].values

        raise ValueError("No embedding returned from Vertex AI")

    except ImportError:
        print("vertexai not installed. Using google-genai fallback.")
        return await embed_text_genai(text)


async def embed_text_genai(text: str) -> list[float]:
    """
    Generate text embedding using google-genai library.

    Alternative to Vertex AI when using API key authentication.

    Args:
        text: Text to embed

    Returns:
        List of floats representing the embedding
    """
    try:
        from google import genai
        from google.genai import types

        client = genai.Client()

        response = client.models.embed_content(
            model=f"models/{EMBEDDING_MODEL}",
            contents=[text],
            config=types.EmbedContentConfig(
                task_type="RETRIEVAL_DOCUMENT",
            ),
        )

        if response.embeddings and len(response.embeddings) > 0:
            return list(response.embeddings[0].values)

        raise ValueError("No embedding returned from genai")

    except Exception as e:
        print(f"google-genai embedding failed: {e}")
        raise


# =============================================================================
# Main Embedding Function
# =============================================================================


async def embed_text(text: str) -> list[float]:
    """
    Generate text embedding, using Vertex AI if available or stub otherwise.

    This is the main entry point for embedding generation.

    Args:
        text: Text to embed

    Returns:
        List of floats representing the embedding

    Example:
        >>> embedding = await embed_text("Isolate compromised host")
        >>> len(embedding)
        768
    """
    if not is_llm_available():
        print("Using stub embeddings (Vertex AI not configured)")
        return generate_stub_embedding(text)

    try:
        return await embed_text_vertex(text)
    except Exception as e:
        print(f"Vertex embedding failed, using stub: {e}")
        return generate_stub_embedding(text)


# =============================================================================
# Similarity Search
# =============================================================================


async def get_similar_runbooks(
    text: str,
    k: int = 5,
) -> list[dict[str, Any]]:
    """
    Retrieve similar runbooks from the database using semantic search.

    1. Generates embedding for the query text
    2. Queries pgvector for nearest neighbors
    3. Returns ranked results

    Args:
        text: Query text (e.g., incident description)
        k: Number of results to return

    Returns:
        List of dicts with {id, text, score}

    Example:
        >>> results = await get_similar_runbooks("brute force login attack", k=3)
        >>> for r in results:
        ...     print(f"{r['score']:.2f}: {r['text'][:50]}...")
    """
    from app.db import query_similar_runbooks

    # Generate query embedding
    query_embedding = await embed_text(text)

    # Query database
    results = await query_similar_runbooks(query_embedding, k)

    return results


async def get_similar_runbooks_with_conn(
    conn,
    text: str,
    k: int = 5,
) -> list[dict[str, Any]]:
    """
    Retrieve similar runbooks using an existing database connection.

    Useful when you need to reuse a connection within a transaction.

    Args:
        conn: asyncpg connection
        text: Query text
        k: Number of results

    Returns:
        List of similar runbooks
    """
    import json

    # Generate query embedding
    query_embedding = await embed_text(text)
    vector_str = f"[{','.join(map(str, query_embedding))}]"

    try:
        rows = await conn.fetch(
            """
            SELECT id, text, metadata,
                   1 - (embedding <=> $1::vector) as similarity
            FROM runbooks
            ORDER BY embedding <=> $1::vector
            LIMIT $2;
            """,
            vector_str,
            k,
        )

        return [
            {
                "id": row["id"],
                "text": row["text"],
                "score": float(row["similarity"]),
                "metadata": json.loads(row["metadata"]) if row["metadata"] else {},
            }
            for row in rows
        ]
    except Exception as e:
        print(f"Similar runbooks query failed: {e}")
        return []


# =============================================================================
# Batch Embedding
# =============================================================================


async def embed_texts(texts: list[str]) -> list[list[float]]:
    """
    Generate embeddings for multiple texts.

    More efficient than calling embed_text multiple times when
    the embedding API supports batching.

    Args:
        texts: List of texts to embed

    Returns:
        List of embeddings
    """
    if not is_llm_available():
        return [generate_stub_embedding(t) for t in texts]

    try:
        from google import genai
        from google.genai import types

        client = genai.Client()

        response = client.models.embed_content(
            model=f"models/{EMBEDDING_MODEL}",
            contents=texts,
            config=types.EmbedContentConfig(
                task_type="RETRIEVAL_DOCUMENT",
            ),
        )

        return [list(e.values) for e in response.embeddings]

    except Exception as e:
        print(f"Batch embedding failed, using stubs: {e}")
        return [generate_stub_embedding(t) for t in texts]


# =============================================================================
# Utility Functions
# =============================================================================


def cosine_similarity(a: list[float], b: list[float]) -> float:
    """
    Calculate cosine similarity between two vectors.

    Useful for local similarity comparisons.

    Args:
        a: First vector
        b: Second vector

    Returns:
        Similarity score between -1 and 1
    """
    import math

    dot_product = sum(x * y for x, y in zip(a, b))
    norm_a = math.sqrt(sum(x * x for x in a))
    norm_b = math.sqrt(sum(x * x for x in b))

    if norm_a == 0 or norm_b == 0:
        return 0.0

    return dot_product / (norm_a * norm_b)


async def search_and_rerank(
    query: str,
    k: int = 10,
    rerank_k: int = 5,
) -> list[dict[str, Any]]:
    """
    Two-stage retrieval with reranking.

    1. Retrieve k candidates using embedding similarity
    2. Rerank using a more sophisticated scoring (future: cross-encoder)

    Args:
        query: Query text
        k: Initial candidates to retrieve
        rerank_k: Final results to return

    Returns:
        Reranked list of results
    """
    # Stage 1: Vector search
    candidates = await get_similar_runbooks(query, k)

    if len(candidates) <= rerank_k:
        return candidates

    # Stage 2: Simple reranking based on text overlap (placeholder)
    # In production, use a cross-encoder model
    query_terms = set(query.lower().split())

    for candidate in candidates:
        text_terms = set(candidate["text"].lower().split())
        overlap = len(query_terms & text_terms)
        # Combine vector score with term overlap
        candidate["rerank_score"] = candidate["score"] * 0.7 + (overlap / len(query_terms)) * 0.3

    # Sort by rerank score
    candidates.sort(key=lambda x: x.get("rerank_score", 0), reverse=True)

    return candidates[:rerank_k]
