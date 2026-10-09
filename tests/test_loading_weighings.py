from copy import deepcopy
from decimal import Decimal

import pytest

from modules import goods_returns, order_records as records
import orders_dashboard.loading_page as page
from test_store_loading import ACTOR, record, choose, destinations, fill, confirm, ui_state


def context(record, stores):
    if stores:
        destination = destinations(record)[0]
        return destination['id'], destination['positions'][0]['id']
    return '', record['loading_lines'][0]['id']


def measurement(record, destination_id, position_id):
    if destination_id:
        destination = next(d for d in destinations(record) if d['id'] == destination_id)
        return next(p for p in destination['positions'] if p['id'] == position_id)['loading']['measurement']
    return next(line for line in record['loading_lines'] if line['id'] == position_id)['measurement']


def save(record, dest, pos, weighing_id, boxes, tare, gross):
    for field, value in [('box_count', boxes), ('tare_weight_per_box_kg', tare), ('gross_weight_kg', gross)]:
        if dest:
            record = records.save_store_loading_draft(record['id'], 'route_4', dest, pos, field, value, ACTOR, weighing_id)
        else:
            record = records.save_loading_draft(record['id'], 'route_4', pos, field, value, ACTOR, weighing_id)
    return record


def change(record, dest, pos, remove_id=None):
    return records.change_loading_weighing(record['id'], record['revision'], 'route_4', dest, pos, ACTOR, remove_id)


@pytest.mark.parametrize('stores', [False, True])
def test_different_tare_and_decimal_sum_with_confirmation(record, stores):
    if stores:
        record = choose(record)
    dest, pos = context(record, stores)
    record = save(record, dest, pos, '', '3', '0,4', '15')
    assert 'weighings' not in measurement(record, dest, pos)
    record = change(record, dest, pos)
    parts = measurement(record, dest, pos)['weighings']
    assert parts[0]['net_weight_kg'] == '13.8'
    assert not measurement(record, dest, pos)['net_weight_kg']
    with pytest.raises(records.OrderRecordError):
        if stores:
            records.confirm_store_loading(record['id'], record['revision'], 'route_4', dest, ACTOR)
        else:
            records.confirm_route_loading(record['id'], record['revision'], 'route_4', ACTOR)
    record = save(record, dest, pos, parts[1]['id'], '2', '0.6', '10')
    total = measurement(record, dest, pos)
    assert (total['box_count'], total['gross_weight_kg'], total['total_tare_weight_kg'], total['net_weight_kg']) == ('5', '25', '2.4', '22.6')
    assert total['tare_weight_per_box_kg'] == ''
    assert records.load_order_record(record['id'])['revision'] == record['revision']
    if stores:
        record = records.confirm_store_loading(record['id'], record['revision'], 'route_4', dest, ACTOR)
        assert not records.route_loading_ready(record, 'route_4')
        other = destinations(record)[1]
        record = confirm(fill(record, other, '0', '0', '1'), other)
    else:
        record = records.confirm_route_loading(record['id'], record['revision'], 'route_4', ACTOR)
    assert records.route_loading_ready(record, 'route_4')
    expected = Decimal('23.6') if stores else Decimal('22.6')
    assert records.loading_line_net_weight(record, record['loading_lines'][0]) == expected
    assert Decimal(records.route_return_balance(record, 'route_4')['lines'][0]['loaded_net_kg']) == expected
    with pytest.raises(records.OrderRecordConflict):
        change(record, dest, pos)
    with pytest.raises(records.OrderRecordConflict):
        save(record, dest, pos, parts[0]['id'], '1', '0', '1')


@pytest.mark.parametrize('stores', [False, True])
def test_remove_stale_unknown_and_scalar_requests_are_atomic(record, stores):
    if stores:
        record = choose(record)
    dest, pos = context(record, stores)
    record = save(record, dest, pos, '', '3', '0.4', '15')
    stale = record['revision']
    record = change(record, dest, pos)
    parts = measurement(record, dest, pos)['weighings']
    for portion_id in ['', 'unknown']:
        with pytest.raises(records.OrderRecordConflict):
            save(record, dest, pos, portion_id, '2', '0.6', '10')
    with pytest.raises(records.OrderRecordConflict):
        records.change_loading_weighing(record['id'], stale, 'route_4', dest, pos, ACTOR)
    with pytest.raises(records.OrderRecordConflict):
        change(record, dest, pos, 'unknown')
    assert records.load_order_record(record['id']) == record
    record = change(record, dest, pos, parts[1]['id'])
    assert measurement(record, dest, pos)['net_weight_kg'] == '13.8'
    assert measurement(record, dest, pos)['weighings'][0]['id'] == parts[0]['id']
    with pytest.raises(records.OrderRecordError):
        change(record, dest, pos, parts[0]['id'])
    with pytest.raises(records.OrderRecordConflict):
        save(record, dest, pos, parts[1]['id'], '1', '0', '1')


def test_zero_portion_requires_own_reason_and_tampered_total_rejected(record):
    dest, pos = context(record, False)
    record = save(record, dest, pos, '', '3', '0.4', '15')
    record = change(record, dest, pos)
    part_id = measurement(record, dest, pos)['weighings'][1]['id']
    record = save(record, dest, pos, part_id, '0', '0', '0')
    with pytest.raises(records.OrderRecordError):
        records.confirm_route_loading(record['id'], record['revision'], 'route_4', ACTOR)
    record = records.save_loading_draft(record['id'], 'route_4', pos, 'zero_reason', records.ZERO_REASON_OPTIONS[0], ACTOR, part_id)
    record = records.confirm_route_loading(record['id'], record['revision'], 'route_4', ACTOR)
    assert records.route_loading_ready(record, 'route_4')
    corrupt = deepcopy(record)
    measurement(corrupt, dest, pos)['net_weight_kg'] = '99'
    assert not records.route_loading_ready(corrupt, 'route_4')
    with pytest.raises(records.OrderRecordError):
        records.route_return_balance(corrupt, 'route_4')


def test_multi_weighing_autosave_keeps_input_buffer(record):
    record = choose(record)
    dest, pos = context(record, True)
    record = save(record, dest, pos, '', '3', '0.4', '15')
    record = change(record, dest, pos)
    part_id = measurement(record, dest, pos)['weighings'][1]['id']
    record = save(record, dest, pos, part_id, '2', '0.6', '10')
    state = ui_state(record)
    page.LoadingState._apply_record(state, record['id'], 'route_4')
    old = deepcopy(state.loading_rows[0]['weighings'])
    page.LoadingState.set_context_measurement_field.fn(state, record['id'], 'route_4', dest, pos, 'gross_weight_kg', '11,5', part_id)
    assert state.loading_rows[0]['preview_net_weight_kg'] == '24.1'
    assert state.loading_rows[0]['weighings'][1]['gross_weight_kg'] == old[1]['gross_weight_kg']
    assert state.loading_rows[0]['weighings'][1]['preview_net_weight_kg'] == '10.3'
    assert state.loading_rows[0]['weighings'][0] == old[0]


def test_structural_click_uses_flushed_revision_and_deduplicates(record):
    state = ui_state(record)
    state._last_weighing_request = ""
    dest, pos = context(record, False)
    captured = record["revision"]
    page.LoadingState.set_context_measurement_field.fn(state, record["id"], "route_4", dest, pos, "gross_weight_kg", "1,5")
    assert state.selected_record["revision"] > captured
    page.LoadingState.change_context_weighing.fn(state, record["id"], "route_4", dest, pos, captured, "")
    current = state.selected_record
    assert measurement(current, dest, pos)["weighings"][0]["gross_weight_kg"] == "1.5"
    page.LoadingState.change_context_weighing.fn(state, record["id"], "route_4", dest, pos, captured, "")
    assert state.selected_record == current
    assert len(measurement(records.load_order_record(record["id"]), dest, pos)["weighings"]) == 2


def test_multi_loading_return_submission_and_acceptance(record):
    record = choose(record)
    dest, pos = context(record, True)
    record = save(record, dest, pos, "", "3", "0.4", "15")
    record = change(record, dest, pos)
    part_id = measurement(record, dest, pos)["weighings"][1]["id"]
    record = save(record, dest, pos, part_id, "2", "0.6", "10")
    record = records.confirm_store_loading(record["id"], record["revision"], "route_4", dest, ACTOR)
    other = destinations(record)[1]
    record = confirm(fill(record, other, "0", "0", "1"), other)
    for destination, gross in zip(destinations(record), ("20", "1")):
        record = records.save_store_shipment(record["id"], "route_4", destination["id"], {
            destination["positions"][0]["id"]: {"box_count": "0", "tare_weight_per_box_kg": "0", "gross_weight_kg": gross},
        }, "weighing-shipment-" + destination["id"], {"kind": "driver", "id": "driver-test"})
    route = record["routes"][0]
    assignment = {
        "assignment_id": "multi-weighing-trip", "driver_id": "driver-test",
        "order_record_id": record["id"], "route_key": "route_4", "route_label": route["route_label"],
        "stores": [{
            "store_id": "store-" + destination["id"], "name": destination["name"],
            "order_record_destination_id": destination["id"], "status": "completed",
            "lines": [{"line_id": "line-" + position["id"], "name": position["name"],
                       "order_record_position_id": position["id"], "loading_line_id": position["loading_line_id"],
                       "actual_qty": position["shipment"]["measurement"]["net_weight_kg"]}
                      for position in destination["positions"]],
        } for destination in route["destinations"]],
    }
    balance = records.route_return_balance(record, "route_4")
    assert balance["lines"][0]["available_net_kg"] == "2.6"
    context_data = goods_returns.return_context(assignment)
    document = goods_returns.submit_return(assignment, {
        "operation_id": "multi-weighing-return", "base_revision": 0, "facts_token": context_data["facts_token"],
        "lines": {balance["lines"][0]["loading_line_id"]: {"box_count": "0", "tare_weight_per_box_kg": "0", "gross_weight_kg": "2,6", "reason": goods_returns.RETURN_REASONS[0], "comment": ""}},
    }, {"kind": "driver", "id": "driver-test"})
    goods_returns.decide_return(document["id"], document["revision"], "accepted", "", {"kind": "dashboard", "id": "admin"})
    reconciliation = page._return_reconciliation(record)
    assert reconciliation["total_returned_kg"] == "2.6"
    assert reconciliation["total_unexplained_kg"] == "0"


@pytest.mark.parametrize("field,value", [("box_count", "1.5"), ("gross_weight_kg", "-1"), ("tare_weight_per_box_kg", "invalid")])
def test_invalid_portion_does_not_change_confirmed_or_other_data(record, field, value):
    dest, pos = context(record, False)
    record = save(record, dest, pos, "", "3", "0.4", "15")
    record = change(record, dest, pos)
    part_id = measurement(record, dest, pos)["weighings"][1]["id"]
    before = deepcopy(record)
    try:
        record = records.save_loading_draft(record["id"], "route_4", pos, field, value, ACTOR, part_id)
    except records.OrderRecordError:
        assert records.load_order_record(record["id"]) == before
        return
    with pytest.raises(records.OrderRecordError):
        records.confirm_route_loading(record["id"], record["revision"], "route_4", ACTOR)
    assert measurement(record, dest, pos)["weighings"][0] == measurement(before, dest, pos)["weighings"][0]
