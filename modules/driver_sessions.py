"""Short-lived server-side sessions for the driver API."""
from __future__ import annotations

from modules.session_store import SessionStore, valid_csrf

SESSION_COOKIE = "driver_session"
SESSION_TTL_SECONDS = 12 * 60 * 60
_store = SessionStore(SESSION_TTL_SECONDS)


def create_session(driver_id: str) -> tuple[str, dict]:
    return _store.create({"driver_id": driver_id})


def get_session(token: str | None) -> dict | None:
    return _store.get(token)


def select_vehicle(token: str | None, vehicle_id: str) -> None:
    if _store.select_vehicle(token, vehicle_id) is None:
        raise ValueError("Сессия истекла")


def destroy_session(token: str | None) -> None:
    _store.destroy(token)


def reset_sessions() -> None:
    _store.reset()
