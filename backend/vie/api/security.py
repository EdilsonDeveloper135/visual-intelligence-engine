"""Local access control.

* Login with the access key generated at install time -> server-side session
  (only the SHA-256 of the token is stored) -> HttpOnly, SameSite=Strict cookie.
* Cookies do not isolate ports on 127.0.0.1, so every state-changing request and
  every WebSocket handshake must carry an `Origin` that matches exactly
  http://127.0.0.1:<port> or http://localhost:<port> (when present).
* Irreversible operations need a short-lived HMAC confirmation token.
"""

from __future__ import annotations

import hashlib
import hmac
import secrets
import time
from collections import deque
from datetime import UTC, datetime, timedelta

from fastapi import Request, WebSocket
from sqlalchemy import select

from ..core.config import get_settings
from ..core.errors import Forbidden, Unauthorized, VieError
from ..db.models import AuditLog, AuthSession
from ..db.session import session_scope

_cache: dict[str, float] = {}  # token_hash -> cache expiry (monotonic)
_login_attempts: deque[float] = deque(maxlen=50)
SAFE_METHODS = {"GET", "HEAD", "OPTIONS"}


def _hash(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def check_access_key(candidate: str) -> bool:
    now = time.monotonic()
    recent = [t for t in _login_attempts if now - t < 60]
    if len(recent) >= 10:
        raise VieError("too_many_attempts", "Demasiados intentos. Espere un minuto.", status_code=429)
    expected = get_settings().access_key.get_secret_value()
    ok = hmac.compare_digest(candidate.encode(), expected.encode())
    if not ok:
        _login_attempts.append(now)
    return ok


async def create_session(user_agent: str | None) -> tuple[str, datetime]:
    token = secrets.token_urlsafe(32)
    expires = datetime.now(UTC) + timedelta(hours=get_settings().session_hours)
    async with session_scope() as s:
        s.add(AuthSession(token_hash=_hash(token), expires_at=expires, user_agent=(user_agent or "")[:200]))
    return token, expires


async def revoke_session(token: str | None) -> None:
    if not token:
        return
    h = _hash(token)
    _cache.pop(h, None)
    async with session_scope() as s:
        row = await s.get(AuthSession, h)
        if row is not None:
            await s.delete(row)


async def session_valid(token: str | None) -> bool:
    if not token:
        return False
    h = _hash(token)
    now = time.monotonic()
    if _cache.get(h, 0) > now:
        return True
    async with session_scope() as s:
        row = (await s.execute(select(AuthSession).where(AuthSession.token_hash == h))).scalars().first()
        if row is None or row.expires_at < datetime.now(UTC):
            _cache.pop(h, None)
            return False
        row.last_seen_at = datetime.now(UTC)
    _cache[h] = now + 30
    return True


def origin_ok(origin: str | None, sec_fetch_site: str | None = None) -> bool:
    if sec_fetch_site and sec_fetch_site.lower() == "cross-site":
        return False
    if origin is None:
        return True  # non-browser client (it still needs the session cookie)
    return origin in get_settings().allowed_origins


async def require_auth(request: Request) -> None:
    s = get_settings()
    if request.method not in SAFE_METHODS and not origin_ok(request.headers.get("origin"),
                                                            request.headers.get("sec-fetch-site")):
        raise Forbidden("bad_origin", "Origen de la petición no permitido.")
    if not s.auth_enabled:
        return
    if not await session_valid(request.cookies.get(s.cookie_name)):
        raise Unauthorized("not_authenticated", "Sesión no iniciada o expirada.")


async def require_auth_ws(ws: WebSocket) -> bool:
    s = get_settings()
    if not origin_ok(ws.headers.get("origin"), ws.headers.get("sec-fetch-site")) or ws.headers.get("origin") is None:
        return False
    if not s.auth_enabled:
        return True
    return await session_valid(ws.cookies.get(s.cookie_name))


# ---------------------------------------------------------------------------
# Confirmation tokens for irreversible operations
# ---------------------------------------------------------------------------
def make_confirmation(action: str, target: str, ttl_s: int = 120) -> tuple[str, int]:
    exp = int(time.time()) + ttl_s
    msg = f"{action}:{target}:{exp}".encode()
    sig = hmac.new(get_settings().secret_key.get_secret_value().encode(), msg, hashlib.sha256).hexdigest()[:32]
    return f"{exp}.{sig}", exp


def verify_confirmation(action: str, target: str, token: str | None) -> None:
    try:
        exp_s, sig = (token or "").split(".", 1)
        exp = int(exp_s)
    except ValueError as exc:
        raise Forbidden("confirmation_required", "Se requiere confirmación explícita.") from exc
    if exp < time.time():
        raise Forbidden("confirmation_expired", "La confirmación expiró; vuelva a solicitarla.")
    msg = f"{action}:{target}:{exp}".encode()
    expected = hmac.new(get_settings().secret_key.get_secret_value().encode(), msg, hashlib.sha256).hexdigest()[:32]
    if not hmac.compare_digest(sig, expected):
        raise Forbidden("confirmation_invalid", "Confirmación no válida.")


async def audit(action: str, *, target_type: str | None = None, target_id: str | None = None,
                details: dict | None = None, outcome: str = "ok", actor: str = "local-user") -> None:
    async with session_scope() as s:
        s.add(AuditLog(action=action, target_type=target_type, target_id=target_id, details=details or {},
                       outcome=outcome, actor=actor))
