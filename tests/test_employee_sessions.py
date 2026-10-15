import pytest

from modules import driver_sessions, loader_sessions, session_store


@pytest.fixture(autouse=True)
def clean_sessions():
    driver_sessions.reset_sessions()
    loader_sessions.reset_sessions()
    yield
    driver_sessions.reset_sessions()
    loader_sessions.reset_sessions()


def test_employee_stores_are_isolated_and_return_copies():
    token, session = driver_sessions.create_session("driver")
    assert loader_sessions.get_session(token) is None
    session["driver_id"] = "another"
    assert driver_sessions.get_session(token)["driver_id"] == "driver"
    copy = driver_sessions.get_session(token)
    copy["driver_id"] = "changed"
    assert driver_sessions.get_session(token)["driver_id"] == "driver"


def test_expiration_and_csrf_keep_previous_contract(monkeypatch):
    clock = [1000.0]
    monkeypatch.setattr(session_store.time, "time", lambda: clock[0])
    token, session = loader_sessions.create_session("loader")
    assert session["role"] == "loader"
    assert session["vehicle_id"] == ""
    assert loader_sessions.valid_csrf(session, session["csrf_token"])
    assert not loader_sessions.valid_csrf(session, "")
    assert not loader_sessions.valid_csrf(session, "wrong")
    clock[0] += loader_sessions.SESSION_TTL_SECONDS
    assert loader_sessions.get_session(token) is None
    assert loader_sessions.select_vehicle(token, "vehicle") is None


def test_vehicle_selection_and_revocation_preserve_facade_behavior():
    driver_token, _ = driver_sessions.create_session("driver")
    loader_token, _ = loader_sessions.create_session("loader")
    assert driver_sessions.select_vehicle(driver_token, "vehicle") is None
    assert loader_sessions.select_vehicle(loader_token, "vehicle")["vehicle_id"] == "vehicle"
    assert driver_sessions.get_session(driver_token)["vehicle_id"] == "vehicle"
    driver_sessions.destroy_session(driver_token)
    loader_sessions.destroy_session(loader_token)
    with pytest.raises(ValueError, match="Сессия истекла"):
        driver_sessions.select_vehicle(driver_token, "vehicle")
    assert loader_sessions.select_vehicle(loader_token, "vehicle") is None
