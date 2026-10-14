from concurrent.futures import ThreadPoolExecutor
from decimal import Decimal
import json
import threading
import zipfile
from types import SimpleNamespace

import pytest
from openpyxl import Workbook
from starlette.testclient import TestClient

from modules import backup, driver_orders, goods_returns, order_records, paths, vehicle_trips
from orders_dashboard import loading_page
import orders_dashboard.orders_dashboard as dashboard
from orders_dashboard.orders_dashboard import custom_api


LOADER = {"kind": "loader", "id": "loader-1", "name": "Грузчик"}
DRIVER = {"kind": "driver", "id": "driver-1", "name": "Водитель"}
ADMIN = {"kind": "dashboard", "id": "admin", "name": "Администратор"}


def _weight(value):
    return {"box_count": "0", "tare_weight_per_box_kg": "0", "gross_weight_kg": str(value)}


@pytest.fixture
def route(tmp_path, monkeypatch):
    root = tmp_path / "processed"
    output = root / "13.10.26" / "order.xlsx"
    output.parent.mkdir(parents=True)
    workbook = Workbook()
    sheet = workbook.active
    sheet.title = "Маршрут №4"
    sheet.append(["Товар", "Сумма", "ФМ 10", "ФМ 14", "ФМ 47"])
    sheet.append(["Дыня", "", 8, 4, 2])
    workbook.save(output)
    workbook.close()
    monkeypatch.setattr(paths, "PROCESSED_FOLDER", root)
    monkeypatch.setattr(paths, "ORDER_RECORDS_FILE", tmp_path / "data" / "order_records.json")
    monkeypatch.setattr(paths, "DRIVER_ORDERS_FOLDER", tmp_path / "data" / "driver_orders")
    monkeypatch.setattr(paths, "GOODS_RETURNS_FILE", tmp_path / "data" / "goods_returns.json")
    monkeypatch.setattr(paths, "VEHICLE_TRIPS_FILE", tmp_path / "data" / "vehicle_trips.sqlite3")
    record = order_records.create_processed_order_record(output, "order.xlsx", "Тест", "Город")
    assignment = {
        "route": "route_4", "label": "Маршрут №4", "driver_id": DRIVER["id"], "driver_name": DRIVER["name"],
        "vehicle_id": "vehicle-1", "vehicle_name": "Газель", "vehicle_plate": "А123ВС71",
    }
    source_path = driver_orders.publish_assignments(output, "Город", "order.xlsx", [assignment], record)[0]
    source = driver_orders.load_snapshot(source_path)
    record = order_records.set_route_loading_mode(record["id"], record["revision"], "route_4", "stores")
    return record["id"], source


def _record(order_id):
    return order_records.load_order_record(order_id)


def _store(order_id, index):
    return _record(order_id)["routes"][0]["destinations"][index]


def _confirm(order_id, index, net):
    destination = _store(order_id, index)
    position = destination["positions"][0]
    record = _record(order_id)
    for field, value in _weight(net).items():
        record = order_records.save_store_loading_draft(order_id, "route_4", destination["id"], position["id"], field, value, LOADER)
    return order_records.confirm_store_loading(order_id, record["revision"], "route_4", destination["id"], LOADER)


def _release(order_id, operation="release-1", revision=None):
    if revision is None:
        revision = _record(order_id)["revision"]
    return driver_orders.release_partial_loading(order_id, "route_4", revision, LOADER, operation)


def _ship(order_id, snapshot, index, net, operation):
    destination = _store(order_id, index)
    store = next(store for store in snapshot["stores"] if store["order_record_destination_id"] == destination["id"])
    position = destination["positions"][0]
    order_records.save_store_shipment(order_id, "route_4", destination["id"], {position["id"]: _weight(net)}, operation, DRIVER,
                                      loading_batch_id=snapshot["loading_batch_id"])
    result = driver_orders.complete_store(snapshot["assignment_id"], store["store_id"],
                                          {store["lines"][0]["line_id"]: _weight(net)}, operation, snapshot["revision"])
    return result


def test_two_stores_depart_and_third_can_load_after_return(route):
    order_id, source = route
    first, second, third = [_store(order_id, i) for i in range(3)]
    _confirm(order_id, 0, 8)
    _confirm(order_id, 1, 4)
    assert not order_records.route_loading_ready(_record(order_id), "route_4")
    assert driver_orders.partial_loading_blocker(order_id, "route_4") == ""
    batch = _release(order_id)
    assert batch["source_assignment_id"] == source["assignment_id"]
    assert {store["order_record_destination_id"] for store in batch["stores"]} == {first["id"], second["id"]}
    assert order_records.loading_batches(_record(order_id), "route_4")[0]["destination_ids"] == [first["id"], second["id"]]
    assert order_records.logistics_summary(_record(order_id))["total_loaded_net_kg"] == "12"
    day = _record(order_id)["processed_at"][:10]
    assert order_records.list_route_trip_summaries(day, "Город")[0]["stage"] == "Загружен частично"
    assert loading_page._store_loading_cards(_record(order_id), "route_4")[2]["status_label"] == "Ожидает загрузки"
    initial_balance = order_records.route_return_balance(_record(order_id), "route_4", batch["loading_batch_id"])
    assert initial_balance["lines"][0]["loaded_net_kg"] == "12"
    assert initial_balance["lines"][0]["planned_kg"] == "12"
    assert [row["id"] for row in initial_balance["destinations"]] == sorted((first["id"], second["id"]))
    assert goods_returns.return_context(batch)["loading_ready"]

    snapshot = _ship(order_id, batch, 0, 7, "ship-1")
    snapshot = _ship(order_id, snapshot, 1, 4, "ship-2")
    assert driver_orders.partial_loading_blocker(order_id, "route_4")
    context = goods_returns.return_context(snapshot)
    assert context["complete"] and context["eligible"]
    line = context["lines"][0]
    assert (line["loaded_net_kg"], line["shipped_net_kg"], line["available_net_kg"]) == ("12", "11", "1")
    pending = goods_returns.submit_return(snapshot, {
        "operation_id": "return-1", "base_revision": 0, "facts_token": context["facts_token"],
        "lines": {line["loading_line_id"]: {**_weight(1), "reason": goods_returns.RETURN_REASONS[0], "comment": ""}},
    }, DRIVER)
    assert driver_orders.partial_loading_blocker(order_id, "route_4")
    goods_returns.decide_return(pending["id"], pending["revision"], "accepted", "", ADMIN)
    assert driver_orders.partial_loading_blocker(order_id, "route_4") == ""

    _confirm(order_id, 2, 2)
    second_batch = _release(order_id, "release-2")
    assert second_batch["assignment_id"] != snapshot["assignment_id"]
    assert [store["order_record_destination_id"] for store in second_batch["stores"]] == [third["id"]]
    assert order_records.route_return_balance(_record(order_id), "route_4", batch["loading_batch_id"])["lines"][0]["available_net_kg"] == "1"
    assert order_records.route_return_balance(_record(order_id), "route_4", second_batch["loading_batch_id"])["lines"][0]["loaded_net_kg"] == "2"
    first_after = goods_returns.return_context(snapshot)
    assert first_after["document"]["id"] == pending["id"]
    assert first_after["facts_token"] == context["facts_token"]
    assert goods_returns.return_context(second_batch)["document"] is None
    assert order_records.logistics_summary(_record(order_id))["total_loaded_net_kg"] == "14"
    assert Decimal(order_records.logistics_summary(_record(order_id))["total_shipped_net_kg"]) == Decimal("11")
    assert driver_orders.completed_delivery_report()["completed_stores"] == 2
    assert driver_orders.find_assignment_for_driver(DRIVER["id"])["assignment_id"] == second_batch["assignment_id"]
    second_completed = _ship(order_id, second_batch, 2, 1, "ship-3")
    second_context = goods_returns.return_context(second_completed)
    assert second_context["eligible"]
    second_line = second_context["lines"][0]
    assert (second_line["loaded_net_kg"], second_line["shipped_net_kg"], second_line["available_net_kg"]) == ("2", "1", "1")
    submitted = goods_returns.submit_return(second_completed, {
        "operation_id": "return-2", "base_revision": 0, "facts_token": second_context["facts_token"],
        "lines": {second_line["loading_line_id"]: {**_weight(1), "reason": goods_returns.RETURN_REASONS[0], "comment": ""}},
    }, DRIVER)
    goods_returns.decide_return(submitted["id"], submitted["revision"], "accepted", "", ADMIN)
    assert goods_returns.return_context(snapshot)["facts_token"] == context["facts_token"]
    assert goods_returns.accepted_by_loading_line(order_id) == {line["loading_line_id"]: "2"}
    assert driver_orders.completed_delivery_report()["completed_stores"] == 3
    assert order_records.logistics_summary(_record(order_id))["total_loaded_net_kg"] == "14"
    assert order_records.logistics_summary(_record(order_id))["total_shipped_net_kg"] == "12"
    assert {item["id"] for item in goods_returns.list_returns()} == {pending["id"], submitted["id"]}


def test_partial_loading_guards_and_retry(route, monkeypatch):
    order_id, source = route
    record = _record(order_id)
    before = paths.ORDER_RECORDS_FILE.read_bytes()
    with pytest.raises(order_records.OrderRecordConflict, match="Нет новых"):
        _release(order_id)
    assert paths.ORDER_RECORDS_FILE.read_bytes() == before
    _confirm(order_id, 0, 8)
    with pytest.raises(order_records.OrderRecordConflict, match="изменены"):
        _release(order_id, revision=record["revision"])
    first = _release(order_id)
    current = _record(order_id)
    with pytest.raises(order_records.OrderRecordConflict, match="конкретную отправку"):
        order_records.route_return_balance(current, "route_4")
    with pytest.raises(order_records.OrderRecordConflict, match="конкретную отправку"):
        order_records.save_store_shipment(order_id, "route_4", _store(order_id, 0)["id"],
                                          {_store(order_id, 0)["positions"][0]["id"]: _weight(5)}, "legacy-ship", DRIVER)
    with pytest.raises(order_records.OrderRecordConflict, match="не включён"):
        order_records.save_store_shipment(order_id, "route_4", _store(order_id, 2)["id"],
                                          {_store(order_id, 2)["positions"][0]["id"]: _weight(2)}, "foreign-ship", DRIVER,
                                          loading_batch_id=first["loading_batch_id"])
    assert _record(order_id)["revision"] == current["revision"]
    with pytest.raises(driver_orders.DriverOrderConflict, match="Сначала завершите"):
        _release(order_id, "release-2")
    assert _release(order_id) == first
    assert driver_orders.publish_assignments(paths.PROCESSED_FOLDER / "13.10.26" / "order.xlsx", "Город", "order.xlsx",
                                             [{"route": "route_4", "driver_id": DRIVER["id"], "vehicle_id": "vehicle-1"}], current)[0] == driver_orders.sidecar_path(first["assignment_id"])
    assert driver_orders.find_assignment_for_driver(DRIVER["id"])["assignment_id"] == first["assignment_id"]


def test_loading_ui_shows_confirmation_and_keeps_remaining_store_available(route):
    order_id, _ = route
    _confirm(order_id, 0, 8)
    _confirm(order_id, 1, 4)
    state = SimpleNamespace(selected_order_id="", selected_route_key="", selected_store_id="", order_options=[], principal=LOADER)
    state._clear_record = loading_page.LoadingState._clear_record.__get__(state)
    state._apply_record = loading_page.LoadingState._apply_record.__get__(state)
    state._refresh_options = lambda: None
    assert state._apply_record(order_id, "route_4")
    assert not state.partial_has_batches
    assert state.partial_waiting_count == 1
    assert state.partial_send_net_kg == "12"
    assert [store["name"] for store in state.partial_send_stores] == ["ФМ 10", "ФМ 14"]
    assert not state.partial_blocker
    rendered = str(loading_page.loading_page())
    assert json.dumps("Завершить загрузку частично") in rendered
    assert json.dumps("Подтвердить отправку") in rendered

    loading_page.LoadingState.prepare_partial_loading.fn(state)
    assert state.partial_dialog_open
    assert state.partial_dialog_names == ["ФМ 10", "ФМ 14"]
    assert state.partial_dialog_waiting_count == 1
    assert state._partial_order_id == order_id
    assert state._partial_route_key == "route_4"
    loading_page.LoadingState.finish_partial_loading.fn(state)
    assert not state.partial_dialog_open
    assert state.partial_has_batches
    assert not state.partial_send_stores
    assert state.store_cards[2]["status_label"] == "Ожидает загрузки"
    assert state.store_cards[2]["released"] is False
    assert len(order_records.loading_batches(_record(order_id), "route_4")) == 1


def test_loading_dialog_rejects_stale_selection_without_releasing(route):
    order_id, _ = route
    _confirm(order_id, 0, 8)
    state = SimpleNamespace(selected_order_id="", selected_route_key="", selected_store_id="", order_options=[], principal=LOADER)
    state._clear_record = loading_page.LoadingState._clear_record.__get__(state)
    state._apply_record = loading_page.LoadingState._apply_record.__get__(state)
    state._refresh_options = lambda: None
    state._apply_record(order_id, "route_4")
    loading_page.LoadingState.prepare_partial_loading.fn(state)
    third = _store(order_id, 2)
    order_records.save_store_loading_draft(order_id, "route_4", third["id"], third["positions"][0]["id"], "gross_weight_kg", "2", LOADER)

    loading_page.LoadingState.finish_partial_loading.fn(state)

    assert state.partial_dialog_open
    assert "изменены" in state.partial_dialog_error
    assert not order_records.loading_batches(_record(order_id), "route_4")
    loading_page.LoadingState.set_partial_dialog_open.fn(state, False)
    loading_page.LoadingState.prepare_partial_loading.fn(state)
    loading_page.LoadingState.finish_partial_loading.fn(state)
    assert not state.partial_dialog_error
    assert len(order_records.loading_batches(_record(order_id), "route_4")) == 1


def test_driver_api_serves_only_released_stores_and_rejects_source_replays(route, monkeypatch):
    order_id, source = route
    _confirm(order_id, 0, 8)
    batch = _release(order_id)
    monkeypatch.setattr(dashboard, "_session", lambda request, mutate=False: ({"driver_id": DRIVER["id"]}, None))
    monkeypatch.setattr(dashboard, "_mileage_required_response", lambda session, assignment=None: None)
    client = TestClient(custom_api)

    response = client.get("/api/driver/order")
    assert response.status_code == 200
    assignment = response.json()["assignment"]
    assert assignment["assignment_id"] == batch["assignment_id"]
    assert assignment["loading_status"] == "partial"
    assert assignment["waiting_store_count"] == 2
    assert len(assignment["stores"]) == 1
    store = assignment["stores"][0]
    values = {store["lines"][0]["line_id"]: _weight(7)}
    revision = _record(order_id)["revision"]

    stale = client.post(f"/api/driver/order/stores/{source['stores'][2]['store_id']}/complete", json={
        "assignment_id": source["assignment_id"], "base_revision": 0,
        "measurements": {source["stores"][2]["lines"][0]["line_id"]: _weight(2)}, "operation_id": "stale-source",
    })
    assert stale.status_code == 409
    assert _record(order_id)["revision"] == revision
    assert driver_orders.load_snapshot(source["assignment_id"])["stores"][2]["status"] == "pending"
    completed = client.post(f"/api/driver/order/stores/{store['store_id']}/complete", json={
        "assignment_id": batch["assignment_id"], "base_revision": batch["revision"],
        "measurements": values, "operation_id": "ship-api",
    })
    assert completed.status_code == 200, completed.json()
    assert completed.json()["assignment"]["stores"][0]["status"] == "completed"
    assert _store(order_id, 0)["positions"][0]["shipment"]["status"] == "completed"


def test_vehicle_trip_imports_only_batch_and_projects_shipment(route, monkeypatch, tmp_path):
    order_id, _ = route
    _confirm(order_id, 0, 8)
    _confirm(order_id, 1, 4)
    batch = _release(order_id)
    monkeypatch.setattr(vehicle_trips, "_fleet_available", lambda snapshot: True)
    trip = vehicle_trips.create_trip([batch["assignment_id"]], "2026-10-14", ADMIN, "trip-created")
    assert trip["members"][0]["loading_batch_id"] == batch["loading_batch_id"]
    trip = vehicle_trips.start_trip(trip["id"], trip["revision"], ADMIN, "trip-started")
    assert len(trip["stops"]) == 2
    assert trip["products"][0]["loaded"] == "12"
    assert [item["loaded"] for item in vehicle_trips.preview_members(trip)] == ["12"]
    assert driver_orders.partial_loading_blocker(order_id, "route_4") == ""
    for index, stop in enumerate(trip["stops"]):
        amount = "8" if index == 0 else "4"
        trip = vehicle_trips.complete_stop(trip["id"], stop["id"], {
            "operation_id": "trip-stop-" + str(index), "base_revision": stop["revision"],
            "measurements": {stop["lines"][0]["id"]: {"kind": "net", "net_weight_kg": amount}},
            "reasons": {},
        }, DRIVER)
    assert not trip["projection_error"]
    assert [store["status"] for store in driver_orders.load_snapshot(batch["assignment_id"])["stores"]] == ["completed", "completed"]
    assert [destination["positions"][0]["shipment"]["status"] for destination in _record(order_id)["routes"][0]["destinations"]] == [
        "completed", "completed", "pending",
    ]
    assert driver_orders.partial_loading_blocker(order_id, "route_4") == ""
    trip = vehicle_trips.close_trip(trip["id"], trip["revision"], ADMIN, "trip-closed")
    assert trip["status"] == "closed"
    assert driver_orders.partial_loading_blocker(order_id, "route_4") == ""
    _confirm(order_id, 2, 2)
    second = _release(order_id, "release-after-trip")
    assert len(second["stores"]) == 1
    assert vehicle_trips.load_trip(trip["id"])["products"][0]["loaded"] == "12"
    vehicle_trips.restore_source_snapshots(paths.VEHICLE_TRIPS_FILE, tmp_path)
    assert driver_orders.find_assignment_for_driver(DRIVER["id"])["assignment_id"] == second["assignment_id"]


def test_next_loaded_stores_join_active_trip_without_reimporting_first(route, monkeypatch):
    order_id, _ = route
    _confirm(order_id, 0, 8)
    first = _release(order_id)
    monkeypatch.setattr(vehicle_trips, "_fleet_available", lambda snapshot: True)
    trip = vehicle_trips.create_trip([first["assignment_id"]], "2026-10-14", ADMIN, "first-created")
    trip = vehicle_trips.start_trip(trip["id"], trip["revision"], ADMIN, "first-started")
    assert vehicle_trips.stock(trip)[0]["remaining_kg"] == "8"
    _confirm(order_id, 1, 4)
    next_batch = _release(order_id, "next-departure")
    trip = vehicle_trips.add_member(trip["id"], trip["revision"], next_batch["assignment_id"], ADMIN, "next-attached")
    assert vehicle_trips.stock(trip)[0]["remaining_kg"] == "12"
    assert len(trip["stops"]) == 2
    assert len(trip["members"]) == 2


def test_concurrent_partial_release_is_idempotent(route):
    order_id, _ = route
    _confirm(order_id, 0, 8)
    revision = _record(order_id)["revision"]
    with ThreadPoolExecutor(max_workers=5) as pool:
        results = list(pool.map(lambda _: _release(order_id, "same-release", revision), range(5)))
    assert len({item["assignment_id"] for item in results}) == 1
    assert len(order_records.loading_batches(_record(order_id), "route_4")) == 1
    assert driver_orders._active_assignment_ids() == {results[0]["assignment_id"]}


def test_second_release_with_new_operation_cannot_reissue_first_stores(route):
    order_id, _ = route
    _confirm(order_id, 0, 8)
    revision = _record(order_id)["revision"]

    def attempt(operation_id):
        try:
            return _release(order_id, operation_id, revision)
        except driver_orders.DriverOrderConflict:
            return None

    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(attempt, ("one", "two")))
    assert len([item for item in results if item]) == 1
    assert len(order_records.loading_batches(_record(order_id), "route_4")) == 1


def test_recovering_pending_group_rechecks_previous_dispatch(route):
    order_id, source = route
    _confirm(order_id, 0, 8)
    first = _release(order_id)
    _confirm(order_id, 1, 4)
    pending = order_records.release_store_loading(order_id, _record(order_id)["revision"], "route_4",
                                                  source["assignment_id"], "pending-second", LOADER)
    assert not driver_orders.loading_batch_published(pending)
    with pytest.raises(driver_orders.DriverOrderConflict, match="Сначала завершите"):
        _release(order_id, "pending-second")
    assert driver_orders.find_assignment_for_driver(DRIVER["id"])["assignment_id"] == first["assignment_id"]
    assert not driver_orders.sidecar_path(driver_orders._stable_id(source["assignment_id"], "loading-batch", pending["id"])).exists()


def test_unauthorized_and_invalid_batches_leave_order_untouched(route):
    order_id, source = route
    _confirm(order_id, 0, 8)
    before = paths.ORDER_RECORDS_FILE.read_bytes()
    with pytest.raises(driver_orders.DriverOrderError, match="Нет доступа"):
        driver_orders.release_partial_loading(order_id, "route_4", _record(order_id)["revision"], DRIVER, "forbidden")
    with pytest.raises(order_records.OrderRecordError, match="Нет доступа"):
        order_records.release_store_loading(order_id, _record(order_id)["revision"], "route_4", source["assignment_id"], "forbidden", DRIVER)
    assert paths.ORDER_RECORDS_FILE.read_bytes() == before
    batch = _release(order_id)
    record = _record(order_id)
    record["loading"]["route_states"]["route_4"]["batches"][0]["destination_ids"].append("another-route-store")
    with pytest.raises(order_records.OrderRecordError, match="не относится к маршруту"):
        order_records.loading_batches(record, "route_4")
    assert _record(order_id)["revision"] > 0
    assert driver_orders.load_snapshot(batch["assignment_id"])["loading_batch_id"]


def test_backup_waits_for_both_driver_shipment_writes(route, tmp_path, monkeypatch):
    order_id, _ = route
    _confirm(order_id, 0, 8)
    batch = _release(order_id)
    store = batch["stores"][0]
    line = store["lines"][0]
    recorded, finish = threading.Event(), threading.Event()
    save = dashboard.save_store_shipment

    def paused_shipment(*args, **kwargs):
        result = save(*args, **kwargs)
        recorded.set()
        assert finish.wait(10)
        return result

    monkeypatch.setattr(dashboard, "save_store_shipment", paused_shipment)
    monkeypatch.setattr(dashboard, "_session", lambda request, mutate=False: ({"driver_id": DRIVER["id"]}, None))
    monkeypatch.setattr(dashboard, "_mileage_required_response", lambda session, assignment=None: None)
    client = TestClient(custom_api)
    with ThreadPoolExecutor(max_workers=2) as pool:
        response = pool.submit(client.post, f"/api/driver/order/stores/{store['store_id']}/complete", json={
            "assignment_id": batch["assignment_id"], "base_revision": 0, "operation_id": "backup-write",
            "measurements": {line["line_id"]: _weight(8)},
        })
        try:
            assert recorded.wait(10)
            archived = pool.submit(backup.create_backup, tmp_path / "archives", tmp_path)
        finally:
            finish.set()
        assert response.result(timeout=15).status_code == 200
        archive = archived.result(timeout=15)
    with zipfile.ZipFile(archive.path) as zipped:
        record_state = json.loads(zipped.read("data/order_records.json"))["records"][0]
        snapshot_state = json.loads(zipped.read(f"data/driver_orders/{batch['assignment_id']}.json"))
    assert record_state["routes"][0]["destinations"][0]["positions"][0]["shipment"]["status"] == "completed"
    assert snapshot_state["stores"][0]["status"] == "completed"


def test_partial_backup_restores_sidecars_and_removes_newer_batches(route, tmp_path):
    order_id, _ = route
    _confirm(order_id, 0, 8)
    _confirm(order_id, 1, 4)
    first = _release(order_id)
    first = _ship(order_id, first, 0, 8, "backup-ship-1")
    first = _ship(order_id, first, 1, 4, "backup-ship-2")
    archived = backup.create_backup(tmp_path / "archives", project_root=tmp_path)
    assert backup.inspect_backup(archived.path).valid
    assert archived.file_count >= 4

    _confirm(order_id, 2, 2)
    second = _release(order_id, "later-release")
    assert len(order_records.loading_batches(_record(order_id), "route_4")) == 2
    assert driver_orders.find_assignment_for_driver(DRIVER["id"])["assignment_id"] == second["assignment_id"]

    backup.restore_backup(archived.path, project_root=tmp_path, safety_backup=False)
    assert len(order_records.loading_batches(_record(order_id), "route_4")) == 1
    assert not driver_orders.sidecar_path(second["assignment_id"]).exists()
    assert driver_orders.load_snapshot(first["assignment_id"])["stores"] == first["stores"]
    assert driver_orders.find_assignment_for_driver(DRIVER["id"])["assignment_id"] == first["assignment_id"]
    assert driver_orders.completed_delivery_report()["completed_stores"] == 2
    assert order_records.logistics_summary(_record(order_id))["total_loaded_net_kg"] == "12"


def test_missing_published_sidecar_repairs_only_before_any_shipment(route):
    order_id, _ = route
    _confirm(order_id, 0, 8)
    snapshot = _release(order_id)
    path = driver_orders.sidecar_path(snapshot["assignment_id"])
    original = path.read_bytes()
    path.unlink()
    assert not driver_orders.loading_batch_published(order_records.loading_batches(_record(order_id), "route_4")[0])
    restored = _release(order_id, "new-ui-attempt")
    assert restored == snapshot
    assert path.read_bytes() == original
    completed = _ship(order_id, restored, 0, 8, "ship-before-loss")
    path.unlink()
    with pytest.raises(driver_orders.DriverOrderConflict, match="восстановите"):
        _release(order_id)
    assert len(order_records.loading_batches(_record(order_id), "route_4")) == 1
    assert _store(order_id, 0)["positions"][0]["shipment"]["status"] == "completed"


def test_retry_after_assignment_write_failure_uses_same_batch(route, monkeypatch):
    order_id, source = route
    _confirm(order_id, 0, 8)
    original_write = driver_orders._atomic_write
    failed = False

    def fail_sidecar(path, payload):
        nonlocal failed
        if path != driver_orders.index_path() and payload.get("loading_batch_id") and not failed:
            failed = True
            raise driver_orders.DriverOrderError("Назначение временно недоступно")
        return original_write(path, payload)

    monkeypatch.setattr(driver_orders, "_atomic_write", fail_sidecar)
    with pytest.raises(driver_orders.DriverOrderError, match="Назначение временно"):
        _release(order_id)
    batch = order_records.loading_batches(_record(order_id), "route_4")[0]
    assert not driver_orders.loading_batch_published(batch)
    assert driver_orders.find_assignment_for_driver(DRIVER["id"])["assignment_id"] == source["assignment_id"]
    monkeypatch.setattr(driver_orders, "_atomic_write", original_write)
    repaired = _release(order_id, "new-ui-attempt")
    assert repaired["loading_batch_id"] == batch["id"]
    assert len(order_records.loading_batches(_record(order_id), "route_4")) == 1


def test_retries_failed_publication_without_duplicate_batch(route, monkeypatch):
    order_id, _ = route
    _confirm(order_id, 0, 8)
    original_write = driver_orders._atomic_write
    index_file = driver_orders.index_path()
    failed = False

    def fail_index(path, payload):
        nonlocal failed
        if path == index_file and not failed:
            failed = True
            raise driver_orders.DriverOrderError("Индекс временно недоступен")
        return original_write(path, payload)

    monkeypatch.setattr(driver_orders, "_atomic_write", fail_index)
    with pytest.raises(driver_orders.DriverOrderError, match="Индекс временно"):
        _release(order_id)
    record = _record(order_id)
    assert len(order_records.loading_batches(record, "route_4")) == 1
    monkeypatch.setattr(driver_orders, "_atomic_write", original_write)
    recovered = _release(order_id, "retry-after-failure")
    assert len(order_records.loading_batches(_record(order_id), "route_4")) == 1
    assert driver_orders.loading_batch_published(order_records.loading_batches(_record(order_id), "route_4")[0])
    assert recovered["loading_batch_id"] == order_records.loading_batches(record, "route_4")[0]["id"]
