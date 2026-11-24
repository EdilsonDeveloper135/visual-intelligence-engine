"""Client for the local Ollama server (internal network only)."""

from __future__ import annotations

import json
from collections.abc import AsyncIterator

import httpx

from ..core.config import get_settings
from ..core.errors import ServiceUnavailable

_client: httpx.AsyncClient | None = None
_digests: dict[str, str] = {}


def client() -> httpx.AsyncClient:
    global _client
    if _client is None:
        s = get_settings()
        _client = httpx.AsyncClient(base_url=s.ollama_url, timeout=httpx.Timeout(float(s.vlm_timeout_s), connect=5.0))
    return _client


async def version() -> str | None:
    try:
        r = await client().get("/api/version", timeout=5)
        return r.json().get("version")
    except httpx.HTTPError:
        return None


async def tags() -> list[dict]:
    try:
        r = await client().get("/api/tags", timeout=10)
        r.raise_for_status()
        return r.json().get("models", [])
    except httpx.HTTPError as exc:
        raise ServiceUnavailable("ollama_unavailable", "El servidor de modelos no está disponible.") from exc


async def loaded() -> list[dict]:
    try:
        r = await client().get("/api/ps", timeout=5)
        return r.json().get("models", [])
    except httpx.HTTPError:
        return []


async def digest(model: str) -> str | None:
    if model in _digests:
        return _digests[model]
    try:
        for m in await tags():
            if m.get("name") == model or m.get("model") == model:
                _digests[model] = m.get("digest")
                return _digests[model]
    except ServiceUnavailable:
        return None
    return None


async def chat(body: dict) -> dict:
    try:
        r = await client().post("/api/chat", json={**body, "stream": False})
    except httpx.TimeoutException as exc:
        raise ServiceUnavailable("vlm_timeout", "El modelo multimodal excedió el tiempo máximo.") from exc
    except httpx.HTTPError as exc:
        raise ServiceUnavailable("ollama_unavailable", "El servidor de modelos no está disponible.") from exc
    if r.status_code >= 400:
        raise ServiceUnavailable("vlm_error", f"El modelo devolvió un error ({r.status_code}).",
                                 details=r.text[:300])
    return r.json()


async def chat_stream(body: dict) -> AsyncIterator[dict]:
    try:
        async with client().stream("POST", "/api/chat", json={**body, "stream": True}) as r:
            if r.status_code >= 400:
                await r.aread()
                raise ServiceUnavailable("vlm_error", f"El modelo devolvió un error ({r.status_code}).")
            async for line in r.aiter_lines():
                if line.strip():
                    yield json.loads(line)
    except httpx.TimeoutException as exc:
        raise ServiceUnavailable("vlm_timeout", "El modelo multimodal excedió el tiempo máximo.") from exc
    except httpx.HTTPError as exc:
        raise ServiceUnavailable("ollama_unavailable", "El servidor de modelos no está disponible.") from exc
