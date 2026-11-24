from __future__ import annotations

import asyncio
import json
import logging
import time
import uuid
from datetime import UTC, datetime

from fastapi import APIRouter, Depends, Query, WebSocket, WebSocketDisconnect
from fastapi.responses import StreamingResponse
from sqlalchemy import select

from ...camera.scene import SceneTracker
from ...clients import vision
from ...core import runtime
from ...core.errors import VieError
from ...db.models import CameraSession, EventLog, Observation
from ...db.session import session_scope
from ...jobs import queue
from ...jobs.events import emit
from .. import services
from ..broadcaster import broadcaster
from ..security import audit, require_auth, require_auth_ws

log = logging.getLogger("vie.api.camera")
router = APIRouter()


@router.get("/events/stream", tags=["events"], dependencies=[Depends(require_auth)],
            summary="Eventos en tiempo real (Server-Sent Events): progreso, resultados, chat")
async def events_stream(observation_id: uuid.UUID | None = None, since_id: int | None = Query(None, ge=0)):
    async def gen():
        q = broadcaster.subscribe()
        try:
            async with session_scope() as session:
                stmt = select(EventLog).order_by(EventLog.id.desc()).limit(50)
                if observation_id:
                    stmt = stmt.where(EventLog.observation_id == observation_id)
                if since_id is not None:
                    stmt = stmt.where(EventLog.id > since_id)
                backlog = list(reversed((await session.execute(stmt)).scalars().all()))
            for e in backlog:
                ev = {"id": e.id, "type": e.type, "level": e.level, "message": e.message,
                      "observation_id": str(e.observation_id) if e.observation_id else None, "data": e.data,
                      "ts": e.ts.isoformat(), "backlog": True}
                yield f"data: {json.dumps(ev, ensure_ascii=False, default=str)}\n\n"
            while True:
                try:
                    ev = await asyncio.wait_for(q.get(), timeout=15)
                except TimeoutError:
                    yield ": keep-alive\n\n"
                    continue
                if observation_id and ev.get("observation_id") != str(observation_id):
                    continue
                yield f"data: {json.dumps(ev, ensure_ascii=False, default=str)}\n\n"
        finally:
            broadcaster.unsubscribe(q)

    return StreamingResponse(gen(), media_type="text/event-stream",
                             headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})


# ---------------------------------------------------------------------------
# Real-time camera
# ---------------------------------------------------------------------------
class CameraSessionManager:
    """Per-connection state. Frames are assessed quickly; only selected frames become observations."""

    def __init__(self, ws: WebSocket, session_id: uuid.UUID, cfg: dict):
        self.ws = ws
        self.id = session_id
        self.cfg = cfg
        self.tracker = SceneTracker(repeat_threshold=int(cfg["repeat_threshold"]),
                                    new_threshold=int(cfg["new_threshold"]),
                                    min_interval_s=float(cfg["min_ocr_interval_s"]))
        self.pending: str | None = None  # observation being processed
        self.last_obs: str | None = None
        self.last_vlm_at = 0.0
        self.last_frame_at = 0.0
        self.stats = {"frames": 0, "ignored": 0, "repeated": 0, "new": 0, "updated": 0, "throttled": 0,
                      "busy": 0, "stabilizing": 0}
        self.observations: set[str] = set()

    async def send(self, msg: dict) -> None:
        await self.ws.send_text(json.dumps(msg, ensure_ascii=False, default=str))

    async def busy(self) -> bool:
        if not self.pending:
            return False
        async with session_scope() as session:
            obs = await session.get(Observation, uuid.UUID(self.pending))
            if obs is None or obs.status not in ("queued", "processing"):
                self.pending = None
                return False
        return True

    async def handle_frame(self, data: bytes) -> None:
        now = time.monotonic()
        if now - self.last_frame_at < 0.25:
            return  # hard rate limit: max 4 frames/s
        self.last_frame_at = now
        self.stats["frames"] += 1
        if len(data) > 2 * 1024 * 1024:
            await self.send({"type": "error", "message": "Fotograma demasiado grande."})
            return
        try:
            a = await vision.assess(data)
        except VieError as exc:
            await self.send({"type": "error", "message": exc.message})
            return
        a["_frame"] = data  # the frame travels with its assessment inside the tracker window
        decision = self.tracker.decide(a, now, can_commit=not await self.busy())
        action = decision.action
        self.stats[action] = self.stats.get(action, 0) + 1
        await self.send({"type": "frame", "action": action, "reason": decision.reason,
                         "distance": decision.distance, "assessment": {k: a.get(k) for k in (
                             "blur_variance", "brightness", "document_area_ratio")},
                         "has_document": a.get("document_quad") is not None, "stats": self.stats})
        if decision.document_appeared:
            await self.send({"type": "document_detected"})
        if action in ("new", "updated"):
            frame = data
            if decision.best_index is not None and decision.best_index < len(self.tracker.window):
                frame = self.tracker.window[decision.best_index].get("_frame", data)
            self.tracker.window.clear()
            await self.create_observation(frame, action)
        elif action == "repeated" and self.last_obs:
            async with session_scope() as session:
                obs = await session.get(Observation, uuid.UUID(self.last_obs))
                if obs is not None:
                    obs.repeat_count += 1
                    obs.last_seen_at = datetime.now(UTC)

    async def create_observation(self, frame: bytes, kind: str) -> None:
        auto_vlm = bool(self.cfg.get("auto_vlm")) and \
            time.monotonic() - self.last_vlm_at >= float(self.cfg["min_vlm_interval_s"])
        mode = "full" if auto_vlm else "ocr_only"
        async with session_scope() as session:
            mime = services.check_upload(frame, "frame.jpg")
            obs = await services.create_observation(
                session, frame, mime, source="camera", filename=f"camara-{datetime.now(UTC):%Y%m%d-%H%M%S}.jpg",
                mode=mode, camera_session_id=self.id, kind=kind,
                supersedes_id=uuid.UUID(self.last_obs) if kind == "updated" and self.last_obs else None,
                priority=queue.PRIORITY["camera"])
            oid = str(obs.id)
        if auto_vlm:
            self.last_vlm_at = time.monotonic()
        self.pending = self.last_obs = oid
        self.tracker.bind_observation(oid)
        self.observations.add(oid)
        await emit("camera.observation", f"Observación {'nueva' if kind == 'new' else 'actualizada'} desde cámara",
                   observation_id=oid, data={"kind": kind, "camera_session_id": str(self.id), "mode": mode})
        await self.send({"type": "observation", "id": oid, "kind": kind, "mode": mode})

    async def analyze_now(self) -> None:
        if not self.last_obs:
            await self.send({"type": "error", "message": "Aún no hay una observación de la cámara."})
            return
        wait = float(self.cfg["min_vlm_interval_s"]) - (time.monotonic() - self.last_vlm_at)
        if wait > 0 and self.last_vlm_at:
            await self.send({"type": "error", "message": f"Espere {wait:.0f} s antes de otra interpretación."})
            return
        async with session_scope() as session:
            obs = await session.get(Observation, uuid.UUID(self.last_obs))
            if obs is None:
                return
            if obs.status in ("queued", "processing"):
                obs.mode = "full"  # the worker will chain the model after OCR
            elif obs.status not in ("interpreting",):
                obs.mode = "full"
                obs.status, obs.stage = "ocr_ready", "awaiting_model"
                await queue.enqueue(session, "interpret", observation_id=obs.id, priority=queue.PRIORITY["camera"],
                                    max_attempts=2)
        self.last_vlm_at = time.monotonic()
        await self.send({"type": "analyze_queued", "id": self.last_obs})

    async def forward_events(self) -> None:
        q = broadcaster.subscribe()
        try:
            while True:
                ev = await q.get()
                if ev.get("observation_id") in self.observations:
                    if ev.get("type") == "camera.relabelled":
                        self.stats["updated"] = max(0, self.stats.get("updated", 0) - 1)
                        self.stats["new"] = self.stats.get("new", 0) + 1
                        await self.send({"type": "stats", "stats": self.stats})
                    await self.send({"type": "event", "event": ev})
        finally:
            broadcaster.unsubscribe(q)


@router.websocket("/camera/ws")
async def camera_ws(ws: WebSocket):
    if not await require_auth_ws(ws):
        await ws.close(code=4401)
        return
    await ws.accept()
    async with session_scope() as session:
        cfg = await runtime.camera_settings(session)
        cs = CameraSession(settings=cfg)
        session.add(cs)
        await session.flush()
        sid = cs.id
    mgr = CameraSessionManager(ws, sid, cfg)
    await audit("camera.session_start", target_type="camera_session", target_id=str(sid))
    await mgr.send({"type": "session", "id": str(sid), "settings": cfg})
    forwarder = asyncio.create_task(mgr.forward_events())
    try:
        while True:
            msg = await ws.receive()
            if msg.get("type") == "websocket.disconnect":
                break
            if msg.get("bytes"):
                await mgr.handle_frame(msg["bytes"])
            elif msg.get("text"):
                try:
                    cmd = json.loads(msg["text"])
                except json.JSONDecodeError:
                    continue
                if cmd.get("type") == "analyze_now":
                    await mgr.analyze_now()
                elif cmd.get("type") == "stop":
                    break
    except WebSocketDisconnect:
        pass
    except Exception:  # noqa: BLE001
        log.exception("camera session error")
    finally:
        forwarder.cancel()
        async with session_scope() as session:
            cs = await session.get(CameraSession, sid)
            if cs is not None:
                cs.ended_at = datetime.now(UTC)
                cs.stats = mgr.stats
        await audit("camera.session_end", target_type="camera_session", target_id=str(sid), details=mgr.stats)
        try:
            await ws.close()
        except Exception:  # noqa: BLE001
            pass
