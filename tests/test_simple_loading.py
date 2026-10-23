from copy import deepcopy
from datetime import datetime
from types import SimpleNamespace

import pytest
from openpyxl import Workbook

from modules import driver_orders, goods_returns, order_records as records, paths, vehicle_trips
from orders_dashboard import loading_page


LOADER = {"kind": "loader", "id": "loader-1", "name": "Склад"}
DRIVER = {"kind": "driver", "id": "driver-1", "name": "Водитель"}


@pytest.fixture
def simple_route(tmp_path, monkeypatch):
    output = tmp_path / "processed" / "20.10.26" / "result.xlsx"
    output.parent.mkdir(parents=True)
    workbook = Workbook()
    sheet = workbook.active
    sheet.title = "Маршрут №4"
    sheet.append(["Товар", "Сумма", "ФМ 10", "ФМ 47"])
    sheet.append(["Дыня", None, 8, 4])
    sheet.append(["Морковь", None, 2, 0])
    workbook.save(output)
    workbook.close()
    monkeypatch.setattr(paths, "PROCESSED_FOLDER", output.parent.parent)
    monkeypatch.setattr(paths, "ORDER_RECORDS_FILE", tmp_path / "orders.json")
    monkeypatch.setattr(paths, "DRIVER_ORDERS_FOLDER", tmp_path / "driver_orders")
    monkeypatch.setattr(paths, "GOODS_RETURNS_FILE", tmp_path / "returns.json")
    monkeypatch.setattr(paths, "VEHICLE_TRIPS_FILE", tmp_path / "trips.sqlite3")
    record = records.create_processed_order_record(output, "order.xlsx", "Клиент", "Город")
    assignment = {
        "route": "route_4", "label": "Маршрут №4", "driver_id": DRIVER["id"],
        "driver_name": DRIVER["name"], "vehicle_id": "vehicle-1", "vehicle_name": "Газель",
    }
    snapshot = driver_orders.load_snapshot(driver_orders.publish_assignments(
        output, "Город", "order.xlsx", [assignment], record
    )[0])
    record = records.set_route_loading_mode(record["id"], record["revision"], "route_4", "simple")
    return record, snapshot


def current(record):
    return records.load_order_record(record["id"])


def lines(record):
    return [line for line in current(record)["loading_lines"] if line["route_key"] == "route_4"]


def counted(record):
    for line, boxes in zip(lines(record), ("3", "0")):
        records.save_simple_box_count_draft(record["id"], "route_4", line["id"], boxes, LOADER)
    return records.confirm_simple_box_counts(record["id"], current(record)["revision"], "route_4", LOADER)


def weighted(record):
    for line, tare, gross in zip(lines(record), ("0.5", "0"), ("11.5", "0")):
        records.save_simple_weight_draft(record["id"], "route_4", line["id"], "tare_weight_per_box_kg", tare, LOADER)
        records.save_simple_weight_draft(record["id"], "route_4", line["id"], "gross_weight_kg", gross, LOADER)
        if line["name"] == "Морковь":
            records.save_simple_weight_draft(record["id"], "route_4", line["id"], "zero_reason", records.ZERO_REASON_OPTIONS[0], LOADER)
    return records.confirm_simple_weight(record["id"], current(record)["revision"], "route_4", LOADER)


def test_simple_mode_confirms_boxes_without_inventing_weight(simple_route, monkeypatch):
    record, snapshot = simple_route
    first, second = lines(record)
    assert records.route_loading_mode(current(record), "route_4") == "simple"
    with pytest.raises(records.OrderRecordConflict):
        records.save_simple_weight_draft(record["id"], "route_4", first["id"], "gross_weight_kg", "8", LOADER)
    with pytest.raises(records.OrderRecordConflict):
        records.confirm_simple_weight(record["id"], current(record)["revision"], "route_4", LOADER)
    with pytest.raises(records.OrderRecordError, match="доступ"):
        records.save_simple_box_count_draft(record["id"], "route_4", first["id"], "3", DRIVER)
    with pytest.raises(records.OrderRecordError, match="ящик"):
        records.confirm_simple_box_counts(record["id"], current(record)["revision"], "route_4", LOADER)
    records.save_simple_box_count_draft(record["id"], "route_4", first["id"], "3", LOADER)
    for invalid in ("1.5", "-1", "три"):
        with pytest.raises(records.OrderRecordError):
            records.save_simple_box_count_draft(record["id"], "route_4", second["id"], invalid, LOADER)
    counted(record)
    saved = current(record)
    assert saved["loading"]["route_states"]["route_4"]["status"] == "counted"
    assert [(line["confirmed_box_count"], line["measurement"]["net_weight_kg"]) for line in lines(record)] == [
        ("3", ""), ("0", ""),
    ]
    assert not records.route_loading_ready(saved, "route_4")
    assert records.logistics_summary(saved)["total_loaded_net_kg"] == "0"
    assert not goods_returns.return_context(snapshot)["loading_ready"]
    with pytest.raises(records.OrderRecordError, match="не подтвердил"):
        records.route_return_balance(saved, "route_4")
    destination = saved["routes"][0]["destinations"][0]
    position = destination["positions"][0]
    with pytest.raises(records.OrderRecordConflict):
        records.save_store_shipment(saved["id"], "route_4", destination["id"], {
            position["id"]: {"kind": "net", "net_weight_kg": "8"},
        }, "early-ship", DRIVER)
    monkeypatch.setattr(vehicle_trips, "_fleet_available", lambda assignment: True)
    trip = vehicle_trips.create_trip([snapshot["assignment_id"]], "2026-10-20", {"kind": "dashboard", "id": "admin"}, "trip-created")
    with pytest.raises((records.OrderRecordError, vehicle_trips.TripError)):
        vehicle_trips.start_trip(trip["id"], trip["revision"], {"kind": "dashboard", "id": "admin"}, "early-trip")
    assert vehicle_trips.load_trip(trip["id"])["status"] == "draft"
    assert current(record)["revision"] == saved["revision"]


def test_simple_mode_later_measured_weight_enables_normal_shipment(simple_route, monkeypatch):
    record, snapshot = simple_route
    counted(record)
    first, second = lines(record)
    with pytest.raises(records.OrderRecordConflict):
        records.save_simple_box_count_draft(record["id"], "route_4", first["id"], "4", LOADER)
    for line in (first, second):
        with pytest.raises(records.OrderRecordConflict):
            records.save_loading_draft(record["id"], "route_4", line["id"], "gross_weight_kg", "8", LOADER)
    with pytest.raises(records.OrderRecordError, match="Вес"):
        records.confirm_simple_weight(record["id"], current(record)["revision"], "route_4", LOADER)
    for field, value in (("tare_weight_per_box_kg", "0.5"), ("gross_weight_kg", "11.5")):
        records.save_simple_weight_draft(record["id"], "route_4", first["id"], field, value, LOADER)
    assert lines(record)[0]["confirmed_box_count"] == "3"
    with pytest.raises(records.OrderRecordConflict):
        records.save_simple_weight_draft(record["id"], "route_4", first["id"], "box_count", "5", LOADER)
    records.save_simple_weight_draft(record["id"], "route_4", second["id"], "tare_weight_per_box_kg", "0", LOADER)
    records.save_simple_weight_draft(record["id"], "route_4", second["id"], "gross_weight_kg", "0", LOADER)
    with pytest.raises(records.OrderRecordError, match="причину"):
        records.confirm_simple_weight(record["id"], current(record)["revision"], "route_4", LOADER)
    weighted(record)
    saved = current(record)
    assert records.route_loading_ready(saved, "route_4")
    assert records.logistics_summary(saved)["total_loaded_net_kg"] == "10"
    assert [(line["measurement"]["box_count"], line["confirmed_box_count"]) for line in lines(record)] == [("3", "3"), ("0", "0")]
    assert records.route_return_balance(saved, "route_4")["lines"]
    assert goods_returns.return_context(snapshot)["loading_ready"]
    with pytest.raises(records.OrderRecordConflict):
        records.save_simple_weight_draft(record["id"], "route_4", first["id"], "gross_weight_kg", "12", LOADER)
    monkeypatch.setattr(vehicle_trips, "_fleet_available", lambda assignment: True)
    trip = vehicle_trips.create_trip([snapshot["assignment_id"]], "2026-10-20", {"kind": "dashboard", "id": "admin"}, "trip-created-after-weight")
    started = vehicle_trips.start_trip(trip["id"], trip["revision"], {"kind": "dashboard", "id": "admin"}, "trip-after-weight")
    assert started["status"] == "active"
    assert started["products"][0]["loaded"] == "10"


def test_simple_mode_blocks_stale_replay_cross_route_and_mutation_after_count(simple_route):
    record, _ = simple_route
    first = lines(record)[0]
    before = deepcopy(current(record))
    with pytest.raises(records.OrderRecordNotFound):
        records.save_simple_box_count_draft(record["id"], "route_4", "foreign-line", "1", LOADER)
    assert current(record) == before
    records.save_simple_box_count_draft(record["id"], "route_4", first["id"], "3", LOADER)
    with pytest.raises(records.OrderRecordConflict):
        records.set_route_loading_mode(record["id"], current(record)["revision"], "route_4", "route")
    with pytest.raises(records.OrderRecordConflict):
        records.confirm_route_loading(record["id"], current(record)["revision"], "route_4", LOADER)
    counted(record)
    revision = current(record)["revision"]
    with pytest.raises(records.OrderRecordConflict):
        records.confirm_simple_box_counts(record["id"], revision, "route_4", LOADER)
    with pytest.raises(records.OrderRecordConflict):
        records.confirm_simple_box_counts(record["id"], revision - 1, "route_4", LOADER)
    assert current(record)["revision"] == revision


def test_simple_loading_page_preserves_box_counts_and_requires_separate_weight(simple_route):
    record, _ = simple_route
    state = SimpleNamespace(
        selected_order_id="", selected_route_key="", selected_store_id="", order_options=[],
        loading_sort="name_desc", principal=LOADER, back_target="/", status="",
    )
    state._apply_record = loading_page.LoadingState._apply_record.__get__(state)
    state._patch_loading_measurement = loading_page.LoadingState._patch_loading_measurement.__get__(state)
    state._refresh_options = loading_page.LoadingState._refresh_options.__get__(state)
    state._apply_record(record["id"], "route_4")
    assert state.loading_mode == "simple"
    assert not state.simple_boxes_confirmed and not state.route_is_ready
    assert state.total_loaded_net_kg == ""
    assert [row["name"] for row in loading_page._sort_loading_rows(state.loading_rows, state.loading_sort)] == ["Морковь", "Дыня"]
    for row, boxes in zip(state.loading_rows, ("3", "0")):
        loading_page.LoadingState.set_context_measurement_field.fn(
            state, record["id"], "route_4", "", row["id"], "box_count", boxes
        )
    assert state.simple_box_total == "3"
    state._apply_record(record["id"], "route_4")
    assert [row["box_count"] for row in state.loading_rows] == ["3", "0"]
    loading_page.LoadingState.confirm_simple_boxes.fn(state)
    assert state.simple_boxes_confirmed and not state.route_is_ready
    assert state.save_completed and state.simple_box_total == "3"
    assert "вес пока неизвестен" in state.status
    assert all(row["preview_net_weight_kg"] == "" for row in state.loading_rows)
    state._apply_record(record["id"], "route_4")
    assert state.simple_boxes_confirmed and not state.route_is_ready
    state.principal = {"kind": "dashboard", "id": "admin", "name": "Администратор"}

    for row, tare, gross in zip(state.loading_rows, ("0.5", "0"), ("11.5", "0")):
        for field, value in (("tare_weight_per_box_kg", tare), ("gross_weight_kg", gross)):
            loading_page.LoadingState.set_context_measurement_field.fn(
                state, record["id"], "route_4", "", row["id"], field, value
            )
        if row["name"] == "Морковь":
            loading_page.LoadingState.set_context_measurement_field.fn(
                state, record["id"], "route_4", "", row["id"], "zero_reason", records.ZERO_REASON_OPTIONS[0]
            )
    assert state.simple_box_total == "3"
    assert not state.route_is_ready
    loading_page.LoadingState.confirm_simple_route_weight.fn(state)
    assert state.route_is_ready and state.is_read_only
    assert [row["box_count"] for row in state.loading_rows] == ["3", "0"]
    assert records.logistics_summary(current(record))["total_loaded_net_kg"] == "10"


def test_simple_dispatcher_stage_waits_for_weighing(simple_route):
    record, _ = simple_route
    day = datetime.fromisoformat(record["processed_at"]).astimezone().date().isoformat()

    def trip():
        return next(item for item in records.list_route_trip_summaries(day, "Город")
                    if item["order_record_id"] == record["id"])

    assert trip()["stage"] == "Ожидает загрузки"
    counted(record)
    assert trip()["stage"] == "Ящики учтены, ожидается взвешивание"
    assert trip()["loaded_net_kg"] == "—"
    assert not trip()["loading_ready"]
    first = lines(record)[0]
    records.save_simple_weight_draft(record["id"], "route_4", first["id"], "tare_weight_per_box_kg", "0.5", LOADER)
    assert trip()["stage"] == "Ящики учтены, ожидается взвешивание"
    weighted(record)
    assert trip()["stage"] == "Готов к отгрузке"
    assert trip()["loaded_net_kg"] == "10"


def test_simple_mode_shipment_uses_measured_kg_and_leaves_real_return_balance(simple_route):
    record, _ = simple_route
    counted(record)
    weighted(record)
    saved = current(record)
    destination = saved["routes"][0]["destinations"][0]
    facts = {
        position["id"]: {"kind": "net", "net_weight_kg": "8" if position["name"] == "Дыня" else "0"}
        for position in destination["positions"]
    }
    records.save_store_shipment(saved["id"], "route_4", destination["id"], facts, "simple-ship-1", DRIVER)
    balance = records.route_return_balance(current(record), "route_4")
    melon = next(line for line in balance["lines"] if line["name"] == "Дыня")
    assert (melon["planned_kg"], melon["loaded_net_kg"], melon["shipped_net_kg"], melon["available_net_kg"]) == ("12", "10", "8", "2")
    assert records.logistics_summary(current(record))["total_loaded_net_kg"] == "10"
