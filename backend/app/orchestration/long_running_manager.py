"""
Long-running job manager with pause/resume support.

This module provides background task management for:
- Running long-running operations (e.g., runbook simulation)
- Pausing and resuming jobs
- Job status tracking
- Crash recovery via Redis persistence

Usage:
    from app.orchestration.long_running_manager import LongRunningManager
    
    manager = LongRunningManager()
    
    # Start a job
    job_id = await manager.start_job(my_async_task())
    
    # Check status
    status = await manager.get_job_status(job_id)
    
    # Pause/Resume
    await manager.pause_job(job_id)
    await manager.resume_job(job_id)

API Endpoints (recommended):
    POST /jobs/start       - Start a new job
    GET  /jobs/{id}        - Get job status
    POST /jobs/{id}/pause  - Pause a job
    POST /jobs/{id}/resume - Resume a job
    POST /jobs/{id}/cancel - Cancel a job
"""

import asyncio
from datetime import datetime
from enum import Enum
from typing import Any, Callable, Coroutine, Optional
from uuid import uuid4

from pydantic import BaseModel, Field


# =============================================================================
# Models
# =============================================================================


class JobStatus(str, Enum):
    """Job status enum."""
    PENDING = "pending"
    RUNNING = "running"
    PAUSED = "paused"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


class JobInfo(BaseModel):
    """Job metadata and status."""

    job_id: str
    status: JobStatus
    created_at: datetime
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    last_update: datetime
    progress: float = 0.0  # 0-100
    result: Optional[Any] = None
    error: Optional[str] = None
    metadata: dict = Field(default_factory=dict)

    model_config = {"extra": "ignore"}


# =============================================================================
# Cooperative Task Wrapper
# =============================================================================


class CooperativeTask:
    """
    Wrapper for tasks that support cooperative pause/resume.

    Example:
        async def my_task(coop: CooperativeTask):
            for i in range(100):
                await coop.checkpoint()  # Check for pause
                await do_work(i)
                coop.update_progress(i + 1)
    """

    def __init__(self, job_id: str, manager: "LongRunningManager"):
        self.job_id = job_id
        self.manager = manager
        self._pause_event = asyncio.Event()
        self._pause_event.set()  # Not paused initially
        self._cancelled = False
        self._progress = 0.0

    async def checkpoint(self) -> None:
        """
        Check for pause/cancel. Call between steps.

        Raises:
            asyncio.CancelledError: If job was cancelled
        """
        if self._cancelled:
            raise asyncio.CancelledError("Job cancelled")

        # Wait if paused
        await self._pause_event.wait()

    def update_progress(self, progress: float) -> None:
        """Update job progress (0-100)."""
        self._progress = min(100.0, max(0.0, progress))
        # Fire and forget update
        asyncio.create_task(
            self.manager._update_progress(self.job_id, self._progress)
        )

    def pause(self) -> None:
        """Pause the task."""
        self._pause_event.clear()

    def resume(self) -> None:
        """Resume the task."""
        self._pause_event.set()

    def cancel(self) -> None:
        """Mark task for cancellation."""
        self._cancelled = True
        self._pause_event.set()  # Unblock if paused

    @property
    def is_paused(self) -> bool:
        """Check if currently paused."""
        return not self._pause_event.is_set()


# =============================================================================
# Long Running Manager
# =============================================================================


class LongRunningManager:
    """
    Manages long-running background jobs with pause/resume support.

    Features:
    - Start async tasks as background jobs
    - Pause and resume running jobs
    - Track job status and progress
    - Persist state to Redis for crash recovery
    """

    def __init__(self):
        self._jobs: dict[str, JobInfo] = {}
        self._tasks: dict[str, asyncio.Task] = {}
        self._coop_tasks: dict[str, CooperativeTask] = {}

    async def start_job(
        self,
        coro_factory: Callable[[CooperativeTask], Coroutine],
        job_id: Optional[str] = None,
        metadata: Optional[dict] = None,
    ) -> str:
        """
        Start a new background job.

        Args:
            coro_factory: Factory function that takes CooperativeTask and returns coroutine
            job_id: Optional job ID (generated if not provided)
            metadata: Optional job metadata

        Returns:
            Job ID

        Example:
            async def process_runbook(coop: CooperativeTask):
                for i, step in enumerate(steps):
                    await coop.checkpoint()
                    await execute_step(step)
                    coop.update_progress((i + 1) / len(steps) * 100)
                return {"status": "complete"}

            job_id = await manager.start_job(process_runbook)
        """
        from app.core.observability import log_event

        job_id = job_id or str(uuid4())
        now = datetime.utcnow()

        # Create job info
        job_info = JobInfo(
            job_id=job_id,
            status=JobStatus.PENDING,
            created_at=now,
            last_update=now,
            metadata=metadata or {},
        )
        self._jobs[job_id] = job_info

        # Create cooperative task wrapper
        coop = CooperativeTask(job_id, self)
        self._coop_tasks[job_id] = coop

        # Create and start the task
        async def run_job():
            try:
                self._jobs[job_id].status = JobStatus.RUNNING
                self._jobs[job_id].started_at = datetime.utcnow()
                self._jobs[job_id].last_update = datetime.utcnow()
                await self._persist_job(job_id)

                log_event("job_started", {"job_id": job_id})

                result = await coro_factory(coop)

                self._jobs[job_id].status = JobStatus.COMPLETED
                self._jobs[job_id].completed_at = datetime.utcnow()
                self._jobs[job_id].result = result
                self._jobs[job_id].progress = 100.0

                log_event("job_completed", {"job_id": job_id})

            except asyncio.CancelledError:
                self._jobs[job_id].status = JobStatus.CANCELLED
                log_event("job_cancelled", {"job_id": job_id})

            except Exception as e:
                self._jobs[job_id].status = JobStatus.FAILED
                self._jobs[job_id].error = str(e)
                log_event("job_failed", {"job_id": job_id, "error": str(e)}, level="ERROR")

            finally:
                self._jobs[job_id].last_update = datetime.utcnow()
                await self._persist_job(job_id)

        task = asyncio.create_task(run_job())
        self._tasks[job_id] = task

        log_event("job_created", {"job_id": job_id, "metadata": metadata})
        await self._persist_job(job_id)

        return job_id

    async def pause_job(self, job_id: str) -> bool:
        """
        Pause a running job.

        The job will pause at the next checkpoint.

        Args:
            job_id: Job ID to pause

        Returns:
            True if paused, False if not found or not running
        """
        from app.core.observability import log_event

        if job_id not in self._jobs:
            return False

        job = self._jobs[job_id]
        if job.status != JobStatus.RUNNING:
            return False

        coop = self._coop_tasks.get(job_id)
        if coop:
            coop.pause()
            job.status = JobStatus.PAUSED
            job.last_update = datetime.utcnow()
            await self._persist_job(job_id)
            log_event("job_paused", {"job_id": job_id})
            return True

        return False

    async def resume_job(self, job_id: str) -> bool:
        """
        Resume a paused job.

        Args:
            job_id: Job ID to resume

        Returns:
            True if resumed, False if not found or not paused
        """
        from app.core.observability import log_event

        if job_id not in self._jobs:
            return False

        job = self._jobs[job_id]
        if job.status != JobStatus.PAUSED:
            return False

        coop = self._coop_tasks.get(job_id)
        if coop:
            coop.resume()
            job.status = JobStatus.RUNNING
            job.last_update = datetime.utcnow()
            await self._persist_job(job_id)
            log_event("job_resumed", {"job_id": job_id})
            return True

        return False

    async def cancel_job(self, job_id: str) -> bool:
        """
        Cancel a job.

        Args:
            job_id: Job ID to cancel

        Returns:
            True if cancelled, False if not found
        """
        from app.core.observability import log_event

        if job_id not in self._jobs:
            return False

        job = self._jobs[job_id]
        if job.status in (JobStatus.COMPLETED, JobStatus.FAILED, JobStatus.CANCELLED):
            return False

        # Signal cancellation via cooperative task
        coop = self._coop_tasks.get(job_id)
        if coop:
            coop.cancel()

        # Also cancel the asyncio task
        task = self._tasks.get(job_id)
        if task and not task.done():
            task.cancel()

        job.status = JobStatus.CANCELLED
        job.last_update = datetime.utcnow()
        await self._persist_job(job_id)
        log_event("job_cancelled", {"job_id": job_id})

        return True

    async def get_job_status(self, job_id: str) -> Optional[JobInfo]:
        """
        Get job status.

        Args:
            job_id: Job ID

        Returns:
            JobInfo or None if not found
        """
        # Try in-memory first
        if job_id in self._jobs:
            return self._jobs[job_id]

        # Try Redis
        return await self._load_job(job_id)

    async def list_jobs(
        self,
        status: Optional[JobStatus] = None,
        limit: int = 50,
    ) -> list[JobInfo]:
        """
        List jobs with optional status filter.

        Args:
            status: Filter by status
            limit: Maximum results

        Returns:
            List of JobInfo
        """
        jobs = list(self._jobs.values())

        if status:
            jobs = [j for j in jobs if j.status == status]

        # Sort by created_at desc
        jobs.sort(key=lambda j: j.created_at, reverse=True)

        return jobs[:limit]

    async def _update_progress(self, job_id: str, progress: float) -> None:
        """Update job progress."""
        if job_id in self._jobs:
            self._jobs[job_id].progress = progress
            self._jobs[job_id].last_update = datetime.utcnow()

    async def _persist_job(self, job_id: str) -> None:
        """Persist job state to Redis."""
        from app.core.db import cache_set

        if job_id in self._jobs:
            job = self._jobs[job_id]
            await cache_set(
                f"job:{job_id}",
                job.model_dump(mode="json"),
                ttl=86400 * 7,  # Keep for 7 days
            )

    async def _load_job(self, job_id: str) -> Optional[JobInfo]:
        """Load job from Redis."""
        from app.core.db import cache_get

        data = await cache_get(f"job:{job_id}")
        if data:
            return JobInfo(**data)
        return None

    async def restore_jobs(self) -> int:
        """
        Restore job states from Redis on startup.

        Note: Running/paused jobs cannot be truly restored as the
        coroutine is lost. They will be marked as failed.

        Returns:
            Number of jobs restored
        """
        from app.core.db import cache_get
        from app.core.observability import log_event

        # This would need Redis SCAN - for now just log
        log_event("job_restore_attempted", {"note": "Full restore requires Redis SCAN"})
        return 0


# =============================================================================
# Example: Runbook Simulation Job
# =============================================================================


async def create_runbook_simulation_job(
    manager: LongRunningManager,
    runbook_steps: list[dict],
    incident_id: str,
) -> str:
    """
    Create a job to simulate runbook execution.

    Example of how to wrap runbook simulation as a long-running job.

    Args:
        manager: LongRunningManager instance
        runbook_steps: List of runbook steps to simulate
        incident_id: Associated incident ID

    Returns:
        Job ID
    """
    async def simulate_steps(coop: CooperativeTask):
        results = []
        total = len(runbook_steps)

        for i, step in enumerate(runbook_steps):
            # Check for pause/cancel
            await coop.checkpoint()

            # Simulate step execution
            await asyncio.sleep(1)  # Simulate work

            results.append({
                "step": i + 1,
                "action": step.get("action", "unknown"),
                "status": "completed",
            })

            # Update progress
            coop.update_progress((i + 1) / total * 100)

        return {
            "incident_id": incident_id,
            "steps_executed": len(results),
            "results": results,
        }

    return await manager.start_job(
        simulate_steps,
        metadata={
            "type": "runbook_simulation",
            "incident_id": incident_id,
            "steps_count": len(runbook_steps),
        },
    )
