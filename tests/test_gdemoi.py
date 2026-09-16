import json
from urllib.error import HTTPError

import pytest

from modules import driver_data, fleet, gdemoi, paths


@pytest.fixture(autouse=True)
def isolated_gdemoi_files(tmp_path, monkeypatch):
    config_dir = tmp_path / "config"
    data_dir = tmp_path / "data"
    gdemoi_file = config_dir / "gdemoi.json"
    fleet_file = config_dir / "fleet.json"
    assignments_file = data_dir / "order_route_assignments.json"

    monkeypatch.setattr(paths, "DATA_DIR", data_dir)
    monkeypatch.setattr(paths, "GDEMOI_FILE", gdemoi_file)
    monkeypatch.setattr(paths, "FLEET_FILE", fleet_file)
    monkeypatch.setattr(paths, "ORDER_ROUTE_ASSIGNMENTS_FILE", assignments_file)
    monkeypatch.setattr(gdemoi, "GDEMOI_FILE", gdemoi_file)
    monkeypatch.setattr(gdemoi, "ORDER_ROUTE_ASSIGNMENTS_FILE", assignments_file)
    monkeypatch.setattr(fleet, "FLEET_FILE", fleet_file)
    monkeypatch.setattr(fleet, "ORDER_ROUTE_ASSIGNMENTS_FILE", assignments_file)
    monkeypatch.setattr(driver_data, "DATA_DIR", data_dir / "tracking_data")


class _Response:
    def __init__(self, payload: dict):
        self._body = json.dumps(payload).encode("utf-8")

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False

    def read(self):
        return self._body


def test_settings_roundtrip_blank_key_keeps_saved_value():
    assert gdemoi.load_settings() == {"api_key": ""}

    gdemoi.save_settings("secret-key")
    assert gdemoi.load_settings() == {"api_key": "secret-key"}

    gdemoi.save_settings("  ")
    assert gdemoi.load_settings() == {"api_key": "secret-key"}


def test_is_configured():
    assert gdemoi.is_configured() is False
    gdemoi.save_settings("secret-key")
    assert gdemoi.is_configured() is True


def test_get_states_parses_location_and_skips_entries_without_gps(monkeypatch):
    captured = {}

    def fake_urlopen(request, timeout):
        captured["request"] = request
        captured["timeout"] = timeout
        return _Response({
            "success": True,
            "states": {
                "111": {"gps": {"location": {"lat": 48.1, "lng": 37.8}, "speed": 42}, "connection_status": "active"},
                "222": {"gps": {"location": {}}, "connection_status": "offline"},
            },
        })

    monkeypatch.setattr(gdemoi, "urlopen", fake_urlopen)

    states = gdemoi.get_states("test-key", [111, 222])

    assert states == {
        111: {"lat": 48.1, "lng": 37.8, "speed": 42, "updated": None, "online": True},
    }
    request = captured["request"]
    assert request.full_url == "https://api.gdemoi.ru/v2/tracker/get_states"
    assert request.get_header("Authorization") == "NVX test-key"
    payload = json.loads(request.data.decode())
    assert payload == {"trackers": [111, 222], "list_blocked": True, "allow_not_exist": True}


def test_get_states_returns_empty_without_calling_api_when_no_tracker_ids(monkeypatch):
    def fake_urlopen(*_args, **_kwargs):
        raise AssertionError("не должно вызываться без ID трекеров")

    monkeypatch.setattr(gdemoi, "urlopen", fake_urlopen)

    assert gdemoi.get_states("test-key", []) == {}


def test_request_raises_friendly_message_for_known_api_error(monkeypatch):
    def fake_urlopen(request, timeout):
        return _Response({"success": False, "status": {"code": 208}})

    monkeypatch.setattr(gdemoi, "urlopen", fake_urlopen)

    with pytest.raises(gdemoi.GdemoiError, match="тариф"):
        gdemoi.list_trackers("test-key")


def test_request_raises_friendly_message_for_http_error(monkeypatch):
    def fake_urlopen(request, timeout):
        body = json.dumps({"status": {"code": 3}}).encode("utf-8")
        raise HTTPError(request.full_url, 403, "Forbidden", {}, __import__("io").BytesIO(body))

    monkeypatch.setattr(gdemoi, "urlopen", fake_urlopen)

    with pytest.raises(gdemoi.GdemoiError, match="ключ"):
        gdemoi.list_trackers("test-key")


def test_list_trackers_parses_source_fields(monkeypatch):
    def fake_urlopen(request, timeout):
        return _Response({
            "success": True,
            "list": [
                {"id": 1698528, "label": "Маяк №1", "source": {"model": "telfmb003_a2", "blocked": False}},
            ],
        })

    monkeypatch.setattr(gdemoi, "urlopen", fake_urlopen)

    assert gdemoi.list_trackers("test-key") == [
        {"id": 1698528, "label": "Маяк №1", "model": "telfmb003_a2", "blocked": False},
    ]


def test_latest_vehicle_route_map_uses_last_recorded_entry():
    fleet.record_order_route_assignments(
        "order1.xlsx", "Город", "result1.xlsx",
        [{"route": "route_1", "vehicle_id": "old-vehicle"}],
    )
    fleet.record_order_route_assignments(
        "order2.xlsx", "Город", "result2.xlsx",
        [{"route": "route_1", "vehicle_id": "vehicle-a"}, {"route": "route_2", "vehicle_id": "vehicle-b"}],
    )

    assert gdemoi.latest_vehicle_route_map() == {"vehicle-a": "route_1", "vehicle-b": "route_2"}


def test_latest_vehicle_route_map_is_empty_without_history():
    assert gdemoi.latest_vehicle_route_map() == {}


def test_poll_and_record_returns_empty_without_api_key():
    vehicle = fleet.add_vehicle("Газель", "А123ВС71", tracker_id="1698528")
    fleet.record_order_route_assignments(
        "order.xlsx", "Город", "result.xlsx",
        [{"route": "route_1", "vehicle_id": vehicle["id"]}],
    )

    assert gdemoi.poll_and_record() == []


def test_poll_and_record_returns_empty_without_bound_vehicles():
    gdemoi.save_settings("test-key")

    assert gdemoi.poll_and_record() == []


def test_poll_and_record_writes_gps_for_vehicle_on_its_current_route(monkeypatch):
    gdemoi.save_settings("test-key")
    vehicle = fleet.add_vehicle("Газель", "А123ВС71", tracker_id="1698528")
    fleet.record_order_route_assignments(
        "order.xlsx", "Город", "result.xlsx",
        [{"route": "route_1", "vehicle_id": vehicle["id"]}],
    )
    monkeypatch.setattr(
        gdemoi, "get_states",
        lambda api_key, tracker_ids: {1698528: {"lat": 48.1, "lng": 37.8, "speed": 40, "updated": "now", "online": True}},
    )

    updated = gdemoi.poll_and_record()

    assert updated == ["route_1"]
    data = driver_data.load_today("route_1")
    assert data["last_position"]["lat"] == 48.1
    assert data["last_position"]["lon"] == 37.8


def test_poll_and_record_skips_vehicle_not_on_any_current_route():
    gdemoi.save_settings("test-key")
    fleet.add_vehicle("Газель", "А123ВС71", tracker_id="1698528")

    assert gdemoi.poll_and_record() == []
