"""Independent in-memory stores for employee sessions."""
from __future__ import annotations

import secrets
import threading
import time


class SessionStore:
    def __init__(self, ttl_seconds: int):
        self.ttl_seconds = ttl_seconds
        self._lock = threading.RLock()
        self._sessions: dict[str, dict] = {}

    def _purge(self):
        now = time.time()
        for token, session in list(self._sessions.items()):
            if session["expires_at"] <= now:
                self._sessions.pop(token, None)

    def create(self, fields: dict) -> tuple[str, dict]:
        token = secrets.token_urlsafe(32)
        session = {**fields, "csrf_token": secrets.token_urlsafe(24),
                   "created_at": time.time(), "expires_at": time.time() + self.ttl_seconds}
        with self._lock:
            self._purge()
            self._sessions[token] = session
        return token, dict(session)

    def get(self, token: str | None) -> dict | None:
        if not token:
            return None
        with self._lock:
            self._purge()
            session = self._sessions.get(token)
            return dict(session) if session else None

    def select_vehicle(self, token: str | None, vehicle_id: str) -> dict | None:
        with self._lock:
            self._purge()
            session = self._sessions.get(token)
            if session is None:
                return None
            session["vehicle_id"] = vehicle_id
            return dict(session)

    def destroy(self, token: str | None):
        if token:
            with self._lock:
                self._sessions.pop(token, None)

    def reset(self):
        with self._lock:
            self._sessions.clear()


def valid_csrf(session: dict, token: str | None) -> bool:
    return bool(token) and secrets.compare_digest(str(session.get("csrf_token", "")), token)
