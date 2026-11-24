"""Durable job queue on PostgreSQL (FOR UPDATE SKIP LOCKED + leases).

* A job is claimed by setting a lease (`locked_until`). Running jobs renew it
  with heartbeats. If a worker dies, the lease expires and another worker
  reclaims the job (at-least-once processing; handlers are idempotent).
* `NOTIFY vie_jobs` wakes idle workers immediately; they also poll as fallback.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta

from sqlalchemy import select, text, update
from sqlalchemy.ext.asyncio import AsyncSession

from ..db.models import Job

LANES = {"process": "fast", "retention": "fast", "interpret": "vlm", "chat": "vlm"}
PRIORITY = {"chat": 0, "camera": 1, "upload": 3, "reprocess": 4, "maintenance": 9}


async def enqueue(session: AsyncSession, job_type: str, *, observation_id: uuid.UUID | None = None,
                  payload: dict | None = None, priority: int = 5, max_attempts: int = 3,
                  delay_s: float = 0) -> Job:
    job = Job(type=job_type, lane=LANES[job_type], observation_id=observation_id, payload=payload or {},
              priority=priority, max_attempts=max_attempts,
              run_after=datetime.now(UTC) + timedelta(seconds=delay_s))
    session.add(job)
    await session.flush()
    await session.execute(text("SELECT pg_notify('vie_jobs', :lane)"), {"lane": job.lane})
    return job


CLAIM_SQL = text("""
UPDATE jobs SET status = 'running', locked_by = :worker, locked_until = now() + make_interval(secs => :lease),
       attempts = attempts + 1, started_at = now(), error = NULL
WHERE id = (
    SELECT id FROM jobs
    WHERE lane = :lane AND attempts < max_attempts
      AND ((status = 'queued' AND run_after <= now()) OR (status = 'running' AND locked_until < now()))
    ORDER BY priority, created_at
    FOR UPDATE SKIP LOCKED
    LIMIT 1)
RETURNING id
""")


async def claim(session: AsyncSession, lane: str, worker_id: str, lease_s: int) -> Job | None:
    row = (await session.execute(CLAIM_SQL, {"worker": worker_id, "lease": lease_s, "lane": lane})).first()
    if row is None:
        return None
    return await session.get(Job, row[0])


async def heartbeat(session: AsyncSession, job_id: uuid.UUID, worker_id: str, lease_s: int) -> bool:
    res = await session.execute(
        update(Job).where(Job.id == job_id, Job.locked_by == worker_id, Job.status == "running")
        .values(locked_until=datetime.now(UTC) + timedelta(seconds=lease_s)))
    return res.rowcount == 1


async def complete(session: AsyncSession, job_id: uuid.UUID) -> None:
    await session.execute(update(Job).where(Job.id == job_id).values(
        status="done", finished_at=datetime.now(UTC), locked_until=None))


async def fail(session: AsyncSession, job: Job, error: str, retryable: bool) -> bool:
    """Returns True if the job will be retried."""
    retry = retryable and job.attempts < job.max_attempts
    values = {"error": error[:2000], "locked_until": None, "locked_by": None}
    if retry:
        backoff = min(300, 5 * 3 ** (job.attempts - 1))
        values.update(status="queued", run_after=datetime.now(UTC) + timedelta(seconds=backoff))
    else:
        values.update(status="failed", finished_at=datetime.now(UTC))
    await session.execute(update(Job).where(Job.id == job.id).values(**values))
    return retry


async def sweep_exhausted(session: AsyncSession) -> list[Job]:
    """Jobs whose lease expired after their last allowed attempt: mark them failed."""
    rows = (await session.execute(
        select(Job).where(Job.status == "running", Job.locked_until < datetime.now(UTC),
                          Job.attempts >= Job.max_attempts).with_for_update(skip_locked=True))).scalars().all()
    for job in rows:
        job.status, job.finished_at = "failed", datetime.now(UTC)
        job.error = (job.error or "") + " | lease expired after the last attempt (worker crash or timeout)"
    return list(rows)


async def counts(session: AsyncSession) -> dict:
    rows = (await session.execute(text(
        "SELECT lane, status, count(*) FROM jobs WHERE status IN ('queued','running') GROUP BY lane, status"))).all()
    out: dict = {}
    for lane, status, n in rows:
        out.setdefault(lane, {})[status] = n
    return out
