"""
Database connection helpers for Neon PostgreSQL (pgvector) and Upstash Redis.

This module provides async connection management, caching helpers,
and vector similarity search functionality.

IMPORTANT: All database dependencies are OPTIONAL.
- When databases are not configured, in-memory storage is used
- No import errors if asyncpg/redis packages are not installed
- Perfect for local development, testing, and serverless deployments

Environment Variables (all optional):
    - NEON_DATABASE_URL: PostgreSQL connection string for Neon
    - UPSTASH_REDIS_REST_URL: Redis REST URL for Upstash
    - UPSTASH_REDIS_REST_TOKEN: Redis authentication token
"""

import json
import os
from contextlib import asynccontextmanager
from typing import Any, Optional

# =============================================================================
# Configuration
# =============================================================================

# Connection pool settings (when using real DB)
PG_POOL_MIN_SIZE = 2
PG_POOL_MAX_SIZE = 10
PG_COMMAND_TIMEOUT = 30  # seconds

# Redis settings
REDIS_DEFAULT_TTL = 3600  # 1 hour

# Embedding dimension (must match your embedding model)
EMBEDDING_DIMENSION = 768  # text-embedding-004 default

# =============================================================================
# In-Memory Storage (fallback when no DB configured)
# =============================================================================

# Simple in-memory stores for development/serverless
_memory_cache: dict[str, Any] = {}
_memory_runbooks: dict[str, dict] = {}
_memory_sessions: dict[str, dict] = {}


def _get_memory_cache():
    """Get the in-memory cache store."""
    return _memory_cache


def _get_memory_runbooks():
    """Get the in-memory runbook store."""
    return _memory_runbooks


# =============================================================================
# PostgreSQL (Neon) Connection Management
# =============================================================================

# Global connection pool (lazy loaded)
_pg_pool = None
_pg_available: Optional[bool] = None


def _check_pg_available() -> bool:
    """Check if asyncpg is installed and DB URL is configured."""
    global _pg_available
    if _pg_available is not None:
        return _pg_available
    
    if not os.getenv("NEON_DATABASE_URL"):
        _pg_available = False
        return False
    
    try:
        import asyncpg  # noqa: F401
        _pg_available = True
    except ImportError:
        _pg_available = False
        print("asyncpg not installed. Using in-memory storage.")
    
    return _pg_available


async def init_pg_pool():
    """
    Initialize the PostgreSQL connection pool.

    Call this at application startup. Returns None if DB not configured.
    """
    global _pg_pool

    if not _check_pg_available():
        return None

    database_url = os.getenv("NEON_DATABASE_URL")
    if not database_url:
        print("Info: NEON_DATABASE_URL not set. Using in-memory storage.")
        return None

    try:
        import asyncpg

        _pg_pool = await asyncpg.create_pool(
            database_url,
            min_size=PG_POOL_MIN_SIZE,
            max_size=PG_POOL_MAX_SIZE,
            command_timeout=PG_COMMAND_TIMEOUT,
        )
        print("PostgreSQL connection pool initialized")
        return _pg_pool
    except Exception as e:
        print(f"Failed to initialize PostgreSQL pool: {e}")
        print("Falling back to in-memory storage.")
        return None


async def close_pg_pool():
    """
    Close the PostgreSQL connection pool.

    Call this at application shutdown.
    """
    global _pg_pool
    if _pg_pool:
        await _pg_pool.close()
        _pg_pool = None
        print("PostgreSQL connection pool closed")


async def get_pg_conn():
    """
    Get a PostgreSQL connection from the pool.

    Returns:
        asyncpg.Connection or None if pool not initialized
    """
    if not _check_pg_available():
        return None
        
    if _pg_pool is None:
        await init_pg_pool()

    if _pg_pool:
        return await _pg_pool.acquire()
    return None


@asynccontextmanager
async def get_pg_connection():
    """
    Context manager for PostgreSQL connections.

    Automatically releases connection back to pool.

    Usage:
        async with get_pg_connection() as conn:
            if conn:
                result = await conn.fetch(...)
    """
    conn = None
    try:
        if _pg_pool:
            conn = await _pg_pool.acquire()
        yield conn
    finally:
        if conn and _pg_pool:
            await _pg_pool.release(conn)


# =============================================================================
# Runbook Storage and Retrieval (pgvector)
# =============================================================================


async def ensure_runbook_table():
    """
    Create the runbooks table with pgvector extension if it doesn't exist.

    SQL Schema:
        CREATE EXTENSION IF NOT EXISTS vector;
        CREATE TABLE IF NOT EXISTS runbooks (
            id TEXT PRIMARY KEY,
            text TEXT NOT NULL,
            embedding vector(768),
            created_at TIMESTAMPTZ DEFAULT NOW()
        );
        CREATE INDEX IF NOT EXISTS runbooks_embedding_idx
            ON runbooks USING ivfflat (embedding vector_cosine_ops);
    """
    async with get_pg_connection() as conn:
        if conn is None:
            return False

        try:
            await conn.execute("CREATE EXTENSION IF NOT EXISTS vector;")
            await conn.execute(
                f"""
                CREATE TABLE IF NOT EXISTS runbooks (
                    id TEXT PRIMARY KEY,
                    text TEXT NOT NULL,
                    embedding vector({EMBEDDING_DIMENSION}),
                    metadata JSONB DEFAULT '{{}}',
                    created_at TIMESTAMPTZ DEFAULT NOW()
                );
                """
            )
            await conn.execute(
                """
                CREATE INDEX IF NOT EXISTS runbooks_embedding_idx
                ON runbooks USING ivfflat (embedding vector_cosine_ops)
                WITH (lists = 100);
                """
            )
            return True
        except Exception as e:
            print(f"Error creating runbook table: {e}")
            return False


async def insert_runbook(
    id: str,
    text: str,
    embedding: list[float],
    metadata: Optional[dict] = None,
) -> bool:
    """
    Insert a runbook with its embedding.

    Uses PostgreSQL if available, otherwise in-memory storage.

    Args:
        id: Unique identifier for the runbook
        text: Full text of the runbook
        embedding: Vector embedding of the runbook text
        metadata: Optional metadata dictionary

    Returns:
        True if successful
    """
    # Always store in memory as fallback
    _memory_runbooks[id] = {
        "id": id,
        "text": text,
        "embedding": embedding,
        "metadata": metadata or {},
    }
    
    async with get_pg_connection() as conn:
        if conn is None:
            return True  # Memory storage succeeded

        try:
            # Format embedding for pgvector
            embedding_str = f"[{','.join(map(str, embedding))}]"
            metadata_json = json.dumps(metadata or {})

            await conn.execute(
                """
                INSERT INTO runbooks (id, text, embedding, metadata)
                VALUES ($1, $2, $3::vector, $4::jsonb)
                ON CONFLICT (id) DO UPDATE SET
                    text = EXCLUDED.text,
                    embedding = EXCLUDED.embedding,
                    metadata = EXCLUDED.metadata;
                """,
                id,
                text,
                embedding_str,
                metadata_json,
            )
            return True
        except Exception as e:
            print(f"Error inserting runbook to DB: {e}")
            return True  # Memory storage still succeeded


def _cosine_similarity(a: list[float], b: list[float]) -> float:
    """Compute cosine similarity between two vectors."""
    dot = sum(x * y for x, y in zip(a, b))
    norm_a = sum(x * x for x in a) ** 0.5
    norm_b = sum(x * x for x in b) ** 0.5
    if norm_a == 0 or norm_b == 0:
        return 0.0
    return dot / (norm_a * norm_b)


async def query_similar_runbooks(
    vector: list[float],
    k: int = 5,
) -> list[dict[str, Any]]:
    """
    Query for similar runbooks using vector similarity search.

    Uses PostgreSQL with pgvector if available, otherwise
    does brute-force cosine similarity on in-memory storage.

    Args:
        vector: Query embedding vector
        k: Number of results to return

    Returns:
        List of dicts with {id, text, score, metadata}
    """
    # Try PostgreSQL first
    async with get_pg_connection() as conn:
        if conn is not None:
            try:
                # Format vector for query
                vector_str = f"[{','.join(map(str, vector))}]"

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
                        "metadata": json.loads(row["metadata"])
                        if row["metadata"]
                        else {},
                    }
                    for row in rows
                ]
            except Exception as e:
                print(f"Error querying similar runbooks from DB: {e}")
                # Fall through to memory search

    # Fallback: in-memory brute-force similarity search
    if not _memory_runbooks:
        return []
    
    results = []
    for runbook in _memory_runbooks.values():
        if "embedding" in runbook:
            score = _cosine_similarity(vector, runbook["embedding"])
            results.append({
                "id": runbook["id"],
                "text": runbook["text"],
                "score": score,
                "metadata": runbook.get("metadata", {}),
            })
    
    # Sort by score descending and return top k
    results.sort(key=lambda x: x["score"], reverse=True)
    return results[:k]


# =============================================================================
# User Management (Neon Auth Integration)
# =============================================================================


async def upsert_user(
    auth_user_id: str,
    email: Optional[str] = None,
    display_name: Optional[str] = None,
    roles: Optional[list[str]] = None,
    metadata: Optional[dict] = None,
) -> Optional[dict]:
    """
    Insert or update a user after OAuth login.

    Maps Neon Auth user to application user in app.users table.
    On conflict, updates email, display_name, roles, merges metadata,
    and sets last_seen to now().

    Args:
        auth_user_id: Neon Auth user ID (from JWT sub claim)
        email: User's email address
        display_name: User's display name
        roles: List of roles (e.g., ['analyst', 'admin'])
        metadata: Additional user metadata to merge

    Returns:
        Dict with user data if successful, None otherwise

    Example:
        user = await upsert_user(
            auth_user_id="neon_auth_12345",
            email="analyst@company.com",
            display_name="Security Analyst",
            roles=["analyst"],
            metadata={"department": "Security"}
        )
    """
    async with get_pg_connection() as conn:
        if conn is None:
            # Fallback: store in memory
            user_data = {
                "auth_user_id": auth_user_id,
                "email": email,
                "display_name": display_name,
                "roles": roles or [],
                "metadata": metadata or {},
            }
            _memory_sessions[f"user:{auth_user_id}"] = user_data
            return user_data

        try:
            metadata_json = json.dumps(metadata or {})
            roles_array = roles or []

            row = await conn.fetchrow(
                """
                INSERT INTO app.users (auth_user_id, email, display_name, roles, metadata, last_seen)
                VALUES ($1, $2, $3, $4, $5::jsonb, now())
                ON CONFLICT (auth_user_id) DO UPDATE SET
                    email = EXCLUDED.email,
                    display_name = EXCLUDED.display_name,
                    roles = EXCLUDED.roles,
                    metadata = app.users.metadata || EXCLUDED.metadata,
                    last_seen = now()
                RETURNING id, auth_user_id, email, display_name, roles, metadata, created_at, last_seen;
                """,
                auth_user_id,
                email,
                display_name,
                roles_array,
                metadata_json,
            )

            if row:
                return {
                    "id": str(row["id"]),
                    "auth_user_id": row["auth_user_id"],
                    "email": row["email"],
                    "display_name": row["display_name"],
                    "roles": list(row["roles"]) if row["roles"] else [],
                    "metadata": json.loads(row["metadata"]) if row["metadata"] else {},
                    "created_at": row["created_at"].isoformat() if row["created_at"] else None,
                    "last_seen": row["last_seen"].isoformat() if row["last_seen"] else None,
                }
            return None
        except Exception as e:
            print(f"Error upserting user: {e}")
            return None


async def get_user_by_auth_id(auth_user_id: str) -> Optional[dict]:
    """
    Get a user by their Neon Auth user ID.

    Args:
        auth_user_id: Neon Auth user ID

    Returns:
        User dict or None if not found
    """
    async with get_pg_connection() as conn:
        if conn is None:
            # Fallback: check memory
            return _memory_sessions.get(f"user:{auth_user_id}")

        try:
            row = await conn.fetchrow(
                """
                SELECT id, auth_user_id, email, display_name, roles, metadata, created_at, last_seen
                FROM app.users
                WHERE auth_user_id = $1;
                """,
                auth_user_id,
            )

            if row:
                return {
                    "id": str(row["id"]),
                    "auth_user_id": row["auth_user_id"],
                    "email": row["email"],
                    "display_name": row["display_name"],
                    "roles": list(row["roles"]) if row["roles"] else [],
                    "metadata": json.loads(row["metadata"]) if row["metadata"] else {},
                    "created_at": row["created_at"].isoformat() if row["created_at"] else None,
                    "last_seen": row["last_seen"].isoformat() if row["last_seen"] else None,
                }
            return None
        except Exception as e:
            print(f"Error fetching user: {e}")
            return None


# =============================================================================
# Incident Management
# =============================================================================


async def save_incident(
    incident_id: str,
    payload: dict,
    triage_label: Optional[str] = None,
    triage_score: Optional[float] = None,
    explanation: Optional[str] = None,
    reporter_auth_user_id: Optional[str] = None,
) -> Optional[dict]:
    """
    Save an incident to the database.

    Args:
        incident_id: Unique incident identifier (e.g., INC-2024-001)
        payload: Full incident features/data
        triage_label: Severity label (CRITICAL, HIGH, MEDIUM, LOW)
        triage_score: Numeric severity score
        explanation: LLM-generated explanation
        reporter_auth_user_id: Auth ID of user who reported

    Returns:
        Dict with incident data if successful, None otherwise
    """
    async with get_pg_connection() as conn:
        if conn is None:
            # Fallback: store in memory
            incident_data = {
                "incident_id": incident_id,
                "payload": payload,
                "triage_label": triage_label,
                "triage_score": triage_score,
                "explanation": explanation,
                "reporter_auth_user_id": reporter_auth_user_id,
            }
            _memory_sessions[f"incident:{incident_id}"] = incident_data
            return incident_data

        try:
            payload_json = json.dumps(payload)

            row = await conn.fetchrow(
                """
                INSERT INTO app.incidents (incident_id, reporter_auth_user_id, payload, triage_label, triage_score, explanation)
                VALUES ($1, $2, $3::jsonb, $4, $5, $6)
                ON CONFLICT (incident_id) DO UPDATE SET
                    payload = EXCLUDED.payload,
                    triage_label = EXCLUDED.triage_label,
                    triage_score = EXCLUDED.triage_score,
                    explanation = EXCLUDED.explanation,
                    updated_at = now()
                RETURNING id, incident_id, reporter_auth_user_id, payload, triage_label, triage_score, explanation, status, created_at;
                """,
                incident_id,
                reporter_auth_user_id,
                payload_json,
                triage_label,
                triage_score,
                explanation,
            )

            if row:
                return {
                    "id": str(row["id"]),
                    "incident_id": row["incident_id"],
                    "reporter_auth_user_id": row["reporter_auth_user_id"],
                    "payload": json.loads(row["payload"]) if row["payload"] else {},
                    "triage_label": row["triage_label"],
                    "triage_score": row["triage_score"],
                    "explanation": row["explanation"],
                    "status": row["status"],
                    "created_at": row["created_at"].isoformat() if row["created_at"] else None,
                }
            return None
        except Exception as e:
            print(f"Error saving incident: {e}")
            return None


async def get_incident(incident_id: str) -> Optional[dict]:
    """
    Get an incident by its ID.

    Args:
        incident_id: Incident identifier

    Returns:
        Incident dict or None if not found
    """
    async with get_pg_connection() as conn:
        if conn is None:
            return _memory_sessions.get(f"incident:{incident_id}")

        try:
            row = await conn.fetchrow(
                """
                SELECT id, incident_id, reporter_auth_user_id, payload, triage_label, triage_score, 
                       explanation, status, created_at, updated_at
                FROM app.incidents
                WHERE incident_id = $1;
                """,
                incident_id,
            )

            if row:
                return {
                    "id": str(row["id"]),
                    "incident_id": row["incident_id"],
                    "reporter_auth_user_id": row["reporter_auth_user_id"],
                    "payload": json.loads(row["payload"]) if row["payload"] else {},
                    "triage_label": row["triage_label"],
                    "triage_score": row["triage_score"],
                    "explanation": row["explanation"],
                    "status": row["status"],
                    "created_at": row["created_at"].isoformat() if row["created_at"] else None,
                    "updated_at": row["updated_at"].isoformat() if row["updated_at"] else None,
                }
            return None
        except Exception as e:
            print(f"Error fetching incident: {e}")
            return None


# =============================================================================
# Telemetry Logging
# =============================================================================


async def log_telemetry(
    evt_type: str,
    payload: dict,
    trace_id: Optional[str] = None,
    agent_name: Optional[str] = None,
    duration_ms: Optional[float] = None,
) -> bool:
    """
    Log a telemetry event to the database.

    Args:
        evt_type: Event type (e.g., 'triage.start', 'runbook.complete')
        payload: Event data
        trace_id: Distributed trace ID
        agent_name: Which agent produced this event
        duration_ms: Execution duration if applicable

    Returns:
        True if successful
    """
    async with get_pg_connection() as conn:
        if conn is None:
            # Skip telemetry if no DB
            return True

        try:
            payload_json = json.dumps(payload)

            await conn.execute(
                """
                INSERT INTO app.telemetry (trace_id, evt_type, agent_name, payload, duration_ms)
                VALUES ($1, $2, $3, $4::jsonb, $5);
                """,
                trace_id,
                evt_type,
                agent_name,
                payload_json,
                duration_ms,
            )
            return True
        except Exception as e:
            print(f"Error logging telemetry: {e}")
            return False


# =============================================================================
# Generic Query Helpers
# =============================================================================


async def execute_query(query: str, *args) -> Optional[list]:
    """
    Execute a read query and return results.

    Args:
        query: SQL query string
        *args: Query parameters

    Returns:
        List of rows or None if error
    """
    async with get_pg_connection() as conn:
        if conn is None:
            return None

        try:
            rows = await conn.fetch(query, *args)
            return [dict(row) for row in rows]
        except Exception as e:
            print(f"Error executing query: {e}")
            return None


async def execute_command(query: str, *args) -> bool:
    """
    Execute a write command (INSERT, UPDATE, DELETE).

    Args:
        query: SQL command string
        *args: Command parameters

    Returns:
        True if successful
    """
    async with get_pg_connection() as conn:
        if conn is None:
            return False

        try:
            await conn.execute(query, *args)
            return True
        except Exception as e:
            print(f"Error executing command: {e}")
            return False


# =============================================================================
# Redis (Upstash) Connection Management
# =============================================================================

_redis_client = None
_redis_available: Optional[bool] = None


def _check_redis_available() -> bool:
    """Check if Redis is installed and configured."""
    global _redis_available
    if _redis_available is not None:
        return _redis_available
    
    if not os.getenv("UPSTASH_REDIS_REST_URL"):
        _redis_available = False
        return False
    
    try:
        # Try importing one of the redis clients
        try:
            from upstash_redis import Redis  # noqa: F401
        except ImportError:
            import redis  # noqa: F401
        _redis_available = True
    except ImportError:
        _redis_available = False
        print("Redis libraries not installed. Using in-memory cache.")
    
    return _redis_available


def get_redis():
    """
    Get or create Redis client.

    Returns in-memory fallback if Redis not available.

    Returns:
        Redis client or None if not configured
    """
    global _redis_client

    if _redis_client is not None:
        return _redis_client

    if not _check_redis_available():
        return None

    redis_url = os.getenv("UPSTASH_REDIS_REST_URL")
    redis_token = os.getenv("UPSTASH_REDIS_REST_TOKEN")

    if not redis_url:
        return None

    try:
        # Try Upstash REST client first
        if redis_token:
            from upstash_redis import Redis

            _redis_client = Redis(url=redis_url, token=redis_token)
        else:
            # Fall back to standard redis-py
            import redis

            _redis_client = redis.from_url(redis_url)

        print("Redis client initialized")
        return _redis_client
    except ImportError:
        print("Redis library not installed. Using in-memory cache.")
        return None
    except Exception as e:
        print(f"Failed to initialize Redis client: {e}")
        return None


def close_redis():
    """Close Redis client connection."""
    global _redis_client
    if _redis_client:
        try:
            _redis_client.close()
        except AttributeError:
            pass  # Some clients don't have close()
        _redis_client = None
        print("Redis client closed")


# =============================================================================
# Caching Helpers (with in-memory fallback)
# =============================================================================


async def cache_set(
    key: str,
    value: Any,
    ttl: int = REDIS_DEFAULT_TTL,
) -> bool:
    """
    Set a value in the cache.

    Uses Redis if available, otherwise in-memory dict.

    Args:
        key: Cache key
        value: Value to cache (will be JSON serialized)
        ttl: Time-to-live in seconds (ignored for in-memory)

    Returns:
        True if successful
    """
    client = get_redis()
    if client is None:
        # Use in-memory fallback
        _memory_cache[key] = value
        return True

    try:
        serialized = json.dumps(value)
        client.set(key, serialized, ex=ttl)
        return True
    except Exception as e:
        print(f"Cache set error: {e}")
        # Fallback to memory
        _memory_cache[key] = value
        return True


async def cache_get(key: str) -> Optional[Any]:
    """
    Get a value from the cache.

    Uses Redis if available, otherwise in-memory dict.

    Args:
        key: Cache key

    Returns:
        Cached value or None if not found
    """
    client = get_redis()
    if client is None:
        return _memory_cache.get(key)

    try:
        value = client.get(key)
        if value:
            return json.loads(value)
        return None
    except Exception as e:
        print(f"Cache get error: {e}")
        return _memory_cache.get(key)


async def cache_delete(key: str) -> bool:
    """Delete a key from the cache."""
    client = get_redis()
    
    # Always try memory cache too
    _memory_cache.pop(key, None)
    
    if client is None:
        return True

    try:
        client.delete(key)
        return True
    except Exception as e:
        print(f"Cache delete error: {e}")
        return True


# =============================================================================
# Session Management Helpers (with in-memory fallback)
# =============================================================================


async def store_session(
    session_id: str,
    data: dict[str, Any],
    ttl: int = 3600,
) -> bool:
    """
    Store session data.

    Uses Redis if available, otherwise in-memory.

    Args:
        session_id: Unique session identifier
        data: Session data to store
        ttl: Session TTL in seconds

    Returns:
        True if successful
    """
    key = f"session:{session_id}"
    
    # Always store in memory as backup
    _memory_sessions[session_id] = data
    
    return await cache_set(key, data, ttl)


async def get_session(session_id: str) -> Optional[dict[str, Any]]:
    """
    Retrieve session data.

    Args:
        session_id: Session identifier

    Returns:
        Session data or None if not found
    """
    key = f"session:{session_id}"
    
    # Try cache first
    result = await cache_get(key)
    if result:
        return result
    
    # Fallback to memory
    return _memory_sessions.get(session_id)


async def delete_session(session_id: str) -> bool:
    """Delete a session."""
    key = f"session:{session_id}"
    _memory_sessions.pop(session_id, None)
    return await cache_delete(key)


# =============================================================================
# Telemetry Helpers
# =============================================================================


async def log_telemetry(
    event_type: str,
    data: dict[str, Any],
) -> bool:
    """
    Log telemetry data to Redis for later analysis.

    Uses Redis list to store events.

    Args:
        event_type: Type of telemetry event
        data: Event data

    Returns:
        True if successful
    """
    client = get_redis()
    if client is None:
        return False

    try:
        from datetime import datetime

        event = {
            "type": event_type,
            "data": data,
            "timestamp": datetime.utcnow().isoformat(),
        }
        client.lpush("telemetry:events", json.dumps(event))
        # Keep only last 10000 events
        client.ltrim("telemetry:events", 0, 9999)
        return True
    except Exception as e:
        print(f"Telemetry logging error: {e}")
        return False
