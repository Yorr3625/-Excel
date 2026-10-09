from decimal import Decimal
import json
from types import SimpleNamespace

import pytest
from openpyxl import Workbook

from modules import goods_returns, order_records as records, paths
import orders_dashboard.loading_page as page

ACTOR = {"kind": "loader", "id": "loader-test", "name": "Склад"}


@pytest.fixture
def record(tmp_path, monkeypatch):
    output = tmp_path / "processed_orders" / "09.10.26" / "заказ.xlsx"
    output.parent.mkdir(parents=True)
    book = Workbook()
    sheet = book.active
    sheet.title = "Маршрут №4"
    sheet.append(["Товар", "Сумма", "Магазин А", "Магазин Б"])
    sheet.append(["Помидоры", "", 8, 4])
    other = book.create_sheet("Маршрут №5")
    other.append(["Товар", "Сумма", "Магазин В"])
    other.append(["Помидоры", "", 2])
    book.save(output)
    monkeypatch.setattr(paths, "PROCESSED_FOLDER", tmp_path / "processed_orders")
    monkeypatch.setattr(paths, "ORDER_RECORDS_FILE", tmp_path / "order_records.json")
    monkeypatch.setattr(paths, "GOODS_RETURNS_FILE", tmp_path / "goods_returns.json")
    return records.create_processed_order_record(output, "№42.xlsx", "Тест", "Область")


def destinations(record):
    return record["routes"][0]["destinations"]


def choose(record):
    return records.set_route_loading_mode(record["id"], record["revision"], "route_4", "stores")


def fill(record, destination, boxes="1", tare="0.1", gross="9.1"):
    for field, value in {"box_count": boxes, "tare_weight_per_box_kg": tare, "gross_weight_kg": gross}.items():
        record = records.save_store_loading_draft(record["id"], "route_4", destination["id"], destination["positions"][0]["id"], field, value, ACTOR)
    return record


def confirm(record, destination):
    return records.confirm_store_loading(record["id"], record["revision"], "route_4", destination["id"], ACTOR)


def ready(record):
    record = choose(record)
    first, second = destinations(record)
    record = confirm(fill(record, second, "2", "0.25", "3.5"), second)
    return confirm(fill(record, first), first)


def test_arbitrary_store_order_and_exact_aggregate_preserve_ids(record):
    ids = [position["loading_line_id"] for route in record["routes"] for dest in route["destinations"] for position in dest["positions"]]
    record = choose(record)
    first, second = destinations(record)
    record = confirm(fill(record, second, "2", "0.25", "3.5"), second)
    assert not records.route_loading_ready(record, "route_4")
    assert record["loading"]["route_states"]["route_4"]["status"] == "draft"
    assert records.logistics_summary(record)["total_loaded_net_kg"] == "0"
    assert records.loading_mode_locked(record, "route_4")
    record = confirm(fill(record, first), first)
    assert records.route_loading_ready(record, "route_4")
    assert not records.route_loading_ready(record, "route_5")
    assert record["loading"]["status"] == "draft"
    line = record["loading_lines"][0]
    assert records.loading_line_net_weight(record, line) == Decimal("12")
    assert records.logistics_summary(record)["total_loaded_net_kg"] == "12"
    balance = records.route_return_balance(record, "route_4")
    assert balance["lines"][0]["loaded_net_kg"] == "12"
    assert not balance["complete"]
    assert ids == [position["loading_line_id"] for route in record["routes"] for dest in route["destinations"] for position in dest["positions"]]
    assert all(not line["measurement"]["net_weight_kg"] for line in record["loading_lines"])
    trips = records.list_route_trip_summaries(record["processed_at"][:10], "Область")
    assert next(trip for trip in trips if trip["route_key"] == "route_4")["loaded_net_kg"] == "12"


def test_modes_cannot_mix_or_change_after_input(record):
    record = choose(record)
    line = record["loading_lines"][0]
    with pytest.raises(records.OrderRecordConflict):
        records.save_loading_draft(record["id"], "route_4", line["id"], "box_count", "1", ACTOR)
    with pytest.raises(records.OrderRecordConflict):
        records.confirm_route_loading(record["id"], record["revision"], "route_4", ACTOR)
    record = fill(record, destinations(record)[0])
    with pytest.raises(records.OrderRecordConflict):
        records.set_route_loading_mode(record["id"], record["revision"], "route_4", "route")
    assert records.route_loading_mode(records.load_order_record(record["id"]), "route_4") == "stores"


def test_started_general_loading_is_preserved(record):
    line = record["loading_lines"][0]
    record = records.save_loading_draft(record["id"], "route_4", line["id"], "box_count", "1", ACTOR)
    with pytest.raises(records.OrderRecordConflict):
        choose(record)
    assert records.route_loading_mode(records.load_order_record(record["id"]), "route_4") == "route"


def test_mode_switch_before_input_and_stale_revision(record):
    selected = choose(record)
    assert not records.loading_mode_locked(selected, "route_4")
    with pytest.raises(records.OrderRecordConflict):
        records.set_route_loading_mode(record["id"], record["revision"], "route_4", "route")
    switched = records.set_route_loading_mode(selected["id"], selected["revision"], "route_4", "route")
    assert records.route_loading_mode(switched, "route_4") == "route"


def test_confirmed_store_is_immutable_and_remaining_store_editable(record):
    record = choose(record)
    first, second = destinations(record)
    record = confirm(fill(record, first), first)
    with pytest.raises(records.OrderRecordConflict):
        confirm(record, first)
    with pytest.raises(records.OrderRecordConflict):
        fill(record, first)
    assert not records.route_loading_ready(fill(record, second), "route_4")


def test_invalid_store_position_and_cross_route_are_atomic(record):
    record = choose(record)
    dest = destinations(record)[0]
    before = paths.ORDER_RECORDS_FILE.read_bytes()
    for route_key, destination_id, position_id in [
        ("route_4", "missing", dest["positions"][0]["id"]),
        ("route_4", dest["id"], "missing"),
        ("route_5", dest["id"], dest["positions"][0]["id"]),
    ]:
        with pytest.raises(records.OrderRecordError):
            records.save_store_loading_draft(record["id"], route_key, destination_id, position_id, "box_count", "1", ACTOR)
        assert paths.ORDER_RECORDS_FILE.read_bytes() == before


def test_zero_reason_and_stale_confirmation(record):
    record = choose(record)
    dest = destinations(record)[0]
    record = fill(record, dest, "0", "0", "0")
    with pytest.raises(records.OrderRecordError):
        confirm(record, dest)
    stale = record["revision"]
    record = records.save_store_loading_draft(record["id"], "route_4", dest["id"], dest["positions"][0]["id"], "zero_reason", records.ZERO_REASON_OPTIONS[0], ACTOR)
    with pytest.raises(records.OrderRecordConflict):
        records.confirm_store_loading(record["id"], stale, "route_4", dest["id"], ACTOR)
    assert (destinations(confirm(record, dest))[0]["loading"])["status"] == "loaded"


def test_return_capacity_and_shortage_keep_original_semantics(record):
    record = ready(record)
    for dest, gross in zip(destinations(record), ("8", "2")):
        record = records.save_store_shipment(record["id"], "route_4", dest["id"], {dest["positions"][0]["id"]: {
            "box_count": "0", "tare_weight_per_box_kg": "0", "gross_weight_kg": gross,
        }}, "shipment-" + dest["id"], {"kind": "driver", "id": "driver-test"})
    balance = records.route_return_balance(record, "route_4")
    assert balance["complete"]
    assert balance["lines"][0]["available_net_kg"] == "2"
    route = record["routes"][0]
    assignment = {
        "assignment_id": "store-loading-trip", "driver_id": "driver-test",
        "order_record_id": record["id"], "route_key": "route_4", "route_label": route["route_label"],
        "stores": [{
            "store_id": "store-" + dest["id"], "name": dest["name"],
            "order_record_destination_id": dest["id"], "status": "completed",
            "lines": [{
                "line_id": "line-" + pos["id"], "name": pos["name"],
                "order_record_position_id": pos["id"], "loading_line_id": pos["loading_line_id"],
                "actual_qty": pos["shipment"]["measurement"]["net_weight_kg"],
            } for pos in dest["positions"]],
        } for dest in route["destinations"]],
    }
    context = goods_returns.return_context(assignment)
    assert context["eligible"] and context["complete"]
    line_id = balance["lines"][0]["loading_line_id"]
    document = goods_returns.submit_return(assignment, {
        "operation_id": "return-store-loading", "base_revision": 0, "facts_token": context["facts_token"],
        "lines": {line_id: {"box_count": "0", "tare_weight_per_box_kg": "0", "gross_weight_kg": "2", "reason": goods_returns.RETURN_REASONS[0], "comment": ""}},
    }, {"kind": "driver", "id": "driver-test"})
    goods_returns.decide_return(document["id"], document["revision"], "accepted", "", {"kind": "dashboard", "id": "admin"})
    reconciliation = page._return_reconciliation(record)
    assert reconciliation["total_returned_kg"] == "2"
    assert reconciliation["total_unexplained_kg"] == "0"
    summary = records.logistics_summary(record)
    assert next(row for row in summary["items"] if row["name"] == "Помидоры")["shortage_kg"] == "4"


def test_partial_store_loading_does_not_allow_shipments(record):
    record = choose(record)
    first, second = destinations(record)
    record = confirm(fill(record, first), first)
    before = paths.ORDER_RECORDS_FILE.read_bytes()
    with pytest.raises(records.OrderRecordConflict):
        records.save_store_shipment(record["id"], "route_4", first["id"], {
            first["positions"][0]["id"]: {"box_count": "0", "tare_weight_per_box_kg": "0", "gross_weight_kg": "8"},
        }, "partial-shipment", {"kind": "driver", "id": "driver-test"})
    assert paths.ORDER_RECORDS_FILE.read_bytes() == before


@pytest.mark.parametrize("field,value", [("box_count", "1.5"), ("gross_weight_kg", "-1"), ("tare_weight_per_box_kg", "invalid")])
def test_invalid_store_weights_cannot_be_confirmed(record, field, value):
    record = choose(record)
    dest = destinations(record)[0]
    record = fill(record, dest)
    try:
        record = records.save_store_loading_draft(record["id"], "route_4", dest["id"], dest["positions"][0]["id"], field, value, ACTOR)
    except records.OrderRecordError:
        return
    with pytest.raises(records.OrderRecordError):
        confirm(record, dest)
    assert not records.route_loading_ready(records.load_order_record(record["id"]), "route_4")


def test_mismatched_product_link_is_not_accepted(record):
    payload = json.loads(paths.ORDER_RECORDS_FILE.read_text(encoding="utf8"))
    payload["records"][0]["routes"][0]["destinations"][0]["positions"][0]["name"] = "Другой товар"
    paths.ORDER_RECORDS_FILE.write_text(json.dumps(payload), encoding="utf8")
    changed = records.load_order_record(record["id"])
    assert not records.store_loading_available(changed, "route_4")


def test_incomplete_exact_link_disables_store_loading(record):
    payload = json.loads(paths.ORDER_RECORDS_FILE.read_text(encoding="utf8"))
    payload["records"][0]["loading_lines"][0].pop("route_key")
    paths.ORDER_RECORDS_FILE.write_text(json.dumps(payload), encoding="utf8")
    legacy = records.load_order_record(record["id"])
    assert not records.store_loading_available(legacy, "route_4")
    with pytest.raises(records.OrderRecordError):
        choose(legacy)


def ui_state(record):
    state = SimpleNamespace(selected_order_id="", selected_route_key="", selected_store_id="", order_options=[], principal=ACTOR)
    state._clear_record = page.LoadingState._clear_record.__get__(state)
    state._apply_record = page.LoadingState._apply_record.__get__(state)
    state._patch_loading_measurement = page.LoadingState._patch_loading_measurement.__get__(state)
    state._refresh_options = lambda: None
    state.select_store = page.LoadingState.select_store.fn.__get__(state)
    state._apply_record(record["id"], "route_4")
    return state


def test_ui_arbitrary_selection_survives_refresh_and_preserves_other_drafts(record):
    record = choose(record)
    first, second = destinations(record)
    record = fill(record, second, "2", "0.25", "3.5")
    state = ui_state(record)
    page.LoadingState.select_store.fn(state, second["id"])
    assert state.total_loaded_net_kg == "3"
    state._apply_record(record["id"], "route_4")
    assert state.selected_store_id == second["id"]
    page.LoadingState.select_store.fn(state, first["id"])
    assert state.total_loaded_net_kg == ""
    page.LoadingState.set_context_measurement_field.fn(state, record["id"], "route_4", second["id"], second["positions"][0]["id"], "gross_weight_kg", "4.5")
    assert state.selected_store_id == first["id"]
    page.LoadingState.select_store.fn(state, second["id"])
    assert state.total_loaded_net_kg == "4"


def test_ui_confirmation_locks_only_selected_store(record):
    record = choose(record)
    first, second = destinations(record)
    record = confirm(fill(record, first), first)
    state = ui_state(record)
    assert state.is_read_only and not state.route_is_ready
    page.LoadingState.select_store.fn(state, second["id"])
    assert not state.is_read_only
    assert state.store_confirmed_count == 1
    assert state.store_confirmed_net_kg == "9"


@pytest.mark.parametrize("mode", ["route", "stores"])
def test_fast_autosave_supports_comma_decimal_without_full_refresh(record, monkeypatch, mode):
    if mode == "stores":
        record = choose(record)
        dest = destinations(record)[0]
        record = fill(record, dest, "0", "0", "1,5")
        destination_id = dest["id"]
        position_id = dest["positions"][0]["id"]
    else:
        line = next(line for line in record["loading_lines"] if line["route_key"] == "route_4")
        for field, value in {"box_count": "0", "tare_weight_per_box_kg": "0", "gross_weight_kg": "1,5"}.items():
            record = records.save_loading_draft(record["id"], "route_4", line["id"], field, value, ACTOR)
        destination_id, position_id = "", line["id"]
    state = ui_state(record)
    original_rows = [dict(row) for row in state.loading_rows]
    original_reconciliation = state.reconciliation
    original_shipments = state.shipment_rows
    def unexpected(*args):
        pytest.fail("Successful autosave must not reload the record or rebuild reconciliation")
    monkeypatch.setattr(page, "load_order_record", unexpected)
    monkeypatch.setattr(page, "_return_reconciliation", unexpected)
    page.LoadingState.set_context_measurement_field.fn(state, record["id"], "route_4", destination_id, position_id, "gross_weight_kg", "0,4")
    assert state.total_loaded_net_kg == "0.4"
    assert state.loading_rows[0]["gross_weight_kg"] == original_rows[0]["gross_weight_kg"] == "1.5"
    assert state.loading_rows[0]["preview_net_weight_kg"] == "0.4"
    assert state.selected_record["revision"] == record["revision"] + 1
    assert state.reconciliation is original_reconciliation
    assert state.shipment_rows is original_shipments
    assert state.mode_locked
    saved = records.load_order_record(record["id"])
    measurement = (destinations(saved)[0]["positions"][0]["loading"]["measurement"] if mode == "stores"
                   else next(line for line in saved["loading_lines"] if line["id"] == position_id)["measurement"])
    assert measurement["gross_weight_kg"] == "0.4"
    assert measurement["net_weight_kg"] == "0.4"


def test_autosave_of_previous_store_preserves_current_form_and_revision(record):
    record = choose(record)
    first, second = destinations(record)
    state = ui_state(record)
    current_rows = state.loading_rows
    page.LoadingState.set_context_measurement_field.fn(state, record["id"], "route_4", second["id"], second["positions"][0]["id"], "gross_weight_kg", "1,5")
    assert state.selected_store_id == first["id"]
    assert state.loading_rows is current_rows
    assert state.selected_record["revision"] == record["revision"] + 1
    assert next(card for card in state.store_cards if card["id"] == second["id"])["status"] == "draft"


def test_clear_autosaved_weight_removes_preview_without_resetting_buffer(record):
    record = choose(record)
    dest = destinations(record)[0]
    record = fill(record, dest, "0", "0", "0,4")
    state = ui_state(record)
    page.LoadingState.set_context_measurement_field.fn(state, record["id"], "route_4", dest["id"], dest["positions"][0]["id"], "gross_weight_kg", "")
    assert state.total_loaded_net_kg == ""
    assert state.loading_rows[0]["preview_net_weight_kg"] == ""
    assert state.loading_rows[0]["gross_weight_kg"] == "0.4"


def test_store_loading_page_compiles():
    rendered = str(page.loading_page())
    assert "loading-store-grid" in rendered
    assert "set_context_measurement_field" in rendered
