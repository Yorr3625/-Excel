from copy import deepcopy
import uuid

import pytest

from modules import paths, driver_orders, order_records as records, vehicle_trips as trips
from test_store_loading import record, ACTOR

ADMIN = {'kind': 'dashboard', 'id': 'admin', 'name': 'Администратор'}
DRIVER = {'kind': 'driver', 'id': 'driver', 'name': 'Водитель'}


def op():
    return uuid.uuid4().hex


@pytest.fixture
def assignments(record, tmp_path, monkeypatch, request):
    monkeypatch.setattr(trips, '_fleet_available', lambda snapshot: True)
    monkeypatch.setattr(paths, 'VEHICLE_TRIPS_FILE', tmp_path / 'vehicle_trips.sqlite3')
    monkeypatch.setattr(paths, 'DRIVER_ORDERS_FOLDER', tmp_path / 'driver_orders')
    for mode, filename in [('Город', 'city.json'), ('Область', 'region.json')]:
        target = tmp_path / filename
        target.write_text('{"route_1": ["Магазин Г"]}', encoding='utf8')
        monkeypatch.setattr(paths, 'STORES_CITY_FILE' if mode == 'Город' else 'STORES_REGION_FILE', target)
    for line in record['loading_lines']:
        for field, value in [('box_count', '0'), ('tare_weight_per_box_kg', '0'), ('gross_weight_kg', getattr(request, 'param', {}).get(line['route_key'], '100' if line['route_key'] == 'route_4' else '20'))]:
            record = records.save_loading_draft(record['id'], line['route_key'], line['id'], field, value, ACTOR)
        record = records.confirm_route_loading(record['id'], record['revision'], line['route_key'], ACTOR)
    output = paths.PROCESSED_FOLDER / '09.10.26' / 'заказ.xlsx'
    snapshots = []
    for route in ('route_4', 'route_5'):
        snapshot = driver_orders.build_assignment_snapshot(output, 'Область', {
            'route': route, 'label': route, 'driver_id': 'driver', 'driver_name': 'Водитель',
            'vehicle_id': 'vehicle', 'vehicle_name': 'Машина', 'vehicle_plate': 'TEST',
        }, order_record=record)
        driver_orders.save_snapshot(snapshot)
        snapshots.append(snapshot)
    return snapshots


def start(assignments):
    trip = trips.create_trip([item['assignment_id'] for item in assignments], '2026-10-10', ADMIN, op())
    return trips.start_trip(trip['id'], trip['revision'], ADMIN, op())


def accept(trip, stop, amount, reason='Отказ магазина', operation_id=None):
    return trips.complete_stop(trip['id'], stop['id'], {
        'operation_id': operation_id or op(), 'base_revision': stop['revision'],
        'measurements': {line['id']: {'kind': 'net', 'net_weight_kg': amount} for line in stop['lines']},
        'reasons': {line['id']: {'reason': reason, 'comment': 'Тест'} for line in stop['lines']},
    }, DRIVER)


def finish(trip):
    for stop in trip['stops']:
        if stop['status'] == 'pending':
            trip = accept(trip, stop, '0')
    return trip


def test_two_routes_stock_reservations_and_no_automatic_merge(assignments):
    assert trips.list_trips() == []
    trip = start(assignments)
    assert len(trip['members']) == 2
    assert len(trip['stops']) == 3
    stock = trips.stock(trip)[0]
    assert (stock['remaining_kg'], stock['reserved_kg'], stock['available_kg']) == ('120', '14', '106')
    dto = trips.as_assignment(trip)
    assert len(dto['stores']) == 3
    assert dto['trip_id'] == trip['id']
    with pytest.raises(trips.TripConflict):
        trips.create_trip([assignments[0]['assignment_id']], '2026-10-10', ADMIN, op())


def test_partial_refusal_transfer_and_new_delivery_keep_original_plan(assignments):
    trip = start(assignments)
    first = trip['stops'][0]
    trip = accept(trip, first, '1,5')
    assert trips.stock(trip)[0]['shipped_kg'] == '1.5'
    assert trip['stops'][0]['lines'][0]['planned'] == '8'
    trip = trips.redirect(trip['id'], trip['revision'], trip['products'][0]['id'], '6,5', trip['stops'][1]['name'], ADMIN, op())
    added = trip['stops'][-1]
    assert added['kind'] == 'transfer'
    assert trips.stock(trip)[0]['shipped_kg'] == '1.5'
    trip = accept(trip, added, '6')
    assert trips.stock(trip)[0]['shipped_kg'] == '7.5'
    assert trip['stops'][0]['lines'][0]['accepted'] == '1.5'
    snapshot = driver_orders.load_snapshot(assignments[0]['assignment_id'])
    assert snapshot['stores'][0]['lines'][0]['actual_qty'] == '1.5'
    assert not trip['projection_error']


def test_duplicate_payload_revision_and_negative_stock_protected(assignments):
    trip = start(assignments)
    stop = trip['stops'][0]
    identity = op()
    current = accept(trip, stop, '1.5', operation_id=identity)
    replay = accept(trip, stop, '1.5', operation_id=identity)
    assert replay == current
    with pytest.raises(trips.TripConflict):
        accept(trip, stop, '2', operation_id=identity)
    with pytest.raises(trips.TripConflict):
        trips.redirect(current['id'], trip['revision'], current['products'][0]['id'], '1', current['stops'][1]['name'], ADMIN, op())
    before = deepcopy(current)
    with pytest.raises(trips.TripConflict):
        trips.redirect(current['id'], current['revision'], current['products'][0]['id'], '1000', current['stops'][1]['name'], ADMIN, op())
    assert trips.load_trip(current['id']) == before


def test_zero_partial_requires_reason_and_owner(assignments):
    trip = start(assignments)
    with pytest.raises(trips.TripError):
        accept(trip, trip['stops'][0], '0', reason='')
    payload = {'operation_id': op(), 'base_revision': 0, 'measurements': {trip['stops'][0]['lines'][0]['id']: {'kind': 'net', 'net_weight_kg': '0'}}}
    with pytest.raises(trips.TripError):
        trips.complete_stop(trip['id'], trip['stops'][0]['id'], payload, {'kind': 'driver', 'id': 'other'})


def test_topup_is_separate_and_only_confirmed_measurements_add_stock(assignments):
    trip = start(assignments)
    product = trip['products'][0]['id']
    measurement = {'weighings': [
        {'id': 'one', 'box_count': '3', 'tare_weight_per_box_kg': '0.4', 'gross_weight_kg': '15'},
        {'id': 'two', 'box_count': '2', 'tare_weight_per_box_kg': '0.6', 'gross_weight_kg': '10'},
    ]}
    trip = trips.save_topup(trip['id'], trip['revision'], product, measurement, ACTOR, op())
    assert trips.stock(trip)[0]['remaining_kg'] == '120'
    identity = op()
    before = trip['revision']
    trip = trips.confirm_topup(trip['id'], before, trip['topups'][0]['id'], ACTOR, identity)
    assert trips.stock(trip)[0]['remaining_kg'] == '142.6'
    assert trips.confirm_topup(trip['id'], before, trip['topups'][0]['id'], ACTOR, identity) == trip
    assert records.load_order_record(assignments[0]['order_record_id'])['loading_lines'][0]['measurement']['net_weight_kg'] == '100'


def test_return_receipt_difference_and_closure(assignments):
    trip = finish(start(assignments))
    context = trips.return_context(trip)
    product = trip['products'][0]['id']
    doc = trips.submit_return(trip['id'], {'operation_id': op(), 'base_revision': 0, 'facts_token': context['facts_token'],
        'lines': {product: {'box_count': '0', 'tare_weight_per_box_kg': '0', 'gross_weight_kg': '120', 'reason': context['reasons'][0], 'comment': ''}}}, DRIVER)
    trip = trips.load_trip(trip['id'])
    assert doc['status'] == 'submitted'
    assert trips.stock(trip)[0]['remaining_kg'] == '120'
    trip = trips.receive_return(trip['id'], trip['revision'], {product: '118'}, '', ACTOR, op())
    assert trips.stock(trip)[0]['remaining_kg'] == '2'
    assert trip['returns'][-1]['lines'][0]['difference_kg'] == '-2'
    with pytest.raises(trips.TripConflict):
        trips.close_trip(trip['id'], trip['revision'], ADMIN, op())
    trip = trips.resolve_difference(trip['id'], trip['revision'], product, '-2', 'Недостача при сверке', ADMIN, op())
    trip = trips.close_trip(trip['id'], trip['revision'], ADMIN, op())
    assert trip['status'] == 'closed'
    assert trips.active_for_driver('driver') is None
    with pytest.raises(trips.TripConflict):
        trips.redirect(trip['id'], trip['revision'], product, '1', 'Магазин А', ADMIN, op())


def test_projection_failure_repair_does_not_spend_twice(assignments, monkeypatch):
    trip = start(assignments)
    original = driver_orders.complete_store
    monkeypatch.setattr(driver_orders, 'complete_store', lambda *args: (_ for _ in ()).throw(OSError('disk')))
    trip = accept(trip, trip['stops'][0], '1.5')
    assert trip['projection_error']
    assert trips.stock(trip)[0]['shipped_kg'] == '1.5'
    monkeypatch.setattr(driver_orders, 'complete_store', original)
    trips.repair_projections(trip['id'])
    repaired = trips.load_trip(trip['id'])
    assert not repaired['projection_error']
    assert trips.stock(repaired)[0]['shipped_kg'] == '1.5'


def test_edit_and_cancel_transfer_release_reserve_without_shipping(assignments):
    trip = start(assignments)
    product = trip['products'][0]['id']
    trip = trips.redirect(trip['id'], trip['revision'], product, '10', 'Магазин Г', ADMIN, op())
    target = deepcopy(trip['stops'][-1])
    trip = trips.edit_redirect(trip['id'], trip['revision'], target['id'], product, '5', target['name'], ADMIN, op())
    with pytest.raises(trips.TripConflict):
        accept(trip, target, '1')
    assert trips.stock(trip)[0]['reserved_kg'] == '19'
    trip = trips.cancel_stop(trip['id'], trip['revision'], target['id'], 'Отмена поставки', ADMIN, op())
    assert trips.stock(trip)[0]['remaining_kg'] == '120'
    assert trips.stock(trip)[0]['reserved_kg'] == '14'


def test_cancel_draft_frees_members_and_vehicle(assignments):
    trip = trips.create_trip([item['assignment_id'] for item in assignments], '2026-10-10', ADMIN, op())
    trip = trips.cancel_draft(trip['id'], trip['revision'], 'Ошибочный выбор', ADMIN, op())
    assert trip['status'] == 'closed'
    assert trips.trip_for_assignment(assignments[0]['assignment_id']) is None
    assert start(assignments)['status'] == 'active'


def test_concurrent_redirects_do_not_overbook(assignments):
    from concurrent.futures import ThreadPoolExecutor
    trip = start(assignments)
    def move():
        try:
            trips.redirect(trip['id'], trip['revision'], trip['products'][0]['id'], '100', 'Магазин Г', ADMIN, op())
            return True
        except trips.TripConflict:
            return False
    with ThreadPoolExecutor(max_workers=2) as pool:
        assert sorted(pool.map(lambda _: move(), range(2))) == [False, True]
    result = trips.load_trip(trip['id'])
    assert trips.stock(result)[0]['available_kg'] == '6'


@pytest.mark.parametrize('assignments', [{'route_4': '2.5', 'route_5': '2.5'}], indirect=True)
def test_confirmed_topup_can_replenish_underloaded_original_stop(assignments):
    trip = start(assignments)
    target = trip['stops'][0]
    assert target['lines'][0]['allocated'] == '5'
    measurement = {'box_count': '0', 'tare_weight_per_box_kg': '0', 'gross_weight_kg': '3'}
    trip = trips.save_topup(trip['id'], trip['revision'], trip['products'][0]['id'], measurement, ACTOR, op(), target_stop_id=target['id'])
    trip = trips.confirm_topup(trip['id'], trip['revision'], trip['topups'][0]['id'], ACTOR, op())
    assert trip['stops'][0]['lines'][0]['allocated'] == '8'
    assert trip['stops'][0]['revision'] == target['revision']


def test_existing_partial_shipments_import_once_and_legacy_return_is_blocked(assignments):
    source = assignments[0]
    shop = source['stores'][0]
    identity = op()
    records.save_store_shipment(source['order_record_id'], source['route_key'], shop['order_record_destination_id'],
        {shop['lines'][0]['order_record_position_id']: {'kind': 'net', 'net_weight_kg': '1.5'}}, identity, DRIVER)
    driver_orders.complete_store(driver_orders.sidecar_path(source['assignment_id']), shop['store_id'],
        {shop['lines'][0]['line_id']: {'kind': 'net', 'net_weight_kg': '1.5'}}, identity, 0)
    trip = start(assignments)
    assert trips.stock(trip)[0]['remaining_kg'] == '118.5'
    assert trip['stops'][0]['status'] == 'completed'
    from modules import goods_returns
    assert not goods_returns.return_context(driver_orders.load_snapshot(source['assignment_id']))['eligible']
    replay = trips.complete_legacy_stop(source['assignment_id'], shop['store_id'], {'operation_id': identity, 'base_revision': 0,
        'measurements': {shop['lines'][0]['line_id']: {'kind': 'net', 'net_weight_kg': '1.5'}}}, DRIVER)
    assert replay['revision'] == 1
    assert trips.stock(trips.load_trip(trip['id']))[0]['shipped_kg'] == '1.5'
