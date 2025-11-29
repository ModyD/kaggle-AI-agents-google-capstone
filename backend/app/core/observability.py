"""
Structured logging and observability for the application.

This module provides:
- JSON structured logging configuration
- Event logging with trace IDs
- Metrics stubs for Cloud Monitoring integration
- OpenTelemetry integration hooks
"""

import json
import logging
import os
import sys
from datetime import datetime
from functools import lru_cache
from typing import Any, Optional
from uuid import uuid4

# =============================================================================
# Logging Configuration
# =============================================================================

# Log level from environment
LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO").upper()

# Whether to output JSON format
JSON_LOGS = os.getenv("JSON_LOGS", "true").lower() == "true"


class JSONFormatter(logging.Formatter):
    """
    Custom JSON log formatter for structured logging.

    Outputs logs in JSON format suitable for Cloud Logging and log aggregators.
    """

    def format(self, record: logging.LogRecord) -> str:
        """Format log record as JSON."""
        log_data = {
            "timestamp": datetime.utcnow().isoformat() + "Z",
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
            "module": record.module,
            "function": record.funcName,
            "line": record.lineno,
        }

        # Add exception info if present
        if record.exc_info:
            log_data["exception"] = self.formatException(record.exc_info)

        # Add extra fields
        if hasattr(record, "trace_id"):
            log_data["trace_id"] = record.trace_id
        if hasattr(record, "event_name"):
            log_data["event_name"] = record.event_name
        if hasattr(record, "payload"):
            log_data["payload"] = record.payload

        return json.dumps(log_data)


class StandardFormatter(logging.Formatter):
    """Standard text formatter for development."""

    def __init__(self):
        super().__init__(
            fmt="%(asctime)s | %(levelname)-8s | %(name)s:%(funcName)s:%(lineno)d | %(message)s",
            datefmt="%Y-%m-%d %H:%M:%S",
        )


def configure_logging(json_format: Optional[bool] = None) -> None:
    """
    Configure application logging.

    Args:
        json_format: Force JSON format (default: from JSON_LOGS env var)
    """
    use_json = json_format if json_format is not None else JSON_LOGS

    # Remove existing handlers
    root = logging.getLogger()
    for handler in root.handlers[:]:
        root.removeHandler(handler)

    # Create handler
    handler = logging.StreamHandler(sys.stdout)
    handler.setLevel(LOG_LEVEL)

    # Set formatter
    if use_json:
        handler.setFormatter(JSONFormatter())
    else:
        handler.setFormatter(StandardFormatter())

    # Configure root logger
    root.setLevel(LOG_LEVEL)
    root.addHandler(handler)

    # Reduce noise from third-party libraries
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("httpcore").setLevel(logging.WARNING)
    logging.getLogger("urllib3").setLevel(logging.WARNING)


@lru_cache()
def get_logger(name: str = "app") -> logging.Logger:
    """Get a logger instance."""
    return logging.getLogger(name)


# =============================================================================
# Event Logging
# =============================================================================

# Thread-local storage for trace context
_trace_context: dict[str, str] = {}


def set_trace_id(trace_id: str) -> None:
    """Set the current trace ID for the request context."""
    _trace_context["trace_id"] = trace_id


def get_trace_id() -> str:
    """Get the current trace ID or generate a new one."""
    return _trace_context.get("trace_id", uuid4().hex)


def clear_trace_context() -> None:
    """Clear the trace context."""
    _trace_context.clear()


def log_event(
    name: str,
    payload: dict[str, Any],
    trace_id: Optional[str] = None,
    level: str = "INFO",
) -> None:
    """
    Log a structured event.

    Args:
        name: Event name/type
        payload: Event payload data
        trace_id: Correlation ID (uses context if not provided)
        level: Log level

    Example:
        >>> log_event("incident_triaged", {"label": "HIGH", "score": 8})
    """
    logger = get_logger("events")

    trace = trace_id or get_trace_id()

    # Create log record with extra fields
    extra = {
        "trace_id": trace,
        "event_name": name,
        "payload": payload,
    }

    log_method = getattr(logger, level.lower(), logger.info)
    log_method(f"Event: {name}", extra=extra)


def log_a2a_message(
    message_id: str,
    from_agent: str,
    to_agent: str,
    message_type: str,
    payload_summary: str,
    trace_id: Optional[str] = None,
) -> None:
    """
    Log an A2A protocol message.

    Special logging for agent-to-agent communication.

    Args:
        message_id: Unique message identifier
        from_agent: Sending agent name
        to_agent: Receiving agent name
        message_type: Message type
        payload_summary: Brief summary of payload
        trace_id: Correlation ID
    """
    log_event(
        name="a2a_message",
        payload={
            "message_id": message_id,
            "from_agent": from_agent,
            "to_agent": to_agent,
            "type": message_type,
            "payload_summary": payload_summary[:200],
        },
        trace_id=trace_id,
    )


# =============================================================================
# Metrics Stubs
# =============================================================================

# In-memory metrics storage (for development)
_metrics: dict[str, int] = {}


def increment_metric(name: str, value: int = 1, tags: Optional[dict[str, str]] = None) -> None:
    """
    Increment a counter metric.

    In production, this would send to Cloud Monitoring or Prometheus.

    Args:
        name: Metric name
        value: Increment value
        tags: Optional metric tags/labels

    Example:
        >>> increment_metric("incidents_processed", tags={"severity": "HIGH"})
    """
    # Build metric key with tags
    tag_str = ""
    if tags:
        tag_str = "," + ",".join(f"{k}={v}" for k, v in sorted(tags.items()))
    key = f"{name}{tag_str}"

    _metrics[key] = _metrics.get(key, 0) + value

    # Log metric update
    get_logger("metrics").debug(f"Metric: {key} = {_metrics[key]}")


def record_timing(name: str, duration_ms: float, tags: Optional[dict[str, str]] = None) -> None:
    """
    Record a timing metric.

    Args:
        name: Metric name
        duration_ms: Duration in milliseconds
        tags: Optional tags
    """
    log_event(
        name="timing",
        payload={
            "metric": name,
            "duration_ms": duration_ms,
            "tags": tags or {},
        },
    )


def get_metrics() -> dict[str, int]:
    """Get current metric values (for debugging)."""
    return dict(_metrics)


def reset_metrics() -> None:
    """Reset all metrics (for testing)."""
    _metrics.clear()


# =============================================================================
# Cloud Logging Integration
# =============================================================================


def setup_cloud_logging() -> bool:
    """
    Set up Google Cloud Logging integration.

    Attempts to configure google-cloud-logging for production use.

    Returns:
        True if successfully configured, False otherwise
    """
    try:
        from google.cloud import logging as cloud_logging

        client = cloud_logging.Client()
        client.setup_logging()

        get_logger().info("Cloud Logging configured successfully")
        return True

    except ImportError:
        get_logger().warning(
            "google-cloud-logging not installed. Using standard logging."
        )
        return False

    except Exception as e:
        get_logger().warning(f"Cloud Logging setup failed: {e}. Using standard logging.")
        return False


# =============================================================================
# OpenTelemetry Integration Stubs
# =============================================================================


def setup_opentelemetry(service_name: str = "security-agent") -> bool:
    """
    Set up OpenTelemetry tracing.

    Integration point for distributed tracing in production.

    Args:
        service_name: Name of the service for tracing

    Returns:
        True if successfully configured
    """
    try:
        # OpenTelemetry setup would go here
        # from opentelemetry import trace
        # from opentelemetry.sdk.trace import TracerProvider
        # from opentelemetry.sdk.trace.export import BatchSpanProcessor
        # from opentelemetry.exporter.cloud_trace import CloudTraceSpanExporter

        get_logger().info(
            "OpenTelemetry stub configured. "
            "Install opentelemetry packages for full tracing."
        )
        return True

    except Exception as e:
        get_logger().warning(f"OpenTelemetry setup failed: {e}")
        return False


def create_span(name: str) -> Any:
    """
    Create a tracing span (stub).

    In production with OpenTelemetry, this creates actual spans.

    Args:
        name: Span name

    Returns:
        Span context manager (stub)
    """
    from contextlib import nullcontext

    # Return no-op context manager as stub
    return nullcontext()


# =============================================================================
# Initialization
# =============================================================================

# Configure logging on import
configure_logging()
