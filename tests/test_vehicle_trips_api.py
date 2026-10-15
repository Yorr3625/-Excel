from orders_dashboard.api import common as api_common
import pytest

from modules import driver_orders, fleet, loader_sessions, vehicle_trips as trips
from test_driver_api import client, driver_api_fixture, submit_mileage
from test_vehicle_trips import assignments, record, ADMIN, op


@pytest.fixture
def trip_api(driver_api_fixture, assignments):
    driver, original = driver_api_fixture
    for snapshot in assignments:
        snapshot['driver_id'] = driver['id']
        snapshot['vehicle_id'] = original['vehicle_id']
        driver_orders.save_snapshot(snapshot)
    trip = trips.create_trip([item['assignment_id'] for item in assignments], '2026-10-10', ADMIN, op())
    trip = trips.start_trip(trip['id'], trip['revision'], ADMIN, op())
    return driver, trip, assignments


def login(client, driver):
    response = client.post('/api/driver/login', json={'driver_id': driver['id'], 'pin': '1234'})
    assert response.status_code == 200
    assert submit_mileage(client, response).status_code == 200
    return {'x-driver-csrf': response.json()['csrf_token']}


def test_driver_sees_all_stops_and_net_receipt_is_idempotent(client, trip_api):
    driver, trip, _ = trip_api
    headers = login(client, driver)
    data = client.get('/api/driver/me').json()['assignment']
    assert data['trip_id'] == trip['id']
    assert len(data['stores']) == 3
    stop = trip['stops'][0]
    payload = {'trip_id': trip['id'], 'assignment_id': trip['id'], 'base_revision': 0, 'operation_id': op(),
               'measurements': {stop['lines'][0]['id']: {'kind': 'net', 'net_weight_kg': '1,5'}},
               'reasons': {stop['lines'][0]['id']: {'reason': 'Отказ магазина', 'comment': ''}}}
    endpoint = f"/api/driver/trips/{trip['id']}/stops/{stop['id']}/complete"
    assert client.post(endpoint, json=payload).status_code == 403
    first = client.post(endpoint, headers=headers, json=payload)
    assert first.status_code == 200, first.text
    repeat = client.post(endpoint, headers=headers, json=payload)
    assert repeat.status_code == 200
    assert repeat.json()['assignment']['stock'][0]['shipped_kg'] == '1.5'
    payload['measurements'][stop['lines'][0]['id']]['net_weight_kg'] = '2'
    assert client.post(endpoint, headers=headers, json=payload).status_code == 409
    assert client.post('/api/driver/sync', headers=headers, json={}).status_code == 200


def test_trip_api_is_not_visible_to_another_driver(client, trip_api):
    _, trip, _ = trip_api
    other = fleet.add_driver('Другой водитель')
    fleet.set_driver_pin(other['id'], '1234')
    response = client.post('/api/driver/login', json={'driver_id': other['id'], 'pin': '1234'})
    assert response.status_code == 200
    assert client.get(f"/api/driver/trips/{trip['id']}").status_code == 404
    assert client.get(f"/api/driver/trips/{trip['id']}/returns").status_code == 404


def test_late_legacy_completion_uses_trip_ledger_and_replay_does_not_double_count(client, trip_api):
    driver, trip, assignments = trip_api
    headers = login(client, driver)
    source = assignments[0]
    store = source['stores'][0]
    line = store['lines'][0]
    payload = {'assignment_id': source['assignment_id'], 'operation_id': op(), 'base_revision': 0,
               'measurements': {line['line_id']: {'kind': 'net', 'net_weight_kg': line['required_qty']}}}
    endpoint = f"/api/driver/order/stores/{store['store_id']}/complete"
    for _ in range(2):
        response = client.post(endpoint, headers=headers, json=payload)
        assert response.status_code == 200, response.text
    assert trips.stock(trips.load_trip(trip['id']))[0]['shipped_kg'] == '8'
    # The old per-route return cannot spend this stock again.
    context = client.get('/api/driver/returns/' + source['assignment_id']).json()['context']
    assert not context['eligible']
    assert context['trip_id'] == trip['id']


def test_trip_mileage_accepts_only_proven_source_alias_for_same_vehicle_and_day(client, trip_api):
    driver, trip, assignments = trip_api
    response = client.post('/api/driver/login', json={'driver_id': driver['id'], 'pin': '1234'})
    data = response.json()
    mileage = data['mileage']
    payload = {'odometer_km': '100', 'vehicle_id': mileage['vehicle']['id'], 'date': mileage['date'], 'assignment_id': assignments[0]['assignment_id']}
    headers = {'x-driver-csrf': data['csrf_token']}
    invalid = {**payload, 'assignment_id': 'another'}
    assert client.post('/api/driver/mileage', headers=headers, json=invalid).status_code == 409
    assert client.post('/api/driver/mileage', headers=headers, json=payload).status_code == 200


def test_driver_overnight_and_deferred_unload_operations(client, trip_api):
    driver, trip, _ = trip_api
    headers = login(client, driver)
    endpoint = f"/api/driver/trips/{trip['id']}"
    base = {'trip_id': trip['id'], 'revision': trip['revision'], 'operation_id': op()}
    assert client.post(endpoint + '/arrive', json=base).status_code == 403
    assert client.post(endpoint + '/arrive', headers=headers, json=base).status_code == 200
    assert client.post(endpoint + '/arrive', headers=headers, json=base).status_code == 200
    current = trips.load_trip(trip['id'])
    check = {'trip_id': trip['id'], 'revision': current['revision'], 'operation_id': op(),
             'amounts': {current['products'][0]['id']: '120'}}
    assert client.post(endpoint + '/check', headers=headers, json=check).status_code == 200
    current = trips.load_trip(trip['id'])
    unload = {'trip_id': trip['id'], 'revision': current['revision'], 'operation_id': op(),
              'occurred_at': '2026-10-11T08:00:00+03:00', 'note': 'Бланк на базе'}
    result = client.post(endpoint + '/unload-all', headers=headers, json=unload)
    assert result.status_code == 200, result.text
    assert result.json()['assignment']['status'] == 'released_pending'
    assert result.json()['assignment']['stock'][0]['remaining_kg'] == '0'
    assert client.get('/api/driver/me').json()['assignment'] is None
    assert trips.load_trip(trip['id'])['stops'][0]['status'] == 'deferred'


def test_loader_shared_trip_requires_selected_vehicle_and_keeps_actor(client, trip_api, monkeypatch):
    import orders_dashboard.orders_dashboard as dashboard
    _, trip, _ = trip_api
    loader = fleet.add_driver('Грузчик рейса', role='loader')
    fleet.set_driver_pin(loader['id'], '1234')
    response = client.post('/api/loader/login', json={'loader_id': loader['id'], 'pin': '1234'})
    assert response.status_code == 200
    headers = {'x-loader-csrf': response.json()['csrf_token']}
    monkeypatch.setattr(api_common, '_loader_available_vehicles', lambda: [{'id': trip['vehicle_id']}])
    assert client.get('/api/crew/me').status_code == 409
    assert client.post('/api/loader/vehicle', headers=headers, json={'vehicle_id': trip['vehicle_id']}).status_code == 200
    data = client.get('/api/crew/me').json()
    assert data['driver']['id'] == loader['id']
    assert data['assignment']['trip_id'] == trip['id']
    assert not data['mileage']['required']
    stop = trip['stops'][0]
    payload = {'trip_id': trip['id'], 'assignment_id': trip['id'], 'base_revision': 0, 'operation_id': op(),
               'measurements': {stop['lines'][0]['id']: {'kind': 'net', 'net_weight_kg': '8'}}, 'reasons': {}}
    endpoint = f"/api/crew/trips/{trip['id']}/stops/{stop['id']}/complete"
    assert client.post(endpoint, json=payload).status_code == 403
    result = client.post(endpoint, headers=headers, json=payload)
    assert result.status_code == 200, result.text
    saved = trips.load_trip(trip['id'])
    assert saved['stops'][0]['completed_by']['id'] == loader['id']
    assert saved['history'][-1]['actor']['kind'] == 'loader'
    monkeypatch.setattr(api_common, '_loader_available_vehicles', lambda: [{'id': 'other'}])
    assert client.post('/api/loader/vehicle', headers=headers, json={'vehicle_id': 'other'}).status_code == 200
    assert client.get(f"/api/crew/trips/{trip['id']}").status_code == 404
