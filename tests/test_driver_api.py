from pathlib import Path

import pytest
from openpyxl import Workbook
from starlette.testclient import TestClient

from modules import driver_mileage, driver_orders, fleet, paths
from orders_dashboard.orders_dashboard import custom_api


@pytest.fixture
def driver_api_fixture(tmp_path, monkeypatch):
    config_dir = tmp_path / "config"
    data_dir = tmp_path / "data"
    fleet_file = config_dir / "fleet.json"
    assignments_file = data_dir / "order_route_assignments.json"
    driver_orders_dir = data_dir / "driver_orders"
    mileage_file = data_dir / "driver_mileage.json"
    monkeypatch.setattr(paths, "DATA_DIR", data_dir)
    monkeypatch.setattr(paths, "DRIVER_ORDERS_FOLDER", driver_orders_dir)
    monkeypatch.setattr(paths, "FLEET_FILE", fleet_file)
    monkeypatch.setattr(paths, "ORDER_ROUTE_ASSIGNMENTS_FILE", assignments_file)
    monkeypatch.setattr(paths, "DRIVER_MILEAGE_FILE", mileage_file)
    monkeypatch.setattr(fleet, "FLEET_FILE", fleet_file)
    monkeypatch.setattr(fleet, "ORDER_ROUTE_ASSIGNMENTS_FILE", assignments_file)
    monkeypatch.setattr(driver_mileage, "MILEAGE_FILE", mileage_file)

    driver = fleet.add_driver("Иван")
    fleet.set_driver_pin(driver["id"], "1234")

    output = tmp_path / "processed.xlsx"
    workbook = Workbook()
    sheet = workbook.active
    sheet.title = "Маршрут №1"
    sheet.append(["Товар", "Сумма", "фм 10"])
    sheet.append(["Яблоки", "", 10])
    workbook.save(output)
    snapshot = driver_orders.build_assignment_snapshot(
        output,
        "Город",
        {
            "route": "route_1",
            "label": "Маршрут №1",
            "driver_id": driver["id"],
            "driver_name": driver["name"],
            "vehicle_id": "vehicle-1",
            "vehicle_name": "Газель",
            "vehicle_plate": "А123ВС71",
            "order_file": "order.xlsx",
        },
    )
    driver_orders.save_snapshot(snapshot)
    return driver, snapshot


@pytest.fixture
def client():
    return TestClient(custom_api)


def submit_mileage(client, login, odometer_km="12345"):
    mileage = login.json()["mileage"]
    return client.post(
        "/api/driver/mileage",
        headers={"x-driver-csrf": login.json()["csrf_token"]},
        json={
            "odometer_km": odometer_km,
            "vehicle_id": mileage["vehicle"]["id"],
            "date": mileage["date"],
            "assignment_id": mileage["assignment_id"],
        },
    )


def test_driver_api_requires_session(client, driver_api_fixture):
    response = client.get("/api/driver/order")
    assert response.status_code == 401


def test_driver_api_login_csrf_and_completion(client, driver_api_fixture):
    driver, snapshot = driver_api_fixture
    login = client.post(
        "/api/driver/login",
        json={"driver_id": driver["id"], "pin": "1234"},
    )
    assert login.status_code == 200
    csrf = login.json()["csrf_token"]
    assert login.json()["driver"]["id"] == driver["id"]
    assert login.json()["mileage"]["required"] is True

    blocked = client.get("/api/driver/order")
    assert blocked.status_code == 409
    assert blocked.json()["mileage"]["required"] is True

    saved = submit_mileage(client, login)
    assert saved.status_code == 200
    assert saved.json()["mileage"]["required"] is False

    order = client.get("/api/driver/order")
    assert order.status_code == 200
    assignment = order.json()["assignment"]
    store = assignment["stores"][0]
    line = store["lines"][0]

    denied = client.post(
        f"/api/driver/order/stores/{store['store_id']}/complete",
        json={
            "quantities": {line["line_id"]: "8"},
            "operation_id": "operation-1",
            "base_revision": 0,
        },
    )
    assert denied.status_code == 403

    completed = client.post(
        f"/api/driver/order/stores/{store['store_id']}/complete",
        headers={"x-driver-csrf": csrf},
        json={
            "quantities": {line["line_id"]: "8"},
            "operation_id": "operation-1",
            "base_revision": 0,
        },
    )
    assert completed.status_code == 200
    assert completed.json()["assignment"]["completed_stores"] == 1
    assert completed.json()["assignment"]["summary"][0]["completed"] == 8


def test_driver_api_accepts_login_code_and_requires_csrf_for_logout(client, driver_api_fixture):
    driver, _ = driver_api_fixture
    login = client.post(
        "/api/driver/login",
        json={"login": driver["login"], "pin": "1234"},
    )
    assert login.status_code == 200
    csrf = login.json()["csrf_token"]

    denied = client.post("/api/driver/logout", json={})
    assert denied.status_code == 403

    logged_out = client.post(
        "/api/driver/logout",
        headers={"x-driver-csrf": csrf},
        json={},
    )
    assert logged_out.status_code == 200
    assert client.get("/api/driver/order").status_code == 401


def test_driver_api_invalidates_session_after_driver_deactivation(client, driver_api_fixture):
    driver, _ = driver_api_fixture
    login = client.post(
        "/api/driver/login",
        json={"driver_id": driver["id"], "pin": "1234"},
    )
    assert login.status_code == 200

    fleet.update_driver(
        driver["id"],
        driver["name"],
        driver.get("phone", ""),
        driver.get("rating", 5),
        False,
        driver.get("hired_on", ""),
        driver.get("notes", ""),
        driver.get("default_vehicle_id", ""),
    )

    response = client.get("/api/driver/order")
    assert response.status_code == 401


def test_driver_api_rejects_wrong_pin(client, driver_api_fixture):
    driver, _ = driver_api_fixture
    response = client.post(
        "/api/driver/login",
        json={"driver_id": driver["id"], "pin": "9999"},
    )
    assert response.status_code == 401


def test_driver_api_blocks_completion_and_sync_until_mileage_is_saved(client, driver_api_fixture):
    driver, snapshot = driver_api_fixture
    login = client.post("/api/driver/login", json={"driver_id": driver["id"], "pin": "1234"})
    csrf = login.json()["csrf_token"]
    store = snapshot["stores"][0]
    line = store["lines"][0]

    completion = client.post(
        f"/api/driver/order/stores/{store['store_id']}/complete",
        headers={"x-driver-csrf": csrf},
        json={
            "quantities": {line["line_id"]: "8"},
            "operation_id": "operation-1",
            "base_revision": 0,
        },
    )
    sync = client.post("/api/driver/sync", headers={"x-driver-csrf": csrf}, json={})

    assert completion.status_code == 409
    assert sync.status_code == 409
    assert completion.json()["mileage"]["required"] is True
    assert sync.json()["mileage"]["required"] is True


def test_driver_api_requires_an_explicit_assigned_vehicle(client, driver_api_fixture, monkeypatch):
    driver, snapshot = driver_api_fixture
    assignment_without_vehicle = {**snapshot, "vehicle_id": ""}
    monkeypatch.setattr(
        driver_orders,
        "find_assignment_for_driver",
        lambda driver_id: assignment_without_vehicle if driver_id == driver["id"] else None,
    )

    login = client.post("/api/driver/login", json={"driver_id": driver["id"], "pin": "1234"})
    order = client.get("/api/driver/order")

    assert login.status_code == 200
    assert login.json()["mileage"]["required"] is True
    assert login.json()["mileage"]["available"] is False
    assert order.status_code == 409
    assert "автомобиль" in order.json()["error"]


def test_driver_api_validates_mileage_against_active_assignment(client, driver_api_fixture):
    driver, _ = driver_api_fixture
    login = client.post("/api/driver/login", json={"driver_id": driver["id"], "pin": "1234"})
    mileage = login.json()["mileage"]
    csrf = login.json()["csrf_token"]
    payload = {
        "odometer_km": "12345",
        "vehicle_id": mileage["vehicle"]["id"],
        "date": mileage["date"],
        "assignment_id": mileage["assignment_id"],
    }

    denied = client.post("/api/driver/mileage", json=payload)
    forged_vehicle = client.post(
        "/api/driver/mileage",
        headers={"x-driver-csrf": csrf},
        json={**payload, "vehicle_id": "vehicle-2"},
    )
    forged_day = client.post(
        "/api/driver/mileage",
        headers={"x-driver-csrf": csrf},
        json={**payload, "date": "2000-01-01"},
    )

    assert denied.status_code == 403
    assert forged_vehicle.status_code == 409
    assert forged_day.status_code == 409


def test_driver_api_mileage_retries_are_idempotent_and_conflicts_are_preserved(client, driver_api_fixture):
    driver, _ = driver_api_fixture
    login = client.post("/api/driver/login", json={"driver_id": driver["id"], "pin": "1234"})

    first = submit_mileage(client, login, "12345")
    repeated = submit_mileage(client, login, "12345")
    conflicting = submit_mileage(client, login, "12346")

    assert first.status_code == 200
    assert first.json()["idempotent"] is False
    assert repeated.status_code == 200
    assert repeated.json()["idempotent"] is True
    assert conflicting.status_code == 409
    assert conflicting.json()["mileage"]["required"] is False
