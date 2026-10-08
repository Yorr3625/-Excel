from copy import deepcopy
from datetime import datetime
import json
from types import SimpleNamespace

import pytest

from modules import driver_orders, order_records, paths
import orders_dashboard.orders_dashboard as dashboard


DAY = "2026-10-08"
STAMP = datetime(2026, 10, 8, 10, 0).astimezone().isoformat()


def measurement(net):
    return {"box_count": "0", "tare_weight_per_box_kg": "0", "gross_weight_kg": net, "net_weight_kg": net}


def record(record_id="order-a", mode="Область", state="new"):
    return {
        "id": record_id, "order_number": "42", "client_name": "Клиент", "mode": mode,
        "processed_at": STAMP,
        "loading": {"route_states": {"route_1": {"status": state}}},
        "loading_lines": [{"id": "load-1", "route_key": "route_1", "measurement": measurement("95")}],
        "routes": [{"route_key": "route_1", "route_label": "Маршрут №1", "destinations": [
            {"id": "store-1", "name": "ФМ 10", "positions": [
                {"id": "pos-1", "shipment": {"status": "pending", "measurement": measurement("0")}},
                {"id": "pos-2", "shipment": {"status": "pending", "measurement": measurement("0")}},
            ]},
        ]}],
    }


@pytest.fixture
def records(monkeypatch):
    items = [record()]
    monkeypatch.setattr(order_records, "_read_payload", lambda: {"records": deepcopy(items)})
    return items


@pytest.mark.parametrize("state,stage", [
    ("new", "Ожидает загрузки"), ("draft", "Загрузка начата"), ("loaded", "Готов к отгрузке"),
])
def test_loading_stage_is_route_scoped(records, state, stage):
    records[0]["loading"]["route_states"]["route_1"]["status"] = state
    trips = order_records.list_route_trip_summaries(DAY, "Область")
    assert trips[0]["stage"] == stage
    assert trips[0]["loaded_net_kg"] == ("95" if state == "loaded" else "—")
    assert trips[0]["shipped_net_kg"] == "—"


def test_partial_store_is_not_completed_and_zero_shipment_is_a_fact(records):
    positions = records[0]["routes"][0]["destinations"][0]["positions"]
    positions[0]["shipment"] = {"status": "completed", "measurement": measurement("90")}
    trip = order_records.list_route_trip_summaries(DAY, "Область")[0]
    assert trip["stage"] == "Отгрузка идёт"
    assert trip["completed_stores"] == 0
    assert trip["stores"][0]["status"] == "Частично"
    assert trip["shipped_net_kg"] == "90"
    positions[1]["shipment"] = {"status": "completed", "measurement": measurement("0")}
    trip = order_records.list_route_trip_summaries(DAY, "Область")[0]
    assert trip["completed_stores"] == 1
    assert trip["stage"] == "Отгрузка завершена"
    assert trip["shipped_net_kg"] == "90"


def test_date_mode_and_multiple_orders_are_kept_separate(records):
    records.extend([record("order-b"), record("city", "Город"), record("old")])
    records[-1]["processed_at"] = datetime(2026, 10, 7, 10).astimezone().isoformat()
    before = deepcopy(records)
    assert {trip["order_record_id"] for trip in order_records.list_route_trip_summaries(DAY, "Область")} == {"order-a", "order-b"}
    assert [trip["order_record_id"] for trip in order_records.list_route_trip_summaries(DAY, "Город")] == ["city"]
    assert records == before


def test_legacy_unallocated_loading_is_explicitly_limited(records):
    records[0]["loading_lines"][0].pop("route_key")
    records[0]["loading"]["status"] = "loaded"
    trip = order_records.list_route_trip_summaries(DAY, "Область")[0]
    assert trip["limited_data"]
    assert trip["loaded_net_kg"] == "—"


def test_assignment_lookup_uses_exact_record_and_route_and_keeps_history(tmp_path, monkeypatch):
    monkeypatch.setattr(paths, "DRIVER_ORDERS_FOLDER", tmp_path)
    for aid, rid, route in [("a" * 24, "order-a", "route_1"), ("b" * 24, "order-a", "route_1"), ("c" * 24, "order-b", "route_1"), ("d" * 24, "order-a", "route_2")]:
        driver_orders.save_snapshot({
            "schema_version": 1, "assignment_id": aid, "order_record_id": rid, "route_key": route,
            "driver_id": aid, "driver_name": "Иван", "vehicle_plate": "А123", "created_at": STAMP,
            "output_file": "private-path", "operations": [],
        })
    (tmp_path / "index.json").write_text(json.dumps({"schema_version": 1, "active": {"logical": "b" * 24}, "publications": []}), encoding="utf-8")
    result = driver_orders.route_assignment_summaries({("order-a", "route_1")})
    assert [item["assignment_id"] for item in result] == ["b" * 24, "a" * 24]
    assert [item["active"] for item in result] == [True, False]
    assert all("output_file" not in item and "operations" not in item for item in result)


def test_dispatch_enrichment_does_not_duplicate_facts_or_change_stage(records, monkeypatch):
    monkeypatch.setattr(dashboard.driver_orders, "route_assignment_summaries", lambda pairs: [
        {"order_record_id": "order-a", "route_key": "route_1", "assignment_id": str(index), "active": bool(index),
         "driver_id": "driver", "driver_name": "Иван", "vehicle_plate": "А123", "vehicle_name": "Газель"}
        for index in range(2)
    ])
    monkeypatch.setattr(dashboard.goods_returns, "list_returns", lambda: [
        {"order_record_id": "order-a", "route_key": "route_1", "status": "accepted", "total_net_kg": "5"},
        {"order_record_id": "other", "route_key": "route_1", "status": "rejected", "total_net_kg": "9"},
    ])
    trips = dashboard._dispatch_trips(DAY, "Область")
    assert len(trips) == 1 and len(trips[0]["assignments"]) == 2
    assert trips[0]["stage"] == "Ожидает загрузки"
    assert trips[0]["return_label"] == "Возврат принят"
    assert trips[0]["return_net_kg"] == "5"
    assert "иван" in trips[0]["search_text"] and "фм 10" in trips[0]["search_text"]
    assert trips[0]["loading_href"] == "/loading?order=order-a&route=route_1"


class Harness(SimpleNamespace):
    @property
    def dispatch_filtered_trips(self):
        return dashboard.State.__dict__["dispatch_filtered_trips"].fget(self)

    @property
    def dispatch_routes(self):
        return dashboard.State.__dict__["dispatch_routes"].fget(self)

    @property
    def dispatch_selected_trips(self):
        return dashboard.State.__dict__["dispatch_selected_trips"].fget(self)


def harness():
    state = Harness(
        search_query="", dispatch_stage="Все", dispatch_trips=[], dispatch_route_count=4,
        dispatch_selected_route="", dispatch_mobile_detail=False, dispatch_date=DAY, dispatch_mode="Область",
        dispatch_message="", routes_editor_open=True, route_editor_baseline=[["Original"]], route_stores=[["Edited"]],
        route_editor_pending_action="", route_editor_pending_value="", route_editor_error="", current_page="Маршруты",
        routes_source="Область", selected_route_index=3,
    )
    state._select_visible_dispatch_route = dashboard.State._select_visible_dispatch_route.__get__(state)
    state.cancel_route_editor_transition = dashboard.State.cancel_route_editor_transition.fn.__get__(state)
    state.load_dispatch = dashboard.State.load_dispatch.fn.__get__(state)
    state.set_page = dashboard.State.set_page.fn.__get__(state)
    return state


def test_search_filters_whole_trips_preserves_counts_and_editor_selection(records, monkeypatch):
    monkeypatch.setattr(dashboard.driver_orders, "route_assignment_summaries", lambda pairs: [])
    monkeypatch.setattr(dashboard.goods_returns, "list_returns", lambda: [])
    state = harness()
    state.routes_editor_open = False
    state.dispatch_trips = dashboard._dispatch_trips(DAY, "Область")
    dashboard.State.set_search_query.fn(state, "ФМ 10")
    assert len(state.dispatch_filtered_trips) == 1
    assert state.dispatch_routes[0]["store_count"] == 1
    assert state.selected_route_index == 3
    dashboard.State.select_dispatch_route.fn(state, "route_1")
    assert state.dispatch_mobile_detail
    dashboard.State.set_dispatch_stage.fn(state, "Отгрузка завершена")
    assert state.dispatch_routes == []
    assert state.dispatch_selected_route == ""
    assert not state.dispatch_mobile_detail
    dashboard.State.reset_dispatch_filters.fn(state)
    assert len(state.dispatch_routes) == 4


def test_historical_route_survives_reduced_template_count():
    trips = [{"route_key": "route_7", "route_label": "Маршрут №7", "store_count": 2, "completed_stores": 1}]
    assert [row["route_key"] for row in dashboard._dispatch_routes(trips, 2, True)] == ["route_1", "route_2", "route_7"]
    assert [row["route_key"] for row in dashboard._dispatch_routes(trips, 2, False)] == ["route_7"]


@pytest.mark.parametrize("action", ["overview", "source", "page"])
def test_template_transition_keeps_changes_until_explicit_choice(action):
    state = harness()
    if action == "overview":
        dashboard.State.close_routes_editor.fn(state)
    elif action == "source":
        dashboard.State.set_routes_source.fn(state, "Город")
    else:
        dashboard.State.set_page.fn(state, "Возвраты")
    assert state.route_editor_pending_action == action
    assert state.route_stores == [["Edited"]]
    assert state.routes_editor_open
    assert state.routes_source == "Область" and state.current_page == "Маршруты"
    dashboard.State.cancel_route_editor_transition.fn(state)
    assert state.route_stores == [["Edited"]]
    assert state.route_editor_pending_action == ""


def test_discard_transition_restores_template_without_saving():
    state = harness()
    state.route_editor_pending_action = "source"
    state.route_editor_pending_value = "Город"
    captured = []
    state.load_routes = lambda: captured.append(state.routes_source)
    dashboard.State.finish_route_editor_transition.fn(state, False)
    assert state.route_stores == [["Original"]]
    assert captured == ["Город"]


def test_failed_template_save_stays_in_editor_with_draft():
    state = harness()
    state.route_editor_pending_action = "overview"
    def fail():
        raise OSError("Disk error")
    state.save_routes = fail
    dashboard.State.finish_route_editor_transition.fn(state, True)
    assert state.routes_editor_open
    assert state.route_stores == [["Edited"]]
    assert state.route_editor_pending_action == "overview"
    assert "Disk error" in state.route_editor_error
