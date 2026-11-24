"""Progress/event notifications: persisted in `event_log` and broadcast with NOTIFY."""

from __future__ import annotations

import json
import logging
import uuid
from datetime import UTC, datetime

from sqlalchemy import text

from ..db.models import EventLog
from ..db.session import session_scope

log = logging.getLogger("vie.events")


def _payload(event: dict) -> str:
    raw = json.dumps(event, ensure_ascii=False, default=str)
    if len(raw.encode()) > 7500:  # NOTIFY payload limit is 8000 bytes
        event = {k: v for k, v in event.items() if k != "data"} | {"truncated": True}
        raw = json.dumps(event, ensure_ascii=False, default=str)[:7500]
    return raw


async def emit(event_type: str, message: str = "", *, observation_id: uuid.UUID | str | None = None,
               level: str = "info", data: dict | None = None, persist: bool = True) -> None:
    """Never raises: event delivery must not break processing."""
    try:
        obs = uuid.UUID(str(observation_id)) if observation_id else None
        event = {"type": event_type, "level": level, "message": message,
                 "observation_id": str(obs) if obs else None, "data": data or {},
                 "ts": datetime.now(UTC).isoformat(timespec="milliseconds")}
        async with session_scope() as s:
            if persist:
                row = EventLog(type=event_type, level=level, message=message[:2000], observation_id=obs,
                               data=data or {})
                s.add(row)
                await s.flush()
                event["id"] = row.id
            await s.execute(text("SELECT pg_notify('vie_events', :p)"), {"p": _payload(event)})
    except Exception:  # noqa: BLE001
        log.exception("could not emit event %s", event_type)
