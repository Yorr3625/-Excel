"""Short-lived server-side sessions for the administrative dashboard."""

from __future__ import annotations

import hashlib
import secrets
import threading
import time


SESSION_COOKIE = "dashboard_session"
SESSION_TTL_SECONDS = 12 * 60 * 60

_LOCK = threading.RLock()
_SESSIONS: dict[str, float] = {}


def _key(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def _purge() -> None:
    now = time.time()
    for key, expires_at in list(_SESSIONS.items()):
        if expires_at <= now:
            _SESSIONS.pop(key, None)


def create_session() -> str:
    token = secrets.token_urlsafe(32)
    with _LOCK:
        _purge()
        _SESSIONS[_key(token)] = time.time() + SESSION_TTL_SECONDS
    return token


def valid_session(token: str | None) -> bool:
    if not token:
        return False
    with _LOCK:
        _purge()
        return _key(token) in _SESSIONS


def destroy_session(token: str | None) -> None:
    if token:
        with _LOCK:
            _SESSIONS.pop(_key(token), None)


def reset_sessions() -> None:
    with _LOCK:
        _SESSIONS.clear()
