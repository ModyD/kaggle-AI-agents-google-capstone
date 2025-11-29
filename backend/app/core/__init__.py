"""
Core infrastructure modules.

This package contains:
- Database connection management (PostgreSQL, Redis)
- Observability (logging, metrics, tracing)
"""

from .db import (
    init_pg_pool,
    close_pg_pool,
    get_pg_connection,
    get_pg_conn,
    close_redis,
    get_redis,
    cache_get,
    cache_set,
    cache_delete,
    insert_runbook,
    query_similar_runbooks,
    upsert_user,
    get_user_by_auth_id,
    save_incident,
    get_incident,
    log_telemetry,
    execute_query,
    execute_command,
    store_session,
    get_session,
    delete_session,
)
from .observability import (
    configure_logging,
    get_logger,
    log_event,
    set_trace_id,
    get_trace_id,
    clear_trace_context,
    log_a2a_message,
    setup_cloud_logging,
)

__all__ = [
    # Database
    "init_pg_pool",
    "close_pg_pool",
    "get_pg_connection",
    "get_pg_conn",
    "close_redis",
    "get_redis",
    "cache_get",
    "cache_set",
    "cache_delete",
    "insert_runbook",
    "query_similar_runbooks",
    "upsert_user",
    "get_user_by_auth_id",
    "save_incident",
    "get_incident",
    "log_telemetry",
    "execute_query",
    "execute_command",
    "store_session",
    "get_session",
    "delete_session",
    # Observability
    "configure_logging",
    "get_logger",
    "log_event",
    "set_trace_id",
    "get_trace_id",
    "clear_trace_context",
    "log_a2a_message",
    "setup_cloud_logging",
]
