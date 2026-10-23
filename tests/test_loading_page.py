import json
from copy import deepcopy
from types import SimpleNamespace

import pytest

from modules import dashboard_sessions
from orders_dashboard import loading_page


def measurement(boxes="", tare="", gross="", net=""):
    return {
        "box_count": boxes,
        "tare_weight_per_box_kg": tare,
        "gross_weight_kg": gross,
        "net_weight_kg": net,
    }


def shipment(status="pending", value=""):
    return {
        "status": status,
        "measurement": measurement("0", "0", value, value) if status == "completed" else measurement(),
    }


def _record(status="new"):
    return {
        "id": "record-1",
        "revision": 0,
        "order_number": "42",
        "client_name": "ООО Ромашка",
        "processed_at": "2026-10-05T08:30:00+03:00",
        "mode": "Область",
        "mail_metadata": {"received_display": "05.10.2026 07:00"},
        "loading": {
            "status": status,
            "route_states": {
                "route_1": {"status": "new"},
                "route_2": {"status": "new"},
            },
        },
        "routes": [
            {
                "route_key": "route_1",
                "route_label": "Маршрут №1",
                "destinations": [{
                    "id": "store-1",
                    "name": "ФМ 10",
                    "positions": [{
                        "id": "position-1",
                        "name": "Помидоры",
                        "loading_line_id": "line-1",
                        "shipment": shipment(),
                    }],
                }],
            },
            {
                "route_key": "route_2",
                "route_label": "Маршрут №2",
                "destinations": [{
                    "id": "store-2",
                    "name": "ФМ 20",
                    "positions": [{
                        "id": "position-2",
                        "name": "Помидоры",
                        "loading_line_id": "line-2",
                        "shipment": shipment(),
                    }],
                }],
            },
        ],
        "loading_lines": [
            {"id": "line-1", "route_key": "route_1", "name": "Помидоры", "unit": "kg", "planned_amount": "20", "measurement": measurement()},
            {"id": "line-2", "route_key": "route_2", "name": "Помидоры", "unit": "kg", "planned_amount": "5", "measurement": measurement()},
        ],
    }


def _state(router=None):
    state = SimpleNamespace(
        router=router or {},
        is_authorized=False,
        principal={},
        order_options=[],
        order_option_labels=[],
        selected_order_label="",
        selected_order_id="",
        route_options=[],
        route_option_labels=[],
        selected_route_label="",
        selected_route_key="",
        route_loaded_count=0,
        route_total_count=0,
        back_target="/",
        selected_record={},
        summary_order_number="",
        summary_client_name="",
        summary_processed_at="",
        summary_mode="",
        summary_routes="",
        summary_received_at="",
        summary_position_count=0,
        total_ordered_kg="0",
        total_loaded_net_kg="",
        loading_rows=[],
        loading_sort="source",
        draft_measurements={},
        shipment_rows=[],
        shipment_completed_count=0,
        shipment_total_count=0,
        shipment_status="waiting_loading",
        reconciliation_rows=[],
        reconciliation={},
        summary_expanded=True,
        is_read_only=False,
        status="",
        order_not_found=False,
        save_completed=False,
    )
    state._refresh_options = loading_page.LoadingState._refresh_options.__get__(state)
    state._clear_record = loading_page.LoadingState._clear_record.__get__(state)
    state._apply_record = loading_page.LoadingState._apply_record.__get__(state)
    state.select_order = loading_page.LoadingState.select_order.fn.__get__(state)
    state.select_route = loading_page.LoadingState.select_route.fn.__get__(state)
    return state


def test_loading_principal_accepts_dashboard_session():
    dashboard_sessions.reset_sessions()
    token = dashboard_sessions.create_session()

    principal = loading_page.loading_principal_for_router({
        "headers": {"cookie": f"{dashboard_sessions.SESSION_COOKIE}={token}"}
    })

    assert principal == {"kind": "dashboard", "id": "admin", "name": "Администратор"}


def test_loading_page_selects_order_and_first_route(monkeypatch):
    record = _record()
    monkeypatch.setattr(
        loading_page,
        "loading_principal_for_router",
        lambda router: {"kind": "loader", "id": "loader-1", "name": "Иван"},
    )
    monkeypatch.setattr(
        loading_page,
        "list_order_record_summaries",
        lambda: [{"id": "record-1", "order_number": "42", "client_name": "ООО Ромашка", "processed_at": record["processed_at"], "status": "new"}],
    )
    monkeypatch.setattr(loading_page, "load_order_record", lambda order_id: record)
    state = _state(SimpleNamespace(url=SimpleNamespace(query_parameters={"order": "record-1"})))

    loading_page.LoadingState.load_loading_page.fn(state)

    assert state.selected_order_id == "record-1"
    assert state.selected_route_key == "route_1"
    assert state.route_option_labels == ["Маршрут №1", "Маршрут №2"]
    assert [row["id"] for row in state.loading_rows] == ["line-1"]
    assert state.route_total_count == 2


def test_field_autosave_survives_refresh_and_route_switch(monkeypatch):
    holder = {"record": _record()}
    state = _state()
    monkeypatch.setattr(loading_page, "load_order_record", lambda order_id: holder["record"])
    state._apply_record("record-1")

    def save_draft(order_id, route_key, line_id, field, value, actor):
        record = holder["record"]
        line = next(item for item in record["loading_lines"] if item["id"] == line_id)
        line["measurement"][field] = value
        record["loading"]["route_states"][route_key]["status"] = "draft"
        record["loading"]["status"] = "draft"
        record["revision"] += 1
        return record

    monkeypatch.setattr(loading_page, "save_loading_draft", save_draft)
    loading_page.LoadingState.set_loading_sort.fn(state, "weight_desc")
    loading_page.LoadingState.set_measurement_field.fn(state, "line-1", "box_count", "12")

    assert holder["record"]["loading_lines"][0]["measurement"]["box_count"] == "12"
    assert state.status == "Черновик сохранён"
    loading_page.LoadingState.select_route.fn(state, "route_2")
    assert state.selected_route_key == "route_2"
    loading_page.LoadingState.select_route.fn(state, "route_1")
    assert state.draft_measurements["line-1"]["box_count"] == "12"
    assert state.loading_sort == "weight_desc"


def test_zero_measurement_marks_row_for_reason_selection():
    record = _record()
    record["loading_lines"][0]["measurement"] = measurement("0", "0", "0", "0")
    rows = loading_page._loading_rows(record, "route_1", {"line-1": record["loading_lines"][0]["measurement"]})

    assert rows[0]["needs_zero_reason"] is True
    assert rows[0]["zero_reason"] == ""

    record["loading_lines"][0]["measurement"] = measurement("0", "0", "1", "1")
    rows = loading_page._loading_rows(record, "route_1", {"line-1": record["loading_lines"][0]["measurement"]})
    assert rows[0]["needs_zero_reason"] is False


def test_confirming_route_locks_only_selected_route(monkeypatch):
    holder = {"record": _record()}
    state = _state()
    monkeypatch.setattr(loading_page, "load_order_record", lambda order_id: holder["record"])
    state._apply_record("record-1")
    state.principal = {"kind": "loader", "id": "loader-1", "name": "Иван"}
    captured = {}

    def confirm(order_id, revision, route_key, actor):
        captured.update({"order_id": order_id, "revision": revision, "route_key": route_key, "actor": actor})
        record = holder["record"]
        record["loading_lines"][0]["measurement"] = measurement("0", "0", "20", "20")
        record["loading"]["route_states"][route_key]["status"] = "loaded"
        record["revision"] += 1
        return record

    monkeypatch.setattr(loading_page, "confirm_route_loading", confirm)
    loading_page.LoadingState.save_loading.fn(state)

    assert captured["route_key"] == "route_1"
    assert state.is_read_only is True
    loading_page.LoadingState.select_route.fn(state, "route_2")
    assert state.is_read_only is False


def test_order_switch_preserves_autosaved_draft(monkeypatch):
    records = {"record-1": _record(), "record-2": {**_record(), "id": "record-2"}}
    records["record-1"]["loading_lines"][0]["measurement"] = measurement("12")
    monkeypatch.setattr(loading_page, "load_order_record", records.__getitem__)
    state = _state()
    state._apply_record("record-1")

    result = loading_page.LoadingState.request_order.fn(state, "record-2")

    assert result is not None
    assert state.selected_order_id == "record-2"
    loading_page.LoadingState.request_order.fn(state, "record-1")
    assert state.draft_measurements["line-1"]["box_count"] == "12"


@pytest.mark.parametrize("sort_order,expected", [
    ("source", ["tomato", "banana", "melon", "zero"]),
    ("name_asc", ["zero", "banana", "melon", "tomato"]),
    ("name_desc", ["tomato", "melon", "banana", "zero"]),
    ("weight_asc", ["zero", "banana", "tomato", "melon"]),
    ("weight_desc", ["melon", "tomato", "banana", "zero"]),
])
def test_loading_product_sort_is_numeric_and_does_not_mutate_rows(sort_order, expected):
    rows = [
        {"id": "tomato", "name": "Помидоры", "planned_kg": "10", "weighings": [{"id": "part-1"}]},
        {"id": "banana", "name": "Бананы", "planned_kg": "2,5"},
        {"id": "melon", "name": "Дыня", "planned_kg": "100"},
        {"id": "zero", "name": " арбуз ", "planned_kg": "0"},
    ]
    original = deepcopy(rows)

    result = loading_page._sort_loading_rows(rows, sort_order)

    assert [row["id"] for row in result] == expected
    assert rows == original
    assert result is not rows
    assert all(any(row is source for source in rows) for row in result)


def test_loading_alphabet_sort_places_yo_with_e():
    rows = [{"name": name} for name in ("Яблоки", "Жимолость", "Ёлка", "Ежевика", "Ель")]

    assert [row["name"] for row in loading_page._sort_loading_rows(rows, "name_asc")] == [
        "Ежевика", "Ёлка", "Ель", "Жимолость", "Яблоки",
    ]


@pytest.mark.parametrize("sort_order", ["weight_asc", "weight_desc"])
def test_loading_weight_sort_has_stable_alphabetic_ties_and_missing_values_last(sort_order):
    rows = [
        {"id": "b", "name": "Бананы", "planned_kg": "10"},
        {"id": "a-1", "name": "Арбуз", "planned_kg": "10"},
        {"id": "a-2", "name": "Арбуз", "planned_kg": "10"},
        {"id": "bad", "name": "Дыня", "planned_kg": "не число"},
        {"id": "nan", "name": "Малина", "planned_kg": "NaN"},
        {"id": "inf", "name": "Персик", "planned_kg": "Infinity"},
        {"id": "missing", "name": "Яблоки"},
    ]

    assert [row["id"] for row in loading_page._sort_loading_rows(rows, sort_order)] == [
        "a-1", "a-2", "b", "bad", "nan", "inf", "missing",
    ]


@pytest.mark.parametrize("mode", ["route", "stores"])
def test_loading_sort_keeps_measurements_totals_and_context_in_both_modes(mode):
    record = _record()
    first = record["loading_lines"][0]
    first["measurement"] = measurement("1", "1", "11", "10")
    second = {**deepcopy(first), "id": "line-3", "name": "Арбуз", "planned_amount": "2"}
    record["loading_lines"].append(second)
    destination = record["routes"][0]["destinations"][0]
    destination["positions"] = [
        {"id": "position-" + line["id"], "name": line["name"], "planned_amount": line["planned_amount"],
         "loading": {"measurement": deepcopy(line["measurement"])}}
        for line in (first, second)
    ]
    rows = (loading_page._loading_rows(record, "route_1", {}) if mode == "route" else
            loading_page._store_loading_rows(record, "route_1", destination))
    state = SimpleNamespace(loading_rows=rows, loading_sort="source", is_read_only=True)
    original = deepcopy(rows)
    totals = loading_page._loading_totals(rows)

    loading_page.LoadingState.set_loading_sort.fn(state, "name_asc")
    sorted_rows = loading_page.LoadingState.__dict__["sorted_loading_rows"].fget(state)

    assert [row["name"] for row in sorted_rows] == ["Арбуз", "Помидоры"]
    assert loading_page._loading_totals(sorted_rows) == totals == ("22", "20")
    assert rows == original
    assert all(row["order_id"] == "record-1" and row["route_key"] == "route_1" for row in sorted_rows)
    assert all(row["destination_id"] == ("store-1" if mode == "stores" else "") for row in sorted_rows)
    loading_page.LoadingState.set_loading_sort.fn(state, "source")
    assert loading_page.LoadingState.__dict__["sorted_loading_rows"].fget(state) == original


def test_loading_sort_rejects_unknown_options_and_survives_record_changes(monkeypatch):
    record = _record()
    monkeypatch.setattr(loading_page, "load_order_record", lambda order_id: {**record, "id": order_id})
    state = _state()
    loading_page.LoadingState.set_loading_sort.fn(state, "name_desc")
    loading_page.LoadingState.set_loading_sort.fn(state, "unknown")
    assert state.loading_sort == "name_desc"

    state._apply_record("record-1")
    state._apply_record("record-1", "route_2")
    state._apply_record("record-2", "route_1")
    state._clear_record()

    assert state.loading_sort == "name_desc"
    assert loading_page._sort_loading_rows([], "weight_asc") == []


def test_loading_page_renders_accessible_sort_control_and_stable_product_keys():
    rendered = str(loading_page._loading_table())

    assert "loading-product-sort" in rendered
    assert "htmlFor" in rendered
    assert "set_loading_sort" in rendered
    assert "sorted_loading_rows" in rendered
    assert 'key:row_rx_state_?.["id"]' in rendered
    for label in loading_page.LOADING_SORT_OPTIONS.values():
        assert json.dumps(label) in rendered
    assert "sorted_loading_rows" in str(loading_page._store_loading_reconciliation())


def test_simple_mode_page_renders_separate_box_and_weight_steps():
    mode = str(loading_page._loading_mode_control())
    simple = str(loading_page._simple_loading_table())
    page = str(loading_page.loading_page())

    assert json.dumps("Простой · по ящикам") in mode
    assert "choose_loading_mode" in mode and "mode_locked" in mode
    assert json.dumps("Подтвердить ящики") in simple
    assert json.dumps("Указать фактический вес") in simple
    assert json.dumps("Подтвердить фактический вес") in simple
    assert "confirm_simple_boxes" in simple and "confirm_simple_route_weight" in simple
    assert "simple_boxes_confirmed" in simple and "route_is_ready" in simple
    assert "simple-loading-sort" in simple and "sorted_loading_rows" in simple
    assert "set_context_measurement_field" in simple
    assert json.dumps("Добавить взвешивание") not in simple
    assert json.dumps("Загружено нетто") not in simple
    assert "loading_mode_rx_state_?.valueOf?.() === \"simple\"" in page
    assert "_simple_loading_table" not in page  # The conditional contains rendered markup, not a Python function reference.
