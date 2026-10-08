from concurrent.futures import ThreadPoolExecutor
from copy import deepcopy
from decimal import Decimal
import json
import threading

import pytest
from openpyxl import Workbook

from modules import goods_returns as returns, order_records, paths


DRIVER = {"kind": "driver", "id": "driver-1", "name": "Иван"}
ADMIN = {"kind": "dashboard", "id": "admin", "name": "Администратор"}


def measurement(gross, boxes="0", tare="0"):
    return {"box_count": boxes, "tare_weight_per_box_kg": tare, "gross_weight_kg": str(gross)}


def assignment_from_record(record, route_key="route_1", driver_id="driver-1"):
    route = next(route for route in record["routes"] if route["route_key"] == route_key)
    return {
        "assignment_id": "assignment-" + route_key, "driver_id": driver_id, "driver_name": "Иван",
        "order_record_id": record["id"], "route_key": route_key, "route_label": route["route_label"],
        "vehicle_plate": "А123АА", "source_file": "C:/private/order.xlsx", "output_file": "C:/private/output.xlsx",
        "snapshot_path": "C:/private/snapshot.json",
        "stores": [{
            "store_id": "store-" + destination["id"], "name": destination["name"],
            "order_record_destination_id": destination["id"],
            "status": "completed" if all(p["shipment"]["status"] == "completed" for p in destination["positions"]) else "pending",
            "lines": [{
                "line_id": "line-" + position["id"], "name": position["name"],
                "order_record_position_id": position["id"], "loading_line_id": position["loading_line_id"],
                "actual_qty": position["shipment"]["measurement"]["net_weight_kg"],
            } for position in destination["positions"]],
        } for destination in route["destinations"]],
    }


@pytest.fixture
def trip(tmp_path, monkeypatch):
    root = tmp_path / "processed"
    output = root / "07.10.26" / "order.xlsx"
    output.parent.mkdir(parents=True)
    workbook = Workbook()
    one = workbook.active
    one.title = "Маршрут №1"
    one.append(["Товар", "Сумма", "ФМ 10", "ФМ 14"])
    one.append(["Томаты", "", 60, 40])
    one.append(["Огурцы", "", 20, 20])
    two = workbook.create_sheet("Маршрут №2")
    two.append(["Товар", "Сумма", "ФМ 20"])
    two.append(["Томаты", "", 50])
    two.append(["Огурцы", "", 10])
    workbook.save(output)
    workbook.close()
    monkeypatch.setattr(paths, "PROCESSED_FOLDER", root)
    monkeypatch.setattr(paths, "ORDER_RECORDS_FILE", tmp_path / "orders.json")
    monkeypatch.setattr(paths, "GOODS_RETURNS_FILE", tmp_path / "goods_returns.json")
    record = order_records.create_processed_order_record(output, "№42.xlsx", "Клиент", "Область")
    loaded = {"route_1": {"Томаты": "95", "Огурцы": "40"}, "route_2": {"Томаты": "50", "Огурцы": "10"}}
    for route in record["routes"]:
        route_key = route["route_key"]
        for line in record["loading_lines"]:
            if line["route_key"] != route_key:
                continue
            for field, value in measurement(loaded[route_key][line["name"]]).items():
                record = order_records.save_loading_draft(record["id"], route_key, line["id"], field, value, {"kind": "loader"})
        record = order_records.confirm_route_loading(record["id"], record["revision"], route_key, {"kind": "loader"})
    for route in record["routes"]:
        for destination in route["destinations"]:
            values = {}
            for position in destination["positions"]:
                if route["route_key"] == "route_1":
                    factor = Decimal("0.9") if position["name"] == "Томаты" else Decimal("0.95")
                    gross = Decimal(position["planned_amount"]) * factor
                else:
                    gross = "47" if position["name"] == "Томаты" else "8"
                values[position["id"]] = measurement(gross)
            record = order_records.save_store_shipment(record["id"], route["route_key"], destination["id"], values,
                                                       "ship-" + destination["id"], DRIVER)
    return assignment_from_record(record)


def record_for(trip):
    return order_records.load_order_record(trip["order_record_id"])


def change_record(change):
    payload = json.loads(paths.ORDER_RECORDS_FILE.read_text(encoding="utf-8"))
    record = payload["records"][0]
    change(record)
    record["revision"] += 1
    paths.ORDER_RECORDS_FILE.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
    return record


def payload_for(trip, gross="5", product="Томаты", operation="op-1", revision=None):
    context = returns.return_context(trip)
    line = next(line for line in context["lines"] if line["name"] == product)
    if revision is None:
        revision = context["document"]["revision"] if context["document"] else 0
    return {"operation_id": operation, "base_revision": revision, "facts_token": context["facts_token"],
            "lines": {line["loading_line_id"]: {**measurement(gross), "reason": returns.RETURN_REASONS[0], "comment": ""}}}


def test_lifecycle_uses_loaded_not_ordered_and_never_changes_original(trip):
    original = paths.ORDER_RECORDS_FILE.read_bytes()
    summary = order_records.logistics_summary(record_for(trip))
    context = returns.return_context(trip)
    assert context["eligible"] and context["complete"] and context["loading_ready"]
    tomato = next(line for line in context["lines"] if line["name"] == "Томаты")
    assert (tomato["planned_kg"], tomato["loaded_net_kg"], tomato["shipped_net_kg"], tomato["available_net_kg"]) == ("100", "95", "90", "5")
    with pytest.raises(returns.GoodsReturnError, match="остаток"):
        returns.submit_return(trip, payload_for(trip, "10"), DRIVER)
    submitted = returns.submit_return(trip, payload_for(trip), DRIVER)
    assert (submitted["status"], submitted["revision"], submitted["version"], submitted["total_net_kg"]) == ("submitted", 1, 1, "5")
    assert returns.accepted_by_loading_line(trip["order_record_id"]) == {}
    accepted = returns.decide_return(submitted["id"], 1, "accepted", "Получено", ADMIN)
    assert accepted["status"] == "accepted" and accepted["revision"] == 2
    assert returns.accepted_by_loading_line(trip["order_record_id"]) == {tomato["loading_line_id"]: "5"}
    assert returns.return_context(trip)["document"] == accepted
    assert not returns.return_context(trip)["eligible"]
    assert paths.ORDER_RECORDS_FILE.read_bytes() == original
    assert order_records.logistics_summary(record_for(trip)) == summary
    assert [entry["kind"] for entry in accepted["history"]] == ["submitted", "accepted"]
    assert accepted["history"][-1]["actor"] == ADMIN
    with pytest.raises(returns.GoodsReturnConflict):
        returns.decide_return(accepted["id"], 2, "rejected", "Нет", ADMIN)
    with pytest.raises(returns.GoodsReturnConflict):
        returns.submit_return(trip, payload_for(trip, operation="new-operation"), DRIVER)


def test_partial_return_and_decimal_measurement(trip):
    payload = payload_for(trip, "4.2")
    value = next(iter(payload["lines"].values()))
    value.update(box_count="2", tare_weight_per_box_kg="0,6")
    document = returns.submit_return(trip, payload, DRIVER)
    assert document["total_net_kg"] == "3"
    assert document["lines"][0]["measurement"]["tare_weight_per_box_kg"] == "0.6"
    accepted = returns.decide_return(document["id"], 1, "accepted", "", ADMIN)
    assert accepted["lines"][0]["loaded_net_kg"] == "95"
    assert Decimal("95") - Decimal("90") - Decimal(accepted["total_net_kg"]) == Decimal("2")


def test_retry_is_immutable_even_after_decision_and_conflict_precedes_revision(trip):
    payload = payload_for(trip)
    initial = returns.submit_return(trip, payload, DRIVER)
    assert returns.submit_return(trip, payload, DRIVER) == initial
    decided = returns.decide_return(initial["id"], 1, "accepted", "", ADMIN)
    assert returns.submit_return(trip, payload, DRIVER) == initial
    altered = deepcopy(payload)
    altered["base_revision"] = 999
    next(iter(altered["lines"].values()))["gross_weight_kg"] = "4"
    with pytest.raises(returns.GoodsReturnConflict, match="другими данными"):
        returns.submit_return(trip, altered, DRIVER)
    initial["lines"].clear()
    assert returns.list_returns() == [decided]
    assert returns.submit_return(trip, payload, DRIVER)["lines"]


def test_rejected_resubmit_preserves_versions_and_counts_only_accepted(trip):
    old_payload = payload_for(trip)
    initial = returns.submit_return(trip, old_payload, DRIVER)
    rejected = returns.decide_return(initial["id"], 1, "rejected", "Получено меньше", ADMIN)
    assert returns.accepted_by_loading_line(trip["order_record_id"]) == {}
    assert returns.return_context(trip)["eligible"]
    assert returns.submit_return(trip, old_payload, DRIVER) == initial
    assert returns.list_returns() == [rejected]
    corrected = returns.submit_return(trip, payload_for(trip, "4", operation="op-2"), DRIVER)
    assert (corrected["id"], corrected["version"], corrected["revision"]) == (initial["id"], 2, 3)
    with pytest.raises(returns.GoodsReturnConflict):
        returns.decide_return(corrected["id"], 1, "accepted", "", ADMIN)
    accepted = returns.decide_return(corrected["id"], 3, "accepted", "", ADMIN)
    assert [item["kind"] for item in accepted["history"]] == ["submitted", "rejected", "submitted", "accepted"]
    assert accepted["history"][0]["total_net_kg"] == "5"
    assert accepted["history"][2]["total_net_kg"] == "4"
    assert len(returns.list_returns()) == 1
    assert list(returns.accepted_by_loading_line(trip["order_record_id"]).values()) == ["4"]
    assert returns.submit_return(trip, old_payload, DRIVER) == initial


@pytest.mark.parametrize("field,value", [
    ("gross_weight_kg", "NaN"), ("gross_weight_kg", "Infinity"), ("gross_weight_kg", "-1"),
    ("gross_weight_kg", "1e1000000"), ("gross_weight_kg", "1e-1000000"), ("gross_weight_kg", "0e1000000"),
    ("gross_weight_kg", "1000000001"), ("gross_weight_kg", "0.1234567891234567891"),
    ("gross_weight_kg", ""), ("gross_weight_kg", None), ("gross_weight_kg", True),
    ("gross_weight_kg", "0"), ("gross_weight_kg", "6"),
    ("tare_weight_per_box_kg", "-1"), ("tare_weight_per_box_kg", "NaN"),
    ("box_count", "1.5"), ("box_count", "-1"), ("box_count", "1e999"),
    ("reason", ""), ("reason", "unknown"), ("reason", "Другое"),
    ("comment", "x" * 2001), ("comment", 42),
])
def test_invalid_line_values_are_rejected_without_writing(trip, field, value):
    payload = payload_for(trip)
    next(iter(payload["lines"].values()))[field] = value
    with pytest.raises(returns.GoodsReturnError):
        returns.submit_return(trip, payload, DRIVER)
    assert not paths.GOODS_RETURNS_FILE.exists()


def test_tare_exceeding_gross_empty_foreign_and_incomplete_lines_rejected(trip):
    payload = payload_for(trip)
    value = next(iter(payload["lines"].values()))
    value.update(box_count="3", tare_weight_per_box_kg="2")
    with pytest.raises(returns.GoodsReturnError, match="тары"):
        returns.submit_return(trip, payload, DRIVER)
    for lines in ({}, [], {"foreign": value}, {next(iter(payload["lines"])): {"reason": "Отказ магазина"}}):
        invalid = {**payload, "lines": lines}
        with pytest.raises(returns.GoodsReturnError):
            returns.submit_return(trip, invalid, DRIVER)


def test_other_reason_needs_comment_and_two_products_do_not_offset(trip):
    payload = payload_for(trip, "4")
    value = next(iter(payload["lines"].values()))
    value.update(reason="Другое", comment="   ")
    with pytest.raises(returns.GoodsReturnError, match="комментарий"):
        returns.submit_return(trip, payload, DRIVER)
    value["comment"] = "Повторное взвешивание"
    cucumber = payload_for(trip, "3", product="Огурцы")["lines"]
    payload["lines"].update(cucumber)
    with pytest.raises(returns.GoodsReturnError, match="остаток"):
        returns.submit_return(trip, payload, DRIVER)
    next(iter(cucumber.values()))["gross_weight_kg"] = "2"
    document = returns.submit_return(trip, payload, DRIVER)
    assert document["total_net_kg"] == "6" and len(document["lines"]) == 2


def test_negative_balance_is_visible_and_cannot_be_offset(trip):
    def overdeliver(record):
        position = next(p for p in record["routes"][0]["destinations"][0]["positions"] if p["name"] == "Огурцы")
        position["shipment"]["measurement"].update(gross_weight_kg="25", net_weight_kg="25")
    record = change_record(overdeliver)
    assignment = assignment_from_record(record)
    context = returns.return_context(assignment)
    cucumber = next(line for line in context["lines"] if line["name"] == "Огурцы")
    assert cucumber["available_net_kg"] == "-4"
    with pytest.raises(returns.GoodsReturnError, match="остаток"):
        returns.submit_return(assignment, payload_for(assignment, "1", product="Огурцы"), DRIVER)
    assert returns.submit_return(assignment, payload_for(assignment), DRIVER)["total_net_kg"] == "5"


def test_pending_route_exposes_loaded_facts_for_offline_cache_but_cannot_submit(trip):
    def pending(record):
        for destination in record["routes"][0]["destinations"]:
            for position in destination["positions"]:
                position["shipment"]["status"] = "pending"
    record = change_record(pending)
    assignment = assignment_from_record(record)
    context = returns.return_context(assignment)
    assert not context["complete"] and not context["eligible"]
    assert context["loading_ready"] and context["lines"] and context["facts_token"]
    assert next(line for line in context["lines"] if line["name"] == "Томаты")["loaded_net_kg"] == "95"
    with pytest.raises(returns.GoodsReturnConflict):
        returns.submit_return(assignment, payload_for(assignment), DRIVER)


@pytest.mark.parametrize("fault", ["destination", "position", "loading_line", "actual", "pending_snapshot", "missing_store", "duplicate_store", "missing_position", "duplicate_position", "pending_canonical"])
def test_snapshot_and_canonical_must_match_exactly(trip, fault):
    assignment = deepcopy(trip)
    store = assignment["stores"][0]
    line = store["lines"][0]
    if fault == "destination":
        store["order_record_destination_id"] = "foreign"
    elif fault == "position":
        line["order_record_position_id"] = assignment["stores"][1]["lines"][0]["order_record_position_id"]
    elif fault == "loading_line":
        line["loading_line_id"] = "foreign"
    elif fault == "actual":
        line["actual_qty"] = "999"
    elif fault == "pending_snapshot":
        store["status"] = "pending"
    elif fault == "missing_store":
        assignment["stores"].pop()
    elif fault == "duplicate_store":
        assignment["stores"][1] = deepcopy(store)
    elif fault == "missing_position":
        store["lines"].pop()
    elif fault == "duplicate_position":
        store["lines"][1] = deepcopy(line)
    else:
        change_record(lambda record: record["routes"][0]["destinations"][0]["positions"][0]["shipment"].update(status="pending"))
    context = returns.return_context(assignment)
    assert not context["eligible"] and not context["complete"] and context["error"]
    assert context["loading_ready"] and context["lines"]
    with pytest.raises(returns.GoodsReturnConflict):
        returns.submit_return(assignment, payload_for(assignment), DRIVER)


@pytest.mark.parametrize("fault", ["missing_link", "missing_record", "unconfirmed", "legacy_loading", "missing_net", "bad_net", "huge_net"])
def test_unreliable_records_block_returns_with_safe_context(trip, fault):
    assignment = deepcopy(trip)
    if fault == "missing_link":
        assignment["order_record_id"] = ""
    elif fault == "missing_record":
        assignment["order_record_id"] = "absent"
    else:
        def mutate(record):
            line = next(line for line in record["loading_lines"] if line["route_key"] == "route_1")
            if fault == "unconfirmed":
                record["loading"]["route_states"]["route_1"]["status"] = "draft"
            elif fault == "legacy_loading":
                for item in record["loading_lines"]:
                    item.pop("route_key", None)
            elif fault == "missing_net":
                line["measurement"]["net_weight_kg"] = ""
            elif fault == "bad_net":
                line["measurement"]["net_weight_kg"] = "1"
            else:
                line["measurement"]["net_weight_kg"] = "1e99999"
        change_record(mutate)
    context = returns.return_context(assignment)
    assert not context["eligible"] and not context["loading_ready"] and context["error"]
    public = json.dumps(context, ensure_ascii=False)
    assert "C:/private" not in public and "snapshot_path" not in public and "output_file" not in public


def test_facts_token_ignores_other_route_but_detects_own_changes(trip):
    payload = payload_for(trip)
    def other_route(record):
        record["loading_lines"][-1]["name"] = "Другой товар маршрута 2"
        record["routes"][1]["destinations"][0]["positions"][0]["shipment"]["completed_at"] = "changed"
    change_record(other_route)
    assert returns.return_context(trip)["facts_token"] == payload["facts_token"]
    returns.submit_return(trip, payload, DRIVER)
    document = returns.list_returns()[0]
    returns.decide_return(document["id"], 1, "rejected", "Уточнить", ADMIN)
    corrected = payload_for(trip, operation="op-2")
    def own_route(record):
        line = next(line for line in record["loading_lines"] if line["route_key"] == "route_1" and line["name"] == "Томаты")
        line["measurement"].update(gross_weight_kg="96", net_weight_kg="96")
    change_record(own_route)
    with pytest.raises(returns.GoodsReturnConflict, match="изменились"):
        returns.submit_return(trip, corrected, DRIVER)


def test_distinct_routes_have_distinct_documents_and_balances(trip):
    first = returns.submit_return(trip, payload_for(trip), DRIVER)
    second_trip = assignment_from_record(record_for(trip), "route_2")
    second = returns.submit_return(second_trip, payload_for(second_trip, "3", operation="second-route"), DRIVER)
    assert first["id"] != second["id"]
    assert first["lines"][0]["loading_line_id"] != second["lines"][0]["loading_line_id"]
    for document in (first, second):
        returns.decide_return(document["id"], 1, "accepted", "", ADMIN)
    assert sorted(returns.accepted_by_loading_line(trip["order_record_id"]).values()) == ["3", "5"]
    assert returns.accepted_by_loading_line("other-order") == {}


@pytest.mark.parametrize("reassigned_driver", [False, True])
def test_republication_or_driver_change_cannot_take_over_return(trip, reassigned_driver):
    payload = payload_for(trip)
    document = returns.submit_return(trip, payload, DRIVER)
    returns.decide_return(document["id"], 1, "rejected", "Исправьте", ADMIN)
    replacement = deepcopy(trip)
    replacement["assignment_id"] = "new-assignment"
    if reassigned_driver:
        replacement["driver_id"] = "driver-2"
    actor = {**DRIVER, "id": replacement["driver_id"]}
    context = returns.return_context(replacement)
    assert context["document"] is None and not context["eligible"]
    with pytest.raises(returns.GoodsReturnConflict, match="другим назначением"):
        returns.submit_return(replacement, payload, actor)
    assert len(returns.list_returns()) == 1


@pytest.mark.parametrize("actor", [{}, {"kind": "driver", "id": "foreign"}, ADMIN, {"kind": "loader", "id": "driver-1"}])
def test_submission_requires_matching_driver_even_on_idempotent_replay(trip, actor):
    payload = payload_for(trip)
    returns.submit_return(trip, payload, DRIVER)
    with pytest.raises(returns.GoodsReturnError, match="доступа"):
        returns.submit_return(trip, payload, actor)


@pytest.mark.parametrize("actor", [DRIVER, {}, {"kind": "dashboard", "id": "other"}, {"kind": "loader", "id": "admin"}])
def test_decision_requires_admin(trip, actor):
    document = returns.submit_return(trip, payload_for(trip), DRIVER)
    with pytest.raises(returns.GoodsReturnError, match="доступа"):
        returns.decide_return(document["id"], 1, "accepted", "", actor)


def test_decision_validation_and_not_found(trip):
    document = returns.submit_return(trip, payload_for(trip), DRIVER)
    for revision, decision, comment in [(True, "accepted", ""), (1, "other", ""), (1, "rejected", " ")]:
        with pytest.raises(returns.GoodsReturnError):
            returns.decide_return(document["id"], revision, decision, comment, ADMIN)
    with pytest.raises(returns.GoodsReturnNotFound):
        returns.decide_return("missing", 1, "accepted", "", ADMIN)


def test_concurrent_identical_submissions_create_one_document(trip):
    payload = payload_for(trip)
    barrier = threading.Barrier(2)
    def submit():
        barrier.wait(timeout=10)
        return returns.submit_return(trip, payload, DRIVER)
    with ThreadPoolExecutor(max_workers=2) as executor:
        results = list(executor.map(lambda _: submit(), range(2)))
    assert results[0] == results[1]
    assert len(returns.list_returns()) == 1


def test_concurrent_distinct_submissions_cannot_duplicate_route(trip):
    payload = payload_for(trip)
    barrier = threading.Barrier(2)
    def submit(operation):
        barrier.wait(timeout=10)
        try:
            return returns.submit_return(trip, {**payload, "operation_id": operation}, DRIVER)["id"]
        except returns.GoodsReturnConflict:
            return "conflict"
    with ThreadPoolExecutor(max_workers=2) as executor:
        results = list(executor.map(submit, ["one", "two"]))
    assert results.count("conflict") == 1
    assert len(returns.list_returns()) == 1


def test_concurrent_decisions_cannot_overwrite_each_other(trip):
    document = returns.submit_return(trip, payload_for(trip), DRIVER)
    barrier = threading.Barrier(2)
    def decide(decision):
        barrier.wait(timeout=10)
        try:
            return returns.decide_return(document["id"], 1, decision, "Проверено", ADMIN)["status"]
        except returns.GoodsReturnConflict:
            return "conflict"
    with ThreadPoolExecutor(max_workers=2) as executor:
        results = list(executor.map(decide, ["accepted", "rejected"]))
    assert results.count("conflict") == 1
    assert len(returns.list_returns()[0]["history"]) == 2


def test_failed_atomic_write_preserves_previous_ledger(trip, monkeypatch):
    document = returns.submit_return(trip, payload_for(trip), DRIVER)
    original = paths.GOODS_RETURNS_FILE.read_bytes()
    def fail_replace(*args):
        raise OSError("private/path should not be exposed")
    monkeypatch.setattr(returns.os, "replace", fail_replace)
    with pytest.raises(returns.GoodsReturnError, match="сохранить") as error:
        returns.decide_return(document["id"], 1, "accepted", "", ADMIN)
    assert "private/path" not in str(error.value)
    assert paths.GOODS_RETURNS_FILE.read_bytes() == original
    assert not list(paths.GOODS_RETURNS_FILE.parent.glob(".goods_returns.json.*.tmp"))


def test_corrupt_ledger_fails_closed(trip):
    paths.GOODS_RETURNS_FILE.write_text("{broken", encoding="utf-8")
    with pytest.raises(returns.GoodsReturnError, match="прочитать"):
        returns.list_returns()
    assert paths.GOODS_RETURNS_FILE.read_text(encoding="utf-8") == "{broken"
