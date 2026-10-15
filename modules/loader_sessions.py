"""Short-lived server-side sessions for the loader workspace."""
from __future__ import annotations

from modules.session_store import SessionStore, valid_csrf

SESSION_COOKIE = "loader_session"
SESSION_TTL_SECONDS = 12 * 60 * 60
_store = SessionStore(SESSION_TTL_SECONDS)


def create_session(loader_id: str) -> tuple[str, dict]:
    return _store.create({"loader_id": loader_id, "role": "loader", "vehicle_id": ""})


def get_session(token: str | None) -> dict | None:
    return _store.get(token)


def select_vehicle(token: str | None, vehicle_id: str) -> dict | None:
    return _store.select_vehicle(token, vehicle_id)


def destroy_session(token: str | None) -> None:
    _store.destroy(token)


def reset_sessions() -> None:
    _store.reset()
