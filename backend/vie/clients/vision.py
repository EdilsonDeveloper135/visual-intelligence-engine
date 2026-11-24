"""Client for the internal vision engine."""

from __future__ import annotations

import httpx

from ..core.config import get_settings
from ..core.errors import ServiceUnavailable, Unprocessable

_client: httpx.AsyncClient | None = None


def client() -> httpx.AsyncClient:
    global _client
    if _client is None:
        _client = httpx.AsyncClient(base_url=get_settings().vision_url,
                                    timeout=httpx.Timeout(180.0, connect=5.0),
                                    headers={"content-type": "application/octet-stream"})
    return _client


async def _post(path: str, data: bytes, params: dict | None = None) -> dict:
    try:
        r = await client().post(path, content=data, params=params)
    except httpx.TimeoutException as exc:
        raise ServiceUnavailable("vision_timeout", "El motor de visión no respondió a tiempo.") from exc
    except httpx.HTTPError as exc:
        raise ServiceUnavailable("vision_unavailable", "El motor de visión no está disponible.") from exc
    if r.status_code in (413, 422, 400):
        body = r.json() if r.headers.get("content-type", "").startswith("application/json") else {}
        detail = body.get("detail", body) if isinstance(body, dict) else {}
        if isinstance(detail, dict):
            raise Unprocessable(detail.get("code", "invalid_media"), detail.get("message", "Archivo no válido."))
        raise Unprocessable("invalid_media", "Archivo no válido.")
    if r.status_code >= 500:
        raise ServiceUnavailable("vision_error", "Error interno del motor de visión.")
    r.raise_for_status()
    return r.json()


async def inspect(data: bytes) -> dict:
    return await _post("/v1/inspect", data)


async def analyze(data: bytes, page: int = 0, *, ocr: str = "auto", preprocess: bool = True) -> dict:
    return await _post("/v1/analyze", data, {"page": page, "ocr": ocr, "preprocess_image": preprocess})


async def assess(frame: bytes) -> dict:
    return await _post("/v1/assess", frame)


async def health() -> dict:
    try:
        r = await client().get("/health", timeout=5)
        return r.json() if r.status_code == 200 else {"status": "error", "http": r.status_code}
    except httpx.HTTPError as exc:
        return {"status": "unreachable", "error": type(exc).__name__}


async def video_keyframes(data: bytes, max_keyframes: int) -> dict:
    return await _post("/v1/video/keyframes", data, {"max_keyframes": max_keyframes})
