"""Short-lived server-side sessions for the loader workspace."""

from __future__ import annotations

import secrets
import threading
import time


SESSION_COOKIE = "loader_session"
SESSION_TTL_SECONDS = 12 * 60 * 60

_LOCK = threading.RLock()
_SESSIONS: dict[str, dict] = {}


def _purge() -> None:
    now = time.time()
    for token, session in list(_SESSIONS.items()):
        if session["expires_at"] <= now:
            _SESSIONS.pop(token, None)


def create_session(loader_id: str) -> tuple[str, dict]:
    token = secrets.token_urlsafe(32)
    session = {
        "loader_id": loader_id,
        "role": "loader",
        "vehicle_id": "",
        "csrf_token": secrets.token_urlsafe(24),
        "created_at": time.time(),
        "expires_at": time.time() + SESSION_TTL_SECONDS,
    }
    with _LOCK:
        _purge()
        _SESSIONS[token] = session
    return token, dict(session)


def get_session(token: str | None) -> dict | None:
    if not token:
        return None
    with _LOCK:
        _purge()
        session = _SESSIONS.get(token)
        return dict(session) if session else None


def select_vehicle(token: str | None, vehicle_id: str) -> dict | None:
    if not token:
        return None
    with _LOCK:
        _purge()
        session = _SESSIONS.get(token)
        if not session:
            return None
        session["vehicle_id"] = vehicle_id
        return dict(session)


def destroy_session(token: str | None) -> None:
    if token:
        with _LOCK:
            _SESSIONS.pop(token, None)


def valid_csrf(session: dict, token: str | None) -> bool:
    return bool(token) and secrets.compare_digest(str(session.get("csrf_token", "")), token)


def reset_sessions() -> None:
    with _LOCK:
        _SESSIONS.clear()
