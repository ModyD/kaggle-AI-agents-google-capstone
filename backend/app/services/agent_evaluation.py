"""
Agent evaluation and metrics collection.

This module provides:
- Metrics recording and aggregation
- Runbook quality evaluation heuristics
- Evaluation result persistence
- Dashboard-ready metrics snapshots

Usage:
    from app.services.agent_evaluation import record_metric, evaluate_runbook_quality, get_metrics_snapshot
    
    # Record a metric
    record_metric("triage_latency_ms", 150.5, labels={"severity": "HIGH"})
    
    # Evaluate runbook quality
    result = await evaluate_runbook_quality(runbook_dict)
    print(f"Quality score: {result.value}")
    
    # Get metrics for dashboard
    snapshot = await get_metrics_snapshot()

Notebook Integration:
    # In a Jupyter notebook
    import matplotlib.pyplot as plt
    from app.services.agent_evaluation import get_metrics_snapshot
    
    snapshot = await get_metrics_snapshot()
    # Plot metrics over time
"""

import asyncio
from collections import defaultdict
from datetime import datetime
from typing import Any, Optional

from pydantic import BaseModel, Field


# =============================================================================
# Models
# =============================================================================


class EvaluationResult(BaseModel):
    """Result of an evaluation with metric, value, and details."""

    metric: str = Field(..., description="Metric name")
    value: float = Field(..., description="Metric value (0-1 for scores)")
    details: dict = Field(default_factory=dict, description="Detailed breakdown")
    timestamp: datetime = Field(default_factory=datetime.utcnow)

    model_config = {"extra": "ignore"}


class MetricEntry(BaseModel):
    """A single metric data point."""

    name: str
    value: float
    labels: dict = Field(default_factory=dict)
    timestamp: datetime = Field(default_factory=datetime.utcnow)


# =============================================================================
# In-Memory Metrics Store (asyncio-safe)
# =============================================================================


class MetricsStore:
    """Thread-safe in-memory metrics storage."""

    def __init__(self):
        self._lock = asyncio.Lock()
        self._counters: dict[str, float] = defaultdict(float)
        self._gauges: dict[str, float] = {}
        self._histograms: dict[str, list[float]] = defaultdict(list)
        self._history: list[MetricEntry] = []
        self._max_history = 1000

    async def increment(self, name: str, value: float = 1.0, labels: Optional[dict] = None):
        """Increment a counter."""
        async with self._lock:
            key = self._make_key(name, labels)
            self._counters[key] += value
            self._add_history(name, self._counters[key], labels)

    async def set_gauge(self, name: str, value: float, labels: Optional[dict] = None):
        """Set a gauge value."""
        async with self._lock:
            key = self._make_key(name, labels)
            self._gauges[key] = value
            self._add_history(name, value, labels)

    async def observe(self, name: str, value: float, labels: Optional[dict] = None):
        """Add observation to histogram."""
        async with self._lock:
            key = self._make_key(name, labels)
            self._histograms[key].append(value)
            # Keep last 100 observations per metric
            if len(self._histograms[key]) > 100:
                self._histograms[key] = self._histograms[key][-100:]
            self._add_history(name, value, labels)

    def _make_key(self, name: str, labels: Optional[dict]) -> str:
        """Create unique key from name and labels."""
        if not labels:
            return name
        label_str = ",".join(f"{k}={v}" for k, v in sorted(labels.items()))
        return f"{name}{{{label_str}}}"

    def _add_history(self, name: str, value: float, labels: Optional[dict]):
        """Add entry to history."""
        self._history.append(MetricEntry(name=name, value=value, labels=labels or {}))
        if len(self._history) > self._max_history:
            self._history = self._history[-self._max_history:]

    async def get_snapshot(self) -> dict:
        """Get current metrics snapshot."""
        async with self._lock:
            snapshot = {
                "counters": dict(self._counters),
                "gauges": dict(self._gauges),
                "histograms": {},
                "recent_history": [e.model_dump() for e in self._history[-50:]],
                "timestamp": datetime.utcnow().isoformat(),
            }

            # Compute histogram stats
            for key, values in self._histograms.items():
                if values:
                    snapshot["histograms"][key] = {
                        "count": len(values),
                        "min": min(values),
                        "max": max(values),
                        "avg": sum(values) / len(values),
                        "p50": sorted(values)[len(values) // 2],
                        "p95": sorted(values)[int(len(values) * 0.95)] if len(values) >= 20 else None,
                    }

            return snapshot


# Global metrics store
_metrics_store = MetricsStore()


# =============================================================================
# Metrics Recording
# =============================================================================


def record_metric(
    name: str,
    value: float,
    labels: Optional[dict] = None,
    metric_type: str = "gauge",
) -> None:
    """
    Record a metric value.

    Args:
        name: Metric name (e.g., 'triage_latency_ms', 'runbook_quality')
        value: Metric value
        labels: Optional labels for metric dimensions
        metric_type: Type of metric ('counter', 'gauge', 'histogram')

    Example:
        >>> record_metric("incidents_processed", 1, labels={"severity": "HIGH"}, metric_type="counter")
        >>> record_metric("llm_latency_ms", 245.5, metric_type="histogram")
    """
    from app.core.observability import log_event

    # Log the metric
    log_event(
        "metric_recorded",
        {
            "name": name,
            "value": value,
            "labels": labels or {},
            "type": metric_type,
        },
    )

    # Store in memory (fire and forget)
    asyncio.create_task(_record_metric_async(name, value, labels, metric_type))


async def _record_metric_async(
    name: str,
    value: float,
    labels: Optional[dict],
    metric_type: str,
):
    """Async helper to record metric."""
    if metric_type == "counter":
        await _metrics_store.increment(name, value, labels)
    elif metric_type == "histogram":
        await _metrics_store.observe(name, value, labels)
    else:  # gauge
        await _metrics_store.set_gauge(name, value, labels)


# =============================================================================
# Runbook Quality Evaluation
# =============================================================================

# Forbidden phrases that indicate low-quality runbooks
FORBIDDEN_PHRASES = [
    "todo",
    "fixme",
    "placeholder",
    "example only",
    "not implemented",
    "coming soon",
    "tbd",
    "insert here",
]


async def evaluate_runbook_quality(
    runbook: dict,
    reference_good: Optional[dict] = None,
) -> EvaluationResult:
    """
    Evaluate runbook quality using heuristics.

    Scoring criteria (0-1 scale):
    - Steps count: 3-10 steps is ideal
    - Step detail: Each step should have adequate detail (20-500 chars)
    - No forbidden phrases
    - Presence of verification steps
    - Clear action verbs

    Args:
        runbook: Runbook dict with 'steps', 'title', etc.
        reference_good: Optional reference runbook for comparison

    Returns:
        EvaluationResult with overall score and breakdown

    Example:
        >>> runbook = {"title": "Isolate Host", "steps": [...]}
        >>> result = await evaluate_runbook_quality(runbook)
        >>> print(f"Score: {result.value:.2f}")
    """
    from app.core.db import cache_set
    from app.core.observability import log_event

    details: dict[str, Any] = {}
    scores: list[float] = []

    # Extract steps
    steps = runbook.get("steps", [])
    if isinstance(steps, list):
        if steps and isinstance(steps[0], dict):
            step_texts = [s.get("description", s.get("text", str(s))) for s in steps]
        else:
            step_texts = [str(s) for s in steps]
    else:
        step_texts = []

    # 1. Steps count score
    step_count = len(step_texts)
    if 3 <= step_count <= 10:
        steps_score = 1.0
    elif step_count < 3:
        steps_score = step_count / 3
    else:
        steps_score = max(0.5, 1.0 - (step_count - 10) * 0.05)
    scores.append(steps_score)
    details["steps_count"] = {"count": step_count, "score": steps_score}

    # 2. Step detail score (average length)
    if step_texts:
        avg_length = sum(len(s) for s in step_texts) / len(step_texts)
        if 20 <= avg_length <= 500:
            detail_score = 1.0
        elif avg_length < 20:
            detail_score = avg_length / 20
        else:
            detail_score = max(0.5, 1.0 - (avg_length - 500) * 0.001)
    else:
        avg_length = 0
        detail_score = 0.0
    scores.append(detail_score)
    details["step_detail"] = {"avg_length": avg_length, "score": detail_score}

    # 3. Forbidden phrases check
    all_text = " ".join(step_texts).lower()
    title = runbook.get("title", "").lower()
    full_text = f"{title} {all_text}"

    forbidden_found = [phrase for phrase in FORBIDDEN_PHRASES if phrase in full_text]
    forbidden_score = 1.0 if not forbidden_found else max(0.0, 1.0 - len(forbidden_found) * 0.2)
    scores.append(forbidden_score)
    details["forbidden_phrases"] = {"found": forbidden_found, "score": forbidden_score}

    # 4. Verification steps presence
    verification_keywords = ["verify", "confirm", "check", "validate", "ensure", "test"]
    has_verification = any(kw in full_text for kw in verification_keywords)
    verification_score = 1.0 if has_verification else 0.5
    scores.append(verification_score)
    details["verification"] = {"present": has_verification, "score": verification_score}

    # 5. Action verbs at start
    action_verbs = ["isolate", "block", "disable", "enable", "run", "execute", "deploy", "update", "restart", "stop", "start", "configure", "remove", "add", "create", "delete"]
    steps_with_verbs = sum(
        1 for s in step_texts if any(s.lower().strip().startswith(v) for v in action_verbs)
    )
    verb_ratio = steps_with_verbs / max(len(step_texts), 1)
    verb_score = min(1.0, verb_ratio + 0.3)  # Bonus for having some action verbs
    scores.append(verb_score)
    details["action_verbs"] = {"ratio": verb_ratio, "score": verb_score}

    # Overall score (weighted average)
    weights = [0.2, 0.25, 0.2, 0.15, 0.2]  # steps, detail, forbidden, verification, verbs
    overall_score = sum(s * w for s, w in zip(scores, weights))

    result = EvaluationResult(
        metric="runbook_quality",
        value=round(overall_score, 3),
        details=details,
    )

    # Record metric
    record_metric("runbook_quality", overall_score, metric_type="histogram")

    # Cache result
    runbook_id = runbook.get("id", runbook.get("runbook_id", "unknown"))
    await cache_set(
        f"eval:runbook:{runbook_id}",
        result.model_dump(),
        ttl=3600,
    )

    log_event(
        "runbook_evaluated",
        {
            "runbook_id": runbook_id,
            "score": overall_score,
            "step_count": step_count,
        },
    )

    return result


# =============================================================================
# Safety Evaluation (Placeholder)
# =============================================================================


async def evaluate_safety(
    content: str,
    context: Optional[str] = None,
) -> EvaluationResult:
    """
    Evaluate content safety.

    TODO: Expand with automated safety scoring using:
    - Vertex AI Safety Attributes
    - Custom policy checks
    - Dangerous command detection

    Args:
        content: Content to evaluate
        context: Optional context for evaluation

    Returns:
        EvaluationResult with safety score
    """
    # Basic safety heuristics
    dangerous_patterns = [
        "rm -rf",
        "format c:",
        "drop table",
        "delete from",
        "exec(",
        "eval(",
        "password",
        "secret",
        "api_key",
    ]

    content_lower = content.lower()
    violations = [p for p in dangerous_patterns if p in content_lower]

    score = 1.0 if not violations else max(0.0, 1.0 - len(violations) * 0.15)

    return EvaluationResult(
        metric="safety",
        value=score,
        details={
            "violations": violations,
            "content_length": len(content),
        },
    )


# =============================================================================
# Metrics Snapshot
# =============================================================================


async def get_metrics_snapshot() -> dict:
    """
    Get current metrics snapshot for dashboard consumption.

    Returns:
        Dict with counters, gauges, histograms, and recent history

    Example:
        >>> snapshot = await get_metrics_snapshot()
        >>> print(f"Total incidents: {snapshot['counters'].get('incidents_processed', 0)}")
    """
    return await _metrics_store.get_snapshot()


async def get_evaluation_history(
    metric: str = "runbook_quality",
    limit: int = 20,
) -> list[dict]:
    """
    Get recent evaluation results from cache.

    Args:
        metric: Metric name to filter
        limit: Maximum results

    Returns:
        List of evaluation result dicts
    """
    from app.core.db import cache_get

    # This would need a proper index in Redis
    # For now, return from in-memory history
    snapshot = await get_metrics_snapshot()
    history = [
        e for e in snapshot.get("recent_history", []) if e.get("name") == metric
    ]
    return history[:limit]


# =============================================================================
# Persistence Helpers
# =============================================================================


async def persist_metrics_to_redis() -> bool:
    """
    Persist current metrics snapshot to Redis.

    Call periodically to ensure metrics survive restarts.
    """
    from app.core.db import cache_set

    snapshot = await get_metrics_snapshot()
    return await cache_set("metrics:snapshot", snapshot, ttl=86400)


async def restore_metrics_from_redis() -> bool:
    """
    Restore metrics from Redis on startup.

    Call during app initialization to recover state.
    """
    from app.core.db import cache_get

    snapshot = await cache_get("metrics:snapshot")
    if not snapshot:
        return False

    # Restore counters and gauges
    async with _metrics_store._lock:
        _metrics_store._counters.update(snapshot.get("counters", {}))
        _metrics_store._gauges.update(snapshot.get("gauges", {}))

    return True
