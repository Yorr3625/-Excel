from copy import deepcopy
from types import SimpleNamespace

import pytest
from openpyxl import Workbook
from starlette.testclient import TestClient

from modules import dashboard_sessions, driver_mileage, driver_orders, fleet, goods_returns, order_records, paths
from orders_dashboard import loading_page
import orders_dashboard.orders_dashboard as dashboard


@pytest.fixture
def trip(tmp_path, monkeypatch):
    for name, value in {
        "PROCESSED_FOLDER": tmp_path,
        "ORDER_RECORDS_FILE": tmp_path / "orders.json",
        "GOODS_RETURNS_FILE": tmp_path / "returns.json",
        "DRIVER_ORDERS_FOLDER": tmp_path / "drivers",
        "DRIVER_ORDERS_INDEX_FILE": tmp_path / "drivers" / "index.json",
        "FLEET_FILE": tmp_path / "fleet.json",
        "DRIVER_MILEAGE_FILE": tmp_path / "mileage.json",
    }.items():
        monkeypatch.setattr(paths, name, value)
    monkeypatch.setattr(fleet, "FLEET_FILE", paths.FLEET_FILE)
    monkeypatch.setattr(driver_mileage, "MILEAGE_FILE", paths.DRIVER_MILEAGE_FILE)
    driver = fleet.add_driver("Тестовый водитель")
    fleet.set_driver_pin(driver["id"], "1234")
    output = tmp_path / "07.10.26" / "order.xlsx"
    output.parent.mkdir()
    book = Workbook()
    book.active.title = "Маршрут №1"
    book.active.append(["Товар", "Сумма", "ФМ 10"])
    book.active.append(["Яблоки", "", 100])
    book.save(output)
    record = order_records.create_processed_order_record(output, "№42.xlsx", "Тест", "Город", {})
    line_id = record["loading_lines"][0]["id"]
    for field, value in {"box_count": "0", "tare_weight_per_box_kg": "0", "gross_weight_kg": "95"}.items():
        record = order_records.save_loading_draft(record["id"], "route_1", line_id, field, value, {})
    record = order_records.confirm_route_loading(record["id"], record["revision"], "route_1", {})
    snapshot = driver_orders.build_assignment_snapshot(output, "Город", {
        "route": "route_1", "label": "Маршрут №1", "driver_id": driver["id"],
        "driver_name": driver["name"], "vehicle_id": "vehicle-1", "vehicle_plate": "ТЕСТ",
        "order_file": "№42.xlsx",
    }, order_record=record)
    driver_orders.save_snapshot(snapshot)
    client = TestClient(dashboard.custom_api)
    login = client.post("/api/driver/login", json={"driver_id": driver["id"], "pin": "1234"}).json()
    headers = {"x-driver-csrf": login["csrf_token"]}
    status = login["mileage"]
    response = client.post("/api/driver/mileage", headers=headers, json={
        "vehicle_id": "vehicle-1", "date": status["date"],
        "assignment_id": snapshot["assignment_id"], "odometer_km": "1000",
    })
    assert response.status_code == 200
    store = snapshot["stores"][0]
    response = client.post(f"/api/driver/order/stores/{store['store_id']}/complete", headers=headers, json={
        "assignment_id": snapshot["assignment_id"], "base_revision": 0, "operation_id": "ship-1",
        "measurements": {store["lines"][0]["line_id"]: {
            "box_count": "0", "tare_weight_per_box_kg": "0", "gross_weight_kg": "90",
        }},
    })
    assert response.status_code == 200
    url = f"/api/driver/returns/{snapshot['assignment_id']}"
    context = client.get(url).json()["context"]
    payload = {
        "operation_id": "return-1", "base_revision": 0, "facts_token": context["facts_token"],
        "lines": {line_id: {"box_count": "1", "tare_weight_per_box_kg": "0.5", "gross_weight_kg": "5.5",
                            "reason": goods_returns.RETURN_REASONS[0], "comment": ""}},
    }
    yield SimpleNamespace(client=client, headers=headers, driver=driver, snapshot=snapshot,
                          record=record, line_id=line_id, url=url, context=context, payload=payload)
    client.close()


def test_return_roundtrip_and_idempotent_replay_do_not_change_shortage(trip):
    before = order_records.load_order_record(trip.record["id"])
    response = trip.client.post(trip.url, headers=trip.headers, json=trip.payload)
    assert response.status_code == 200
    document = response.json()["document"]
    goods_returns.decide_return(document["id"], document["revision"], "accepted", "Принято", {
        "kind": "dashboard", "id": "admin", "name": "Администратор",
    })
    repeated = trip.client.post(trip.url, headers=trip.headers, json=trip.payload)
    assert repeated.status_code == 200
    assert repeated.json() == response.json()
    assert trip.client.get(trip.url).json()["context"]["document"]["status"] == "accepted"
    assert order_records.load_order_record(trip.record["id"]) == before
    summary = loading_page._return_reconciliation(before)
    assert summary["total_shortage_kg"] == "10"
    assert summary["total_returned_kg"] == "5"
    assert summary["total_unexplained_kg"] == "0"


def test_return_api_auth_csrf_and_foreign_assignment(trip):
    anonymous = TestClient(dashboard.custom_api)
    assert anonymous.get(trip.url).status_code == 401
    assert anonymous.post(trip.url, json=trip.payload).status_code == 401
    assert trip.client.post(trip.url, json=trip.payload).status_code == 403
    other = deepcopy(trip.snapshot)
    other["assignment_id"] = "f" * 32
    other["driver_id"] = "another-driver"
    driver_orders.save_snapshot(other)
    url = f"/api/driver/returns/{other['assignment_id']}"
    assert trip.client.get(url).status_code == 404
    assert trip.client.post(url, headers=trip.headers, json=trip.payload).status_code == 404
    assignments = trip.client.get("/api/driver/returns").json()["assignments"]
    assert all(item["assignment_id"] != other["assignment_id"] for item in assignments)
    assert all("output_file" not in item for item in assignments)
    anonymous.close()


def test_return_limit_is_loaded_not_ordered_and_history_is_preserved(trip):
    excessive = deepcopy(trip.payload)
    excessive["lines"][trip.line_id]["gross_weight_kg"] = "10.5"
    assert trip.client.post(trip.url, headers=trip.headers, json=excessive).status_code in (400, 409)
    first = trip.client.post(trip.url, headers=trip.headers, json=trip.payload).json()["document"]
    rejected = goods_returns.decide_return(first["id"], first["revision"], "rejected", "Проверьте вес", {
        "kind": "dashboard", "id": "admin", "name": "Администратор",
    })
    new_payload = deepcopy(trip.payload)
    new_payload.update(operation_id="return-2", base_revision=rejected["revision"])
    response = trip.client.post(trip.url, headers=trip.headers, json=new_payload)
    assert response.status_code == 200
    current = response.json()["document"]
    assert current["id"] == first["id"]
    assert current["version"] == 2
    assert [event["kind"] for event in current["history"]] == ["submitted", "rejected", "submitted"]
    assert goods_returns.accepted_by_loading_line(trip.record["id"]) == {}


def test_historical_return_not_retargeted_or_blocked_by_new_mileage(trip):
    newer = deepcopy(trip.snapshot)
    newer.update(assignment_id="e" * 32, created_at="2099-01-01T00:00:00+00:00", vehicle_id="vehicle-2")
    driver_orders.save_snapshot(newer)
    assert trip.client.get("/api/driver/order").status_code == 409
    response = trip.client.post(trip.url, headers=trip.headers, json=trip.payload)
    assert response.status_code == 200
    assert response.json()["document"]["assignment_id"] == trip.snapshot["assignment_id"]


def test_dashboard_decision_checks_session_and_revision(trip):
    doc = trip.client.post(trip.url, headers=trip.headers, json=trip.payload).json()["document"]
    state = SimpleNamespace(router={}, returns_decision_id=doc["id"], returns_decision_revision=doc["revision"],
                            returns_decision_kind="accepted", returns_decision_comment="", returns_message="", returns_items=[])
    state.cancel_return_decision = dashboard.State.cancel_return_decision.fn.__get__(state)
    state.load_returns_report = dashboard.State.load_returns_report.fn.__get__(state)
    assert dashboard.State.confirm_return_decision.fn(state) is not None
    assert goods_returns.list_returns()[0]["status"] == "submitted"
    token = dashboard_sessions.create_session()
    state.router = {"headers": {"cookie": f"dashboard_session={token}"}}
    dashboard.State.confirm_return_decision.fn(state)
    assert state.returns_decision_id == ""
    assert state.returns_items[0]["status"] == "accepted"
    assert dashboard.PAGE_GROUPS["Возвраты"] == "Возвраты"
    dashboard_sessions.destroy_session(token)


@pytest.mark.parametrize("changes", [{"active": False}, {"role": "loader"}])
def test_return_api_revokes_disabled_or_changed_role(trip, monkeypatch, changes):
    monkeypatch.setattr(dashboard, "driver_by_id", lambda identity: {**trip.driver, **changes})
    assert trip.client.get(trip.url).status_code == 401
    assert trip.client.post(trip.url, headers=trip.headers, json=trip.payload).status_code == 401


def test_reconciliation_does_not_cancel_opposite_route_discrepancies(trip):
    record = order_records.load_order_record(trip.record["id"])
    other_line = deepcopy(record["loading_lines"][0])
    other_line.update(id="other-line", route_key="route_2", planned_amount="5")
    other_line["measurement"].update(gross_weight_kg="5", net_weight_kg="5")
    record["loading_lines"].append(other_line)
    other_route = deepcopy(record["routes"][0])
    other_route.update(route_key="route_2", route_label="Маршрут №2")
    for destination in other_route["destinations"]:
        destination["id"] += "-other"
        for position in destination["positions"]:
            position["id"] += "-other"
            position["loading_line_id"] = "other-line"
            position["shipment"]["measurement"].update(gross_weight_kg="10", net_weight_kg="10")
    record["routes"].append(other_route)
    record["loading"]["route_states"]["route_2"] = {"status": "loaded"}
    summary = loading_page._return_reconciliation(record)
    assert summary["total_loading_to_shipment_kg"] == "0"
    assert summary["total_unexplained_kg"] == "5"
    assert summary["total_excess_kg"] == "5"
