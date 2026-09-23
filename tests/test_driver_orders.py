from pathlib import Path

import pytest
from openpyxl import Workbook

from modules import driver_orders, paths


@pytest.fixture
def order_fixture(tmp_path, monkeypatch):
    output = tmp_path / "processed.xlsx"
    workbook = Workbook()
    sheet = workbook.active
    sheet.title = "Маршрут №1"
    sheet.append(["Товар", "Сумма", "фм 10", "фм 14"])
    sheet.append(["Яблоки", "=SUM(C2:D2)", 10, 4])
    sheet.append(["Бананы", "=SUM(C3:D3)", 2.5, 0])
    sheet.append(["ИТОГО", "=SUM(B2:B3)", None, None])
    workbook.save(output)
    monkeypatch.setattr(paths, "DRIVER_ORDERS_FOLDER", tmp_path / "driver_orders")
    return output


def assignment():
    return {
        "route": "route_1",
        "label": "Маршрут №1",
        "driver_id": "driver-1",
        "driver_name": "Иван",
        "vehicle_id": "vehicle-1",
        "vehicle_name": "Газель",
        "vehicle_plate": "А123ВС71",
    }


def test_build_snapshot_reads_route_sheet_without_changing_workbook(order_fixture):
    snapshot = driver_orders.build_assignment_snapshot(order_fixture, "Город", assignment())

    assert snapshot["route_key"] == "route_1"
    assert [store["name"] for store in snapshot["stores"]] == ["фм 10", "фм 14"]
    assert [line["required_qty"] for line in snapshot["stores"][0]["lines"]] == ["10", "2.5"]
    assert [line["required_qty"] for line in snapshot["stores"][1]["lines"]] == ["4", "0"]
    assert snapshot["revision"] == 0

def test_build_snapshot_keeps_only_positions_present_for_each_store(tmp_path):
    output = tmp_path / "processed.xlsx"
    workbook = Workbook()
    sheet = workbook.active
    sheet.title = "Маршрут №1"
    sheet.append(["Товар", "Сумма", "фм 10", "фм 14", "фм 20"])
    sheet.append(["Яблоки", "", 10, None, None])
    sheet.append(["Бананы", "", None, 2.5, None])
    workbook.save(output)

    snapshot = driver_orders.build_assignment_snapshot(output, "Город", assignment())

    assert [store["name"] for store in snapshot["stores"]] == ["фм 10", "фм 14"]
    assert [line["name"] for line in snapshot["stores"][0]["lines"]] == ["Яблоки"]
    assert [line["name"] for line in snapshot["stores"][1]["lines"]] == ["Бананы"]


def test_completion_updates_summary_and_is_idempotent(order_fixture):
    snapshot = driver_orders.build_assignment_snapshot(order_fixture, "Город", assignment())
    path = driver_orders.save_snapshot(snapshot)
    store = snapshot["stores"][0]
    quantities = {line["line_id"]: value for line, value in zip(store["lines"], [8, 2])}

    result = driver_orders.complete_store(
        path,
        store["store_id"],
        quantities,
        "operation-1",
        0,
    )

    assert result["revision"] == 1
    assert result["completed_stores"] == 1
    summary = {item["name"]: item for item in result["summary"]}
    assert summary["Яблоки"]["completed"] == 8
    assert summary["Яблоки"]["necessary"] == 4
    assert summary["Бананы"]["completed"] == 2
    assert summary["Бананы"]["necessary"] == 0

    repeated = driver_orders.complete_store(
        path,
        store["store_id"],
        {line["line_id"]: 999 for line in store["lines"]},
        "operation-1",
        0,
    )
    assert repeated["revision"] == 1
    assert repeated["summary"] == result["summary"]


def test_completion_rejects_stale_revision_and_missing_lines(order_fixture):
    snapshot = driver_orders.build_assignment_snapshot(order_fixture, "Город", assignment())
    path = driver_orders.save_snapshot(snapshot)
    store = snapshot["stores"][0]
    quantities = {line["line_id"]: 1 for line in store["lines"]}

    driver_orders.complete_store(path, store["store_id"], quantities, "operation-1", 0)

    with pytest.raises(driver_orders.DriverOrderConflict):
        driver_orders.complete_store(path, store["store_id"], quantities, "operation-2", 0)

    with pytest.raises(driver_orders.DriverOrderError, match="каждой строке"):
        driver_orders.complete_store(path, snapshot["stores"][1]["store_id"], {}, "operation-3", 1)


def test_find_assignment_for_driver_returns_published_snapshot(order_fixture):
    snapshot = driver_orders.build_assignment_snapshot(order_fixture, "Город", assignment())
    driver_orders.save_snapshot(snapshot)

    found = driver_orders.find_assignment_for_driver("driver-1")

    assert found["assignment_id"] == snapshot["assignment_id"]
    assert driver_orders.find_assignment_for_driver("other") is None


def test_quantity_validation_rejects_negative_values(order_fixture):
    snapshot = driver_orders.build_assignment_snapshot(order_fixture, "Город", assignment())
    path = driver_orders.save_snapshot(snapshot)
    store = snapshot["stores"][0]
    quantities = {line["line_id"]: -1 for line in store["lines"]}

    with pytest.raises(driver_orders.DriverOrderError, match="отрицательным"):
        driver_orders.complete_store(path, store["store_id"], quantities, "operation-1", 0)

    assert Path(path).exists()
