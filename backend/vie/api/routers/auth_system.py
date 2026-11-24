from __future__ import annotations

import time
from pathlib import Path

from fastapi import APIRouter, Depends, Request, Response
from sqlalchemy import text

from ... import PIPELINE_VERSION, __version__
from ...clients import ollama, vision
from ...core import runtime
from ...core.config import get_settings
from ...core.errors import Unauthorized
from ...db.session import session_scope
from ...jobs import queue
from ..schemas import LoginIn
from ..security import audit, check_access_key, create_session, require_auth, revoke_session, session_valid

router = APIRouter()


@router.post("/auth/login", tags=["auth"], summary="Iniciar sesión con la clave de acceso local")
async def login(body: LoginIn, request: Request, response: Response):
    from ..security import origin_ok
    from ...core.errors import Forbidden

    if not origin_ok(request.headers.get("origin"), request.headers.get("sec-fetch-site")):
        raise Forbidden("bad_origin", "Origen de la petición no permitido.")
    if not check_access_key(body.access_key):
        await audit("auth.login", outcome="denied")
        raise Unauthorized("invalid_key", "Clave de acceso incorrecta.")
    s = get_settings()
    old = request.cookies.get(s.cookie_name)
    await revoke_session(old)  # rotate on login
    token, expires = await create_session(request.headers.get("user-agent"))
    response.set_cookie(s.cookie_name, token, httponly=True, samesite="strict", secure=False, path="/",
                        max_age=s.session_hours * 3600)
    await audit("auth.login")
    return {"authenticated": True, "expires_at": expires.isoformat()}


@router.post("/auth/logout", tags=["auth"], dependencies=[Depends(require_auth)])
async def logout(request: Request, response: Response):
    s = get_settings()
    await revoke_session(request.cookies.get(s.cookie_name))
    response.delete_cookie(s.cookie_name, path="/")
    await audit("auth.logout")
    return {"authenticated": False}


@router.get("/auth/session", tags=["auth"])
async def session_info(request: Request):
    s = get_settings()
    ok = (not s.auth_enabled) or await session_valid(request.cookies.get(s.cookie_name))
    return {"authenticated": ok, "auth_enabled": s.auth_enabled}


@router.get("/health/live", tags=["system"], include_in_schema=True)
async def live():
    return {"status": "ok"}


def _cgroup_stats() -> dict:
    out = {}
    try:
        out["memory_bytes"] = int(Path("/sys/fs/cgroup/memory.current").read_text())
        mx = Path("/sys/fs/cgroup/memory.max").read_text().strip()
        out["memory_limit_bytes"] = None if mx == "max" else int(mx)
        for line in Path("/sys/fs/cgroup/cpu.stat").read_text().splitlines():
            k, v = line.split()
            if k == "usage_usec":
                out["cpu_usage_usec"] = int(v)
    except (OSError, ValueError):
        pass
    return out


@router.get("/health/ready", tags=["system"], dependencies=[Depends(require_auth)])
async def ready():
    return await _status(deep=False)


@router.get("/system/status", tags=["system"], dependencies=[Depends(require_auth)],
            summary="Estado de servicios, modelo activo, cola y recursos")
async def system_status():
    return await _status(deep=True)


async def _status(deep: bool) -> dict:
    s = get_settings()
    t0 = time.perf_counter()
    db = {"status": "ok"}
    model = s.vlm_model
    queue_counts: dict = {}
    worker = None
    try:
        async with session_scope() as session:
            await session.execute(text("SELECT 1"))
            model = await runtime.active_model(session)
            queue_counts = await queue.counts(session)
            worker = await runtime.get_value(session, "worker_heartbeat")
        db["latency_ms"] = round((time.perf_counter() - t0) * 1000)
    except Exception as exc:  # noqa: BLE001
        db = {"status": "error", "error": type(exc).__name__}
    vis = await vision.health()
    ver = await ollama.version()
    tags = []
    try:
        tags = [m.get("name") for m in await ollama.tags()]
    except Exception:  # noqa: BLE001
        pass
    llm = {"status": "ok" if ver else "unreachable", "version": ver, "active_model": model,
           "model_installed": model in tags}
    if deep:
        llm["loaded"] = [{"name": m.get("name"), "size_bytes": m.get("size"), "expires_at": m.get("expires_at")}
                         for m in await ollama.loaded()]
    worker_ok = bool(worker and time.time() - float(worker.get("ts", 0)) < 60)
    overall = "ok" if db["status"] == "ok" and vis.get("status") == "ok" and llm["model_installed"] and worker_ok \
        else "degraded"
    out = {"status": overall, "version": __version__, "pipeline_version": PIPELINE_VERSION, "database": db,
           "vision": vis, "llm": llm, "worker": {"status": "ok" if worker_ok else "unknown", **(worker or {})},
           "queue": queue_counts, "profile": "lite" if "2b" in model else "custom"}
    if deep:
        out["resources"] = {"api": _cgroup_stats(), "worker": (worker or {}).get("resources"),
                            "vision": vis.get("resources")}
    return out
