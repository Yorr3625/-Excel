from decimal import Decimal
import json

import pytest
from openpyxl import Workbook

from modules import order_records, paths


@pytest.fixture
def processed_order(tmp_path, monkeypatch):
    processed_root = tmp_path / "processed_orders"
    output = processed_root / "05.10.26" / "заказ_обработан_10-00-00.xlsx"
    output.parent.mkdir(parents=True)
    workbook = Workbook()
    route_one = workbook.active
    route_one.title = "Маршрут №1"
    route_one.append(["Товар", "Сумма", "ФМ 10", "ФМ 14"])
    route_one.append(["Помидоры", "", 10, 4])
    route_one.append(["Огурцы", "", 2, None])
    route_one.append(["ИТОГО", "", None, None])
    route_two = workbook.create_sheet("Маршрут №2")
    route_two.append(["Товар", "Сумма", "ФМ 20"])
    route_two.append(["Помидоры", "", 6])
    workbook.save(output)
    monkeypatch.setattr(paths, "PROCESSED_FOLDER", processed_root)
    monkeypatch.setattr(paths, "ORDER_RECORDS_FILE", tmp_path / "order_records.json")
    return output


def create_record(output):
    return order_records.create_processed_order_record(
        output,
        "№42.xlsx",
        "ООО Ромашка",
        "Область",
        {"message_id": "mail-42", "received_at": "2026-10-05T09:00:00+03:00"},
    )


def measurement(boxes=1, tare="0", gross="0"):
    return {
        "box_count": str(boxes),
        "tare_weight_per_box_kg": str(tare),
        "gross_weight_kg": str(gross),
    }


def route_lines(record, route_key):
    return [line for line in record["loading_lines"] if line.get("route_key") == route_key]


def draft_route(record, route_key, gross_by_name):
    saved = record
    for line in route_lines(record, route_key):
        for field, value in measurement(0, 0, gross_by_name[line["name"]]).items():
            saved = order_records.save_loading_draft(
                saved["id"], route_key, line["id"], field, value, {"kind": "loader", "id": "loader-1"}
            )
    return saved


def confirm_route(record, route_key):
    return order_records.confirm_route_loading(
        record["id"], record["revision"], route_key, {"kind": "loader", "id": "loader-1", "name": "Иван"}
    )


def destination_measurements(destination, gross_by_name):
    return {
        position["id"]: measurement(0, 0, gross_by_name[position["name"]])
        for position in destination["positions"]
    }


def test_snapshot_creates_separate_loading_lines_per_route(processed_order):
    record = create_record(processed_order)

    assert [route["route_key"] for route in record["routes"]] == ["route_1", "route_2"]
    assert [
        (line["route_key"], line["name"], line["planned_amount"])
        for line in record["loading_lines"]
    ] == [
        ("route_1", "Огурцы", "2"),
        ("route_1", "Помидоры", "14"),
        ("route_2", "Помидоры", "6"),
    ]
    line_ids_by_route = {
        route_key: {line["id"] for line in route_lines(record, route_key)}
        for route_key in ("route_1", "route_2")
    }
    assert all(
        position["loading_line_id"] in line_ids_by_route[route["route_key"]]
        for route in record["routes"]
        for destination in route["destinations"]
        for position in destination["positions"]
    )
    assert [item["status"] for item in order_records.loading_route_summaries(record)] == ["new", "new"]


def test_route_draft_persists_after_reloading_record(processed_order):
    record = create_record(processed_order)
    line = route_lines(record, "route_1")[0]

    saved = order_records.save_loading_draft(
        record["id"], "route_1", line["id"], "box_count", "12", {"kind": "loader", "id": "loader-1"}
    )
    restored = order_records.load_order_record(record["id"])

    saved_line = next(item for item in saved["loading_lines"] if item["id"] == line["id"])
    restored_line = next(item for item in restored["loading_lines"] if item["id"] == line["id"])
    assert saved_line["measurement"]["box_count"] == "12"
    assert restored_line["measurement"]["box_count"] == "12"
    assert restored["loading"]["route_states"]["route_1"]["status"] == "draft"
    assert restored["loading"]["route_states"]["route_2"]["status"] == "new"
    assert restored["loading"]["status"] == "draft"


def test_confirming_one_route_keeps_other_route_editable_and_blocks_only_its_driver(processed_order):
    record = create_record(processed_order)
    drafted = draft_route(record, "route_1", {"Помидоры": "14", "Огурцы": "2"})
    confirmed = confirm_route(drafted, "route_1")

    assert order_records.route_loading_ready(confirmed, "route_1") is True
    assert order_records.route_loading_ready(confirmed, "route_2") is False
    assert confirmed["loading"]["status"] == "draft"
    assert confirmed["loading"]["route_states"]["route_2"]["status"] == "new"

    route_one = confirmed["routes"][0]
    destination = route_one["destinations"][0]
    shipped = order_records.save_store_shipment(
        confirmed["id"],
        "route_1",
        destination["id"],
        destination_measurements(destination, {"Помидоры": "10", "Огурцы": "2"}),
        "operation-1",
        {"kind": "driver"},
    )
    route_two = shipped["routes"][1]
    with pytest.raises(order_records.OrderRecordConflict, match="маршрута"):
        order_records.save_store_shipment(
            shipped["id"],
            "route_2",
            route_two["destinations"][0]["id"],
            destination_measurements(route_two["destinations"][0], {"Помидоры": "6"}),
            "operation-2",
            {"kind": "driver"},
        )


def test_confirm_route_rejects_incomplete_invalid_and_stale_data(processed_order):
    record = create_record(processed_order)
    line = route_lines(record, "route_1")[0]

    with pytest.raises(order_records.OrderRecordError, match="Некорректное"):
        order_records.save_loading_draft(record["id"], "route_1", line["id"], "unknown", "1", {})
    with pytest.raises(order_records.OrderRecordError, match="целым"):
        order_records.save_loading_draft(record["id"], "route_1", line["id"], "box_count", "1.5", {})
    with pytest.raises(order_records.OrderRecordError, match="Некорректное"):
        order_records.confirm_route_loading(record["id"], 0, "route_1", {})

    drafted = draft_route(record, "route_1", {"Помидоры": "14", "Огурцы": "2"})
    confirmed = confirm_route(drafted, "route_1")
    with pytest.raises(order_records.OrderRecordConflict):
        order_records.confirm_route_loading(confirmed["id"], drafted["revision"], "route_1", {})


def test_final_summary_aggregates_route_lines_by_product(processed_order):
    record = create_record(processed_order)
    route_one = confirm_route(draft_route(record, "route_1", {"Помидоры": "14", "Огурцы": "2"}), "route_1")
    route_two = confirm_route(draft_route(route_one, "route_2", {"Помидоры": "6"}), "route_2")

    summary = order_records.logistics_summary(route_two)
    rows = {row["name"]: row for row in summary["items"]}

    assert route_two["loading"]["status"] == "loaded"
    assert summary["total_loaded_net_kg"] == "22"
    assert rows["Помидоры"]["planned_kg"] == "20"
    assert rows["Помидоры"]["loaded_net_kg"] == "20"
    assert rows["Огурцы"]["loaded_net_kg"] == "2"


def test_zero_position_requires_reason_and_clears_it_after_nonzero_value(processed_order):
    record = create_record(processed_order)
    line = route_lines(record, "route_2")[0]
    saved = record
    for field in ("box_count", "tare_weight_per_box_kg", "gross_weight_kg"):
        saved = order_records.save_loading_draft(
            saved["id"], "route_2", line["id"], field, "0", {"kind": "loader"}
        )

    with pytest.raises(order_records.OrderRecordError, match="причину нулевой позиции"):
        confirm_route(saved, "route_2")
    with pytest.raises(order_records.OrderRecordError, match="Некорректная причина"):
        order_records.save_loading_draft(
            saved["id"], "route_2", line["id"], "zero_reason", "Другое", {}
        )

    saved = order_records.save_loading_draft(
        saved["id"],
        "route_2",
        line["id"],
        "zero_reason",
        order_records.ZERO_REASON_OPTIONS[0],
        {"kind": "loader"},
    )
    confirmed = confirm_route(saved, "route_2")
    confirmed_line = route_lines(confirmed, "route_2")[0]
    assert confirmed_line["measurement"]["zero_reason"] == order_records.ZERO_REASON_OPTIONS[0]

    record = create_record(processed_order)
    line = route_lines(record, "route_2")[0]
    saved = record
    for field in ("box_count", "tare_weight_per_box_kg", "gross_weight_kg"):
        saved = order_records.save_loading_draft(saved["id"], "route_2", line["id"], field, "0", {})
    saved = order_records.save_loading_draft(
        saved["id"], "route_2", line["id"], "zero_reason", order_records.ZERO_REASON_OPTIONS[1], {}
    )
    saved = order_records.save_loading_draft(saved["id"], "route_2", line["id"], "gross_weight_kg", "1", {})
    assert route_lines(saved, "route_2")[0]["measurement"]["zero_reason"] == ""


def test_legacy_record_keeps_boxes_without_inventing_route_split(tmp_path, monkeypatch):
    store = tmp_path / "order_records.json"
    monkeypatch.setattr(paths, "ORDER_RECORDS_FILE", store)
    store.write_text(
        json.dumps({
            "schema_version": 1,
            "records": [{
                "id": "legacy",
                "loading": {"status": "loaded"},
                "routes": [],
                "loading_lines": [{
                    "id": "line-1",
                    "name": "Помидоры",
                    "unit": "box",
                    "planned_amount": "20",
                    "loading_amount": "5",
                }],
            }],
        }),
        encoding="utf-8",
    )

    record = order_records.load_order_record("legacy")

    assert "route_key" not in record["loading_lines"][0]
    assert record["loading_lines"][0]["measurement"]["box_count"] == "5"
    assert record["loading"]["status"] == "loaded"


def test_calculate_net_weight_is_pure():
    assert order_records.calculate_net_weight("30", "0.5", 10) == Decimal("25")
