from decimal import Decimal

import pytest

from modules import driver_orders, order_records as records
import orders_dashboard.orders_dashboard as dashboard
from test_driver_api import client, driver_api_fixture, submit_mileage
from test_store_loading import ACTOR, record, ready, destinations


@pytest.mark.parametrize('value,expected', [('1,5', '1.5'), ('0.4', '0.4'), ('0', '0')])
def test_net_measurement_validates_in_both_snapshots(value, expected):
    measure = {'kind': 'net', 'net_weight_kg': value}
    result = {'kind': 'net', 'net_weight_kg': expected}
    assert driver_orders._measurement(measure) == result
    assert records._validated_shipment_measurement(measure) == result
    assert records._shipment_measurement_complete(result)


@pytest.mark.parametrize('value', ['', ' ', '-1', 'NaN', 'Infinity', 'bad', '1' * 100])
def test_invalid_net_rejected_by_both_models(value):
    measure = {'kind': 'net', 'net_weight_kg': value}
    with pytest.raises(driver_orders.DriverOrderError):
        driver_orders._measurement(measure)
    with pytest.raises(records.OrderRecordError):
        records._validated_shipment_measurement(measure)
    assert not records._shipment_measurement_complete(measure)


def test_net_measurement_does_not_accept_extra_tare_or_unknown_kind():
    for value in [{'kind': 'net', 'net_weight_kg': '1', 'box_count': '2'}, {'kind': 'other', 'net_weight_kg': '1'}]:
        with pytest.raises(driver_orders.DriverOrderError):
            driver_orders._measurement(value)
        with pytest.raises(records.OrderRecordError):
            records._validated_shipment_measurement(value)


def test_net_shipment_persists_and_uses_same_return_capacity(record):
    record = ready(record)
    for destination, net in zip(destinations(record), ('8,5', '2')):
        record = records.save_store_shipment(record['id'], 'route_4', destination['id'], {
            destination['positions'][0]['id']: {'kind': 'net', 'net_weight_kg': net},
        }, 'net-' + destination['id'], ACTOR)
    current = records.load_order_record(record['id'])
    assert destinations(current)[0]['positions'][0]['shipment']['measurement'] == {'kind': 'net', 'net_weight_kg': '8.5'}
    balance = records.route_return_balance(current, 'route_4')
    assert balance['complete']
    assert Decimal(balance['lines'][0]['available_net_kg']) == Decimal('1.5')
    assert records.logistics_summary(current)['total_shipped_net_kg'] == '10.5'


def test_net_api_links_registry_and_assignment_and_retries_idempotently(client, driver_api_fixture, monkeypatch):
    driver, snapshot = driver_api_fixture
    snapshot['order_record_id'] = 'record-test'
    store = snapshot['stores'][0]
    store['order_record_destination_id'] = 'destination-test'
    line = store['lines'][0]
    line['order_record_position_id'] = 'position-test'
    driver_orders.save_snapshot(snapshot)
    monkeypatch.setattr(dashboard, 'load_order_record', lambda _: {'id': 'record-test'})
    monkeypatch.setattr(dashboard, 'route_loading_ready', lambda *_: True)
    monkeypatch.setattr(dashboard, 'logistics_summary', lambda _: {'loading_ready': True, 'shipment_status': 'ready_for_shipment'})
    captured = []
    monkeypatch.setattr(dashboard, 'save_store_shipment', lambda *args: captured.append(args) or {})
    login = client.post('/api/driver/login', json={'driver_id': driver['id'], 'pin': '1234'})
    assert submit_mileage(client, login).status_code == 200
    headers = {'x-driver-csrf': login.json()['csrf_token']}
    payload = {'assignment_id': snapshot['assignment_id'], 'base_revision': 0, 'operation_id': 'net-api-op',
               'measurements': {line['line_id']: {'kind': 'net', 'net_weight_kg': '1,5'}}}
    for _ in range(2):
        response = client.post(f"/api/driver/order/stores/{store['store_id']}/complete", headers=headers, json=payload)
        assert response.status_code == 200, response.text
        saved = response.json()['assignment']['stores'][0]['lines'][0]
        assert saved['shipment_measurement'] == {'kind': 'net', 'net_weight_kg': '1.5'}
        assert saved['actual_qty'] == '1.5'
    assert captured[0][3] == {'position-test': {'kind': 'net', 'net_weight_kg': '1,5'}}
    sync = client.post('/api/driver/sync', headers=headers, json={})
    assert sync.status_code == 200
    assert not sync.json()['mileage']['required']
    assert sync.json()['assignment']['revision'] == 1
