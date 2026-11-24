"""Fan-out of `vie_events` notifications to SSE / WebSocket subscribers."""

from __future__ import annotations

import asyncio
import json
import logging

import asyncpg

from ..db.session import raw_dsn

log = logging.getLogger("vie.broadcaster")


class Broadcaster:
    def __init__(self) -> None:
        self._subs: set[asyncio.Queue] = set()
        self._task: asyncio.Task | None = None
        self._stop = asyncio.Event()

    def subscribe(self, maxsize: int = 500) -> asyncio.Queue:
        q: asyncio.Queue = asyncio.Queue(maxsize=maxsize)
        self._subs.add(q)
        return q

    def unsubscribe(self, q: asyncio.Queue) -> None:
        self._subs.discard(q)

    def publish(self, event: dict) -> None:
        for q in list(self._subs):
            try:
                q.put_nowait(event)
            except asyncio.QueueFull:  # slow consumer: drop oldest
                try:
                    q.get_nowait()
                    q.put_nowait(event)
                except Exception:  # noqa: BLE001
                    pass

    def _on_notify(self, _conn, _pid, _channel, payload: str) -> None:
        try:
            self.publish(json.loads(payload))
        except json.JSONDecodeError:
            log.warning("invalid event payload")

    async def _run(self) -> None:
        while not self._stop.is_set():
            try:
                conn = await asyncpg.connect(raw_dsn())
                await conn.add_listener("vie_events", self._on_notify)
                log.info("event broadcaster listening")
                while not self._stop.is_set() and not conn.is_closed():
                    await asyncio.sleep(5)
                await conn.close()
            except Exception:  # noqa: BLE001
                log.warning("event listener disconnected; retrying in 3s")
                await asyncio.sleep(3)

    def start(self) -> None:
        self._task = asyncio.create_task(self._run())

    async def stop(self) -> None:
        self._stop.set()
        if self._task:
            self._task.cancel()


broadcaster = Broadcaster()
