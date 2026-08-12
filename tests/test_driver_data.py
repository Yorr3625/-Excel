import pytest

from modules import driver_data


@pytest.fixture(autouse=True)
def _isolated_tracking_dir(tmp_path, monkeypatch):
    monkeypatch.setattr(driver_data, "DATA_DIR", tmp_path / "tracking_data")


@pytest.mark.parametrize("key", ["route_1", "route_2", "route_3", "route_4"])
def test_known_vehicles_are_accepted(key):
    assert driver_data.is_valid_vehicle(key)
    assert driver_data._file_path(key).name.endswith(f"_{key}.json")


@pytest.mark.parametrize(
    "key",
    [
        "",
        "route_9",
        "../../../evil",
        "../config/stores_city",
        "..\\..\\config\\settings",
        "route_1/../../escape",
    ],
)
def test_unknown_vehicle_keys_are_rejected(key):
    """vehicle_key приходит из тела HTTP-запроса на /api/gps-ping.

    Без белого списка значение вида "../../.." уводило запись json за
    пределы data/tracking_data — вплоть до перезаписи файлов в config/.
    """

    assert not driver_data.is_valid_vehicle(key)

    with pytest.raises(ValueError):
        driver_data._file_path(key)


def test_append_gps_ignores_unknown_vehicle_without_writing(tmp_path):
    evil = "../../../evil"

    # Куда запись ушла бы без белого списка — именно этот файл и не должен
    # появиться (он лежит выше папки трекинга, поэтому проверять только
    # содержимое tmp_path недостаточно).
    escaped = (driver_data.DATA_DIR / f"2026-01-01_{evil}.json").resolve()

    driver_data.append_gps(evil, 48.0, 37.8, 40)

    assert not escaped.exists()
    assert not any(tmp_path.rglob("*.json"))


def test_append_gps_stores_point_for_known_vehicle():
    driver_data.append_gps("route_1", 48.0, 37.8, 42)

    data = driver_data._read(driver_data._file_path("route_1"))

    assert data["last_position"]["lat"] == 48.0
    assert data["last_position"]["speed"] == 42
    assert len(data["trail"]) == 1


def test_append_gps_skips_points_without_coordinates():
    driver_data.append_gps("route_1", None, None, 40)

    assert driver_data._read(driver_data._file_path("route_1")) is None


def test_trail_is_capped(monkeypatch):
    monkeypatch.setattr(driver_data, "TRAIL_LIMIT", 5)

    for i in range(12):
        driver_data.append_gps("route_2", 48.0 + i, 37.8, 30)

    data = driver_data._read(driver_data._file_path("route_2"))

    assert len(data["trail"]) == 5
