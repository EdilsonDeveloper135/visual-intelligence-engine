"""Visual Intelligence Engine — public API (served behind nginx on 127.0.0.1 only)."""

from __future__ import annotations

import logging
import time
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from sqlalchemy import select
from starlette.middleware.base import BaseHTTPMiddleware

from .. import __version__
from ..core.config import get_settings
from ..core.errors import VieError
from ..core.logging import setup_logging
from ..db.models import CustomSchema
from ..db.session import dispose, session_scope
from ..doc_schemas import registry
from ..storage.filestore import get_store
from .broadcaster import broadcaster
from .routers import auth_system, catalog_data, events_camera, observations

log = logging.getLogger("vie.api")
settings = get_settings()
setup_logging(settings.log_level)

SECURITY_HEADERS = {
    "X-Content-Type-Options": "nosniff",
    "X-Frame-Options": "DENY",
    "Referrer-Policy": "no-referrer",
    "Cross-Origin-Resource-Policy": "same-origin",
    "Permissions-Policy": "camera=(self), microphone=(), geolocation=()",
}


@asynccontextmanager
async def lifespan(_app: FastAPI):
    get_store().ensure_dirs()
    try:
        async with session_scope() as s:
            for row in (await s.execute(select(CustomSchema).where(CustomSchema.active.is_(True)))).scalars():
                registry.register_custom(row.definition)
    except Exception:  # noqa: BLE001 - the API must start even if the DB is still migrating
        log.warning("could not load custom schemas at startup")
    broadcaster.start()
    log.info("api started (version %s)", __version__)
    yield
    await broadcaster.stop()
    await dispose()


DESCRIPTION = """
API local del **Visual Intelligence Engine**: observa imágenes, documentos y la cámara, reconoce su contenido
(OCR + modelo multimodal local), extrae datos estructurados, los valida de forma independiente y los guarda
en una memoria visual consultable.

* Autenticación: `POST /api/v1/auth/login` con la clave de acceso local → cookie de sesión `HttpOnly`.
* Toda petición que modifica datos debe provenir del mismo origen (`Origin` exacto).
* Resultados progresivos: `GET /api/v1/events/stream` (SSE) y `WS /api/v1/camera/ws`.
* Operaciones irreversibles en dos pasos con token de confirmación.
"""

app = FastAPI(title="Visual Intelligence Engine API", version=__version__, description=DESCRIPTION,
              lifespan=lifespan, docs_url=None, redoc_url=None, openapi_url="/api/v1/openapi.json")


class GuardMiddleware(BaseHTTPMiddleware):
    """Host allow-list (anti DNS-rebinding), security headers and access logging."""

    async def dispatch(self, request: Request, call_next):
        host = (request.headers.get("host") or "").rsplit(":", 1)[0].strip("[]")
        if host not in settings.allowed_hosts and not request.url.path.startswith("/api/v1/health/live"):
            return JSONResponse({"code": "bad_host", "message": "Host no permitido."}, status_code=400)
        t0 = time.perf_counter()
        response = await call_next(request)
        for k, v in SECURITY_HEADERS.items():
            response.headers.setdefault(k, v)
        if request.url.path.startswith("/api/"):
            response.headers.setdefault("Cache-Control", "no-store")
        if not request.url.path.endswith(("/health/live", "/events/stream")):
            log.info("%s %s -> %s", request.method, request.url.path, response.status_code,
                     extra={"duration_ms": round((time.perf_counter() - t0) * 1000), "path": request.url.path,
                            "status": response.status_code})
        return response


app.add_middleware(GuardMiddleware)


@app.exception_handler(VieError)
async def vie_error(_r: Request, exc: VieError):
    return JSONResponse(exc.to_dict(), status_code=exc.status_code)


@app.exception_handler(RequestValidationError)
async def validation_error(_r: Request, exc: RequestValidationError):
    details = [{"loc": list(e.get("loc", [])), "msg": e.get("msg"), "type": e.get("type")} for e in exc.errors()]
    return JSONResponse({"code": "invalid_request", "message": "La petición no es válida.", "details": details},
                        status_code=422)


@app.exception_handler(Exception)
async def unexpected(_r: Request, exc: Exception):
    log.exception("unhandled error: %s", type(exc).__name__)
    return JSONResponse({"code": "internal_error", "message": "Error interno.", "details": None}, status_code=500)


for r in (auth_system.router, observations.router, events_camera.router, catalog_data.router):
    app.include_router(r, prefix="/api/v1")
