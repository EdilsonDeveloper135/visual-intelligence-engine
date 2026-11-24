"""Worker process: runs pipeline jobs from the PostgreSQL queue.

Two independent lanes run concurrently:
  * fast: decoding / preprocessing / OCR / rules (seconds)
  * vlm : multimodal interpretation and chat (tens of seconds, one at a time)
so OCR results keep flowing while the model is busy.
"""

from __future__ import annotations

import asyncio
import logging
import os
import signal
import socket
import time
import uuid
from datetime import UTC, datetime, timedelta
from pathlib import Path

import asyncpg
from sqlalchemy import select, text

from ..core import runtime
from ..core.config import get_settings
from ..core.errors import ServiceUnavailable, VieError
from ..core.logging import setup_logging
from ..db.models import Asset, AuditLog, Observation
from ..db.session import raw_dsn, session_scope
from ..jobs import queue
from ..jobs.events import emit
from ..pipeline.orchestrator import HANDLERS, Retryable, mark_failed
from ..storage.filestore import get_store

log = logging.getLogger("vie.worker")
HEARTBEAT_FILE = Path(os.environ.get("VIE_WORKER_HEARTBEAT", "/tmp/worker-heartbeat"))
LEASE_S = 60


def _cgroup_stats() -> dict:
    out = {}
    try:
        out["memory_bytes"] = int(Path("/sys/fs/cgroup/memory.current").read_text())
        mx = Path("/sys/fs/cgroup/memory.max").read_text().strip()
        out["memory_limit_bytes"] = None if mx == "max" else int(mx)
    except (OSError, ValueError):
        pass
    return out


class Worker:
    def __init__(self) -> None:
        self.id = f"{socket.gethostname()}-{os.getpid()}-{uuid.uuid4().hex[:6]}"
        self.stop = asyncio.Event()
        self.wake = {"fast": asyncio.Event(), "vlm": asyncio.Event()}
        self.settings = get_settings()

    # -- notifications ---------------------------------------------------------
    async def listen(self) -> None:
        while not self.stop.is_set():
            try:
                conn = await asyncpg.connect(raw_dsn())
                await conn.add_listener("vie_jobs", lambda *a: self.wake.get(a[3], asyncio.Event()).set())
                log.info("listening for job notifications")
                while not self.stop.is_set() and not conn.is_closed():
                    await asyncio.sleep(5)
                await conn.close()
            except Exception:  # noqa: BLE001 - reconnect forever
                log.warning("notification listener lost; retrying in 3s")
                await asyncio.sleep(3)

    # -- lanes ---------------------------------------------------------------------
    async def lane(self, lane: str) -> None:
        while not self.stop.is_set():
            try:
                async with session_scope() as session:
                    job = await queue.claim(session, lane, self.id, LEASE_S)
            except Exception:  # noqa: BLE001 - DB not ready yet
                log.warning("cannot claim jobs (database unavailable?)")
                await asyncio.sleep(3)
                continue
            if job is None:
                self.wake[lane].clear()
                try:
                    await asyncio.wait_for(self.wake[lane].wait(), timeout=2.0)
                except TimeoutError:
                    pass
                continue
            await self.run_job(job)

    async def _heartbeat(self, job_id: uuid.UUID) -> None:
        while True:
            await asyncio.sleep(LEASE_S / 3)
            try:
                async with session_scope() as session:
                    await queue.heartbeat(session, job_id, self.id, LEASE_S)
            except Exception:  # noqa: BLE001
                log.warning("heartbeat failed for job %s", job_id)

    async def run_job(self, job) -> None:
        handler = HANDLERS.get(job.type)
        extra = {"job_id": str(job.id), "job_type": job.type,
                 "observation_id": str(job.observation_id) if job.observation_id else None}
        log.info("job started (attempt %s)", job.attempts, extra=extra)
        hb = asyncio.create_task(self._heartbeat(job.id))
        t0 = time.perf_counter()
        try:
            if handler is None:
                raise VieError("unknown_job", f"Tipo de job desconocido: {job.type}")
            await asyncio.wait_for(handler(job), timeout=self.settings.job_timeout_s)
            async with session_scope() as session:
                await queue.complete(session, job.id)
            log.info("job done", extra={**extra, "duration_ms": round((time.perf_counter() - t0) * 1000)})
        except Exception as exc:  # noqa: BLE001 - classify and record every failure
            retryable = isinstance(exc, (Retryable, ServiceUnavailable, TimeoutError, OSError)) or \
                not isinstance(exc, VieError)
            message = getattr(exc, "message", None) or f"{type(exc).__name__}: {exc}"
            if isinstance(exc, TimeoutError):
                message = f"Tiempo máximo del job excedido ({self.settings.job_timeout_s}s)"
            log.exception("job failed: %s", message, extra=extra) if not isinstance(exc, VieError) \
                else log.warning("job failed: %s", message, extra=extra)
            async with session_scope() as session:
                will_retry = await queue.fail(session, job, message, retryable)
            if will_retry:
                await emit(f"{job.type}.retry", f"Reintentando ({job.attempts}/{job.max_attempts}): {message}",
                           observation_id=job.observation_id, level="warning")
            else:
                await mark_failed(job, message)
        finally:
            hb.cancel()

    # -- maintenance -------------------------------------------------------------------
    async def maintenance(self) -> None:
        while not self.stop.is_set():
            try:
                HEARTBEAT_FILE.write_text(str(time.time()))
                async with session_scope() as session:
                    await runtime.set_value(session, "worker_heartbeat", {
                        "ts": time.time(), "id": self.id, "resources": _cgroup_stats()})
                    for job in await queue.sweep_exhausted(session):
                        await mark_failed(job, job.error or "lease expired")
                    # bounded event log
                    await session.execute(text(
                        "DELETE FROM event_log WHERE id < (SELECT coalesce(max(id), 0) - 20000 FROM event_log)"))
                    await session.execute(text("DELETE FROM auth_sessions WHERE expires_at < now()"))
                await self.retention()
            except Exception:  # noqa: BLE001
                log.exception("maintenance error")
            try:
                await asyncio.wait_for(self.stop.wait(), timeout=10)
            except TimeoutError:
                pass

    async def retention(self) -> None:
        """Purge items that have been in the trash longer than VIE_RETENTION_DAYS (0 = never)."""
        days = self.settings.retention_days
        if days <= 0:
            return
        cutoff = datetime.now(UTC) - timedelta(days=days)
        store = get_store()
        async with session_scope() as session:
            rows = (await session.execute(select(Observation).where(Observation.deleted_at < cutoff).limit(50))
                    ).scalars().all()
            for obs in rows:
                assets = (await session.execute(select(Asset).where(Asset.observation_id == obs.id))).scalars().all()
                originals = [a.path for a in assets if a.kind == "original"]
                store.delete_derived(str(obs.id))
                await session.delete(obs)
                await session.flush()
                for path in originals:
                    still = (await session.execute(select(Asset.id).where(Asset.path == path).limit(1))).first()
                    if still is None:
                        store.delete_original(path)
                session.add(AuditLog(actor="system", action="retention.purge", target_type="observation",
                                     target_id=str(obs.id), details={"retention_days": days}))
            if rows:
                log.info("retention purged %s observations", len(rows))

    async def main(self) -> None:
        get_store().ensure_dirs()
        loop = asyncio.get_running_loop()
        for sig in (signal.SIGTERM, signal.SIGINT):
            loop.add_signal_handler(sig, self.stop.set)
        tasks = [asyncio.create_task(self.listen()), asyncio.create_task(self.lane("fast")),
                 asyncio.create_task(self.lane("vlm")), asyncio.create_task(self.maintenance())]
        log.info("worker %s started", self.id)
        await self.stop.wait()
        for t in tasks:
            t.cancel()
        log.info("worker stopped")


def run() -> None:
    setup_logging(get_settings().log_level)
    asyncio.run(Worker().main())


if __name__ == "__main__":
    run()
