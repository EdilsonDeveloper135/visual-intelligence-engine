"""Runtime settings stored in the database (editable from the UI)."""

from __future__ import annotations

from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from ..db.models import Setting
from .config import get_settings

DEFAULTS: dict[str, Any] = {
    "active_model": None,  # falls back to VIE_VLM_MODEL
    "camera": {"interval_ms": 1500, "min_ocr_interval_s": None, "min_vlm_interval_s": None, "auto_vlm": None,
               "repeat_threshold": 6, "new_threshold": 18},
}


async def get_value(session: AsyncSession, key: str) -> Any:
    row = await session.get(Setting, key)
    if row is not None and "v" in row.value:
        return row.value["v"]
    return DEFAULTS.get(key)


async def set_value(session: AsyncSession, key: str, value: Any) -> None:
    row = await session.get(Setting, key)
    if row is None:
        session.add(Setting(key=key, value={"v": value}))
    else:
        row.value = {"v": value}


async def active_model(session: AsyncSession) -> str:
    return (await get_value(session, "active_model")) or get_settings().vlm_model


async def camera_settings(session: AsyncSession) -> dict:
    s = get_settings()
    stored = await get_value(session, "camera") or {}
    merged = {**DEFAULTS["camera"], **stored}
    merged["min_ocr_interval_s"] = merged.get("min_ocr_interval_s") or s.camera_min_ocr_interval_s
    merged["min_vlm_interval_s"] = merged.get("min_vlm_interval_s") or s.camera_min_vlm_interval_s
    if merged.get("auto_vlm") is None:
        merged["auto_vlm"] = s.camera_auto_vlm
    return merged
