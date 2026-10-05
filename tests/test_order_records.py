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


def test_create_processed_order_record_snapshots_routes_and_ordered_kilograms(processed_order):
    record = create_record(processed_order)

    assert record["schema_version"] == 1
    assert len(record["id"]) == 32
    assert record["order_number"] == "№42"
    assert record["client_name"] == "ООО Ромашка"
    assert record["mode"] == "Область"
    assert record["output_relative_path"] == "05.10.26/заказ_обработан_10-00-00.xlsx"
    assert [route["route_key"] for route in record["routes"]] == ["route_1", "route_2"]
    assert record["routes"][0]["area"] == "Текстильщик"
    assert [item["name"] for item in record["routes"][0]["destinations"]] == ["ФМ 10", "ФМ 14"]
    assert [(line["name"], line["planned_amount"], line["unit"]) for line in record["loading_lines"]] == [
        ("Огурцы", "2", "kg"),
        ("Помидоры", "20", "kg"),
    ]
    assert all(line["loaded_box_count"] == "" for line in record["loading_lines"])
    assert record["loading"]["status"] == "new"
    assert order_records.list_order_record_summaries()[0]["id"] == record["id"]


def test_reprocessing_creates_a_new_record_without_replacing_previous(processed_order):
    first = create_record(processed_order)
    second = create_record(processed_order)

    assert first["id"] != second["id"]
    assert len(order_records.list_order_record_summaries()) == 2
    assert order_records.latest_record_ids_by_source_filename() == {"№42.xlsx": second["id"]}


def test_save_loading_update_records_box_counts_without_kg_comparison(processed_order):
    record = create_record(processed_order)
    box_counts = {line["id"]: 1 for line in record["loading_lines"]}

    saved = order_records.save_loading_update(
        record["id"], 0, box_counts, {"kind": "loader", "id": "loader-1", "name": "Иван"}
    )

    assert saved["revision"] == 1
    assert saved["loading"]["status"] == "loaded"
    assert {line["loaded_box_count"] for line in saved["loading_lines"]} == {"1"}
    assert all("loading_amount" not in line for line in saved["loading_lines"])
    assert saved["loading"]["last_saved_by"] == {
        "kind": "loader", "id": "loader-1", "name": "Иван"
    }


def test_loading_update_requires_every_nonnegative_integer_box(processed_order):
    record = create_record(processed_order)
    line_id = record["loading_lines"][0]["id"]

    with pytest.raises(order_records.OrderRecordError, match="каждой позиции"):
        order_records.save_loading_update(record["id"], 0, {}, {})
    with pytest.raises(order_records.OrderRecordError, match="целым"):
        order_records.save_loading_update(
            record["id"], 0, {line["id"]: "1.5" for line in record["loading_lines"]}, {}
        )
    with pytest.raises(order_records.OrderRecordError, match="отрицательным"):
        order_records.save_loading_update(
            record["id"], 0, {line["id"]: -1 for line in record["loading_lines"]}, {}
        )

    assert order_records.load_order_record(record["id"])["revision"] == 0
    assert line_id


def test_loading_update_rejects_stale_revision(processed_order):
    record = create_record(processed_order)
    amounts = {line["id"]: 0 for line in record["loading_lines"]}
    order_records.save_loading_update(record["id"], 0, amounts, {})

    with pytest.raises(order_records.OrderRecordConflict):
        order_records.save_loading_update(record["id"], 0, amounts, {})


def test_legacy_record_normalizes_boxes_to_kg_and_preserves_box_count(tmp_path, monkeypatch):
    store = tmp_path / "order_records.json"
    monkeypatch.setattr(paths, "ORDER_RECORDS_FILE", store)
    store.write_text(
        json.dumps({
            "schema_version": 1,
            "records": [{
                "id": "legacy",
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

    assert record["loading_lines"] == [{
        "id": "line-1",
        "name": "Помидоры",
        "unit": "kg",
        "planned_amount": "20",
        "loaded_box_count": "5",
    }]


def test_missing_store_is_empty_and_calculate_net_weight_is_pure(tmp_path, monkeypatch):
    monkeypatch.setattr(paths, "ORDER_RECORDS_FILE", tmp_path / "order_records.json")

    assert order_records.list_order_record_summaries() == []
    assert not paths.ORDER_RECORDS_FILE.exists()
    assert order_records.calculate_net_weight("30", "0.5", 10) == Decimal("25")


def test_record_rejects_missing_client_and_output_outside_processed_folder(processed_order, tmp_path):
    with pytest.raises(order_records.OrderRecordError, match="клиента"):
        order_records.create_processed_order_record(processed_order, "№42.xlsx", "", "Город")

    outside = tmp_path / "outside.xlsx"
    outside.write_bytes(b"xlsx")
    with pytest.raises(order_records.OrderRecordError, match="вне каталога"):
        order_records.create_processed_order_record(outside, "№42.xlsx", "Клиент", "Город")
