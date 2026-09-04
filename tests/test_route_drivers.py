import pytest

from modules import paths, route_drivers


@pytest.fixture(autouse=True)
def _isolated_config_dir(tmp_path, monkeypatch):
    """Уводит файл водителей во временную папку, чтобы тесты не трогали config/."""

    target = tmp_path / "route_drivers.json"
    monkeypatch.setattr(paths, "ROUTE_DRIVERS_FILE", target)
    monkeypatch.setattr(route_drivers, "ROUTE_DRIVERS_FILE", target)


def test_load_returns_defaults_when_file_is_missing():
    assert route_drivers.load_route_drivers() == dict(route_drivers.DEFAULT_DRIVERS)


def test_load_survives_broken_json():
    route_drivers.ROUTE_DRIVERS_FILE.write_text("{не json", encoding="utf-8")

    assert route_drivers.load_route_drivers() == dict(route_drivers.DEFAULT_DRIVERS)


def test_save_and_load_roundtrip():
    route_drivers.save_route_drivers(
        {"route_1": "Игорь", "route_2": "Азер", "route_3": "Фарид", "route_4": "Раван"}
    )

    assert route_drivers.load_route_drivers()["route_1"] == "Игорь"


def test_save_fills_missing_keys_with_defaults():
    route_drivers.save_route_drivers({"route_2": "Новый"})

    data = route_drivers.load_route_drivers()
    assert data["route_2"] == "Новый"
    assert data["route_1"] == route_drivers.DEFAULT_DRIVERS["route_1"]


def test_save_creates_parent_directory(tmp_path, monkeypatch):
    target = tmp_path / "нет-такой-папки" / "route_drivers.json"
    monkeypatch.setattr(route_drivers, "ROUTE_DRIVERS_FILE", target)

    route_drivers.save_route_drivers({"route_1": "Игорь"})

    assert target.exists()


@pytest.mark.parametrize(
    "name, expected",
    [
        ("Маршрут №1", 0),
        ("Маршрут №4", 3),
        ("Маршрут№2", 1),
        ("маршрут №3 (что-то)", 2),
        ("Маршрут №9", None),
        ("Служебный лист", None),
        ("", None),
    ],
)
def test_route_index_from_name(name, expected):
    assert route_drivers.route_index_from_name(name) == expected


def test_route_header_text_format():
    assert route_drivers.route_header_text(1, "Азер") == "Маршрут №2 (Азер) - Центр"


def test_route_header_for_name_uses_given_drivers():
    drivers = {"route_1": "Игорь", "route_2": "Азер", "route_3": "Фарид", "route_4": "Раван"}

    assert route_drivers.route_header_for_name("Маршрут №1", drivers) == "Маршрут №1 (Игорь) - Текстильщик"


def test_route_header_for_name_falls_back_to_saved_drivers():
    route_drivers.save_route_drivers({"route_3": "Новенький"})

    assert route_drivers.route_header_for_name("Маршрут №3") == "Маршрут №3 (Новенький) - Заперевальная"


def test_route_header_for_name_unrecognized_returns_none():
    assert route_drivers.route_header_for_name("Служебный лист") is None


def test_route_header_text_omits_district_for_added_routes():
    assert route_drivers.route_header_text(4, "----") == "Маршрут №5 (----)"


def test_route_index_from_name_recognizes_added_routes():
    assert route_drivers.route_index_from_name("Маршрут №5") == 4
    assert route_drivers.route_index_from_name("Маршрут №8") == 7
