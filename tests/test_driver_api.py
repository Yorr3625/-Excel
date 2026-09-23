from pathlib import Path

import pytest
from openpyxl import Workbook
from starlette.testclient import TestClient

from modules import driver_orders, fleet, paths
from orders_dashboard.orders_dashboard import custom_api


@pytest.fixture
def driver_api_fixture(tmp_path, monkeypatch):
    config_dir = tmp_path / "config"
    data_dir = tmp_path / "data"
    fleet_file = config_dir / "fleet.json"
    assignments_file = data_dir / "order_route_assignments.json"
    driver_orders_dir = data_dir / "driver_orders"
    monkeypatch.setattr(paths, "DATA_DIR", data_dir)
    monkeypatch.setattr(paths, "DRIVER_ORDERS_FOLDER", driver_orders_dir)
    monkeypatch.setattr(paths, "FLEET_FILE", fleet_file)
    monkeypatch.setattr(paths, "ORDER_ROUTE_ASSIGNMENTS_FILE", assignments_file)
    monkeypatch.setattr(fleet, "FLEET_FILE", fleet_file)
    monkeypatch.setattr(fleet, "ORDER_ROUTE_ASSIGNMENTS_FILE", assignments_file)

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
