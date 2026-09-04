from modules.config import (
    DEFAULT_ROUTE_COUNT,
    MAX_ROUTES,
    build_groups,
    load_route_count,
    load_settings,
    save_route_count,
    save_settings,
    load_stores,
    save_stores,
)


def test_build_groups_maps_route_keys_to_named_groups():
    stores = {
        "route_1": ["фм 4"],
        "route_2": ["фм 12"],
        "route_3": ["фм 19"],
        "route_4": ["м2"],
    }
    fills = ["green", "yellow", "blue", "purple"]

    groups = build_groups(stores, fills)

    assert [g["name"] for g in groups] == [
        "Маршрут №1",
        "Маршрут №2",
        "Маршрут №3",
        "Маршрут №4",
    ]
    assert groups[0]["names"] == ["фм 4"]
    assert groups[0]["fill"] == "green"
    assert groups[3]["names"] == ["м2"]
    assert groups[3]["fill"] == "purple"


def test_build_groups_supports_route_count_beyond_stored_keys():
    stores = {"route_1": ["фм 4"], "route_2": ["фм 12"]}
    fills = ["green", "yellow", "orange"]

    groups = build_groups(stores, fills, route_count=3)

    assert [g["name"] for g in groups] == ["Маршрут №1", "Маршрут №2", "Маршрут №3"]
    assert groups[2]["names"] == []
    assert groups[2]["fill"] == "orange"


def test_load_route_count_defaults_when_file_missing(tmp_path):
    assert load_route_count(tmp_path / "нет-такого-файла.json") == DEFAULT_ROUTE_COUNT


def test_route_count_round_trip(tmp_path):
    path = tmp_path / "routes.json"

    save_route_count(6, path=path)

    assert load_route_count(path) == 6


def test_route_count_is_clamped_to_valid_range(tmp_path):
    path = tmp_path / "routes.json"

    save_route_count(999, path=path)
    assert load_route_count(path) == MAX_ROUTES

    save_route_count(0, path=path)
    assert load_route_count(path) == 1


def test_settings_round_trip(tmp_path):
    path = tmp_path / "settings.json"
    data = {"open_file_after_processing": True, "create_logs": False}

    save_settings(data, path=str(path))
    loaded = load_settings(path=str(path))

    assert loaded == data


def test_stores_round_trip(tmp_path):
    path = tmp_path / "stores.json"
    data = {"route_1": ["фм 4"], "route_2": ["фм 12"]}

    save_stores(data, path=str(path))
    loaded = load_stores(path=str(path))

    assert loaded == data


def test_save_settings_writes_readable_utf8_json(tmp_path):
    path = tmp_path / "settings.json"

    save_settings({"комментарий": "проверка кириллицы"}, path=str(path))

    text = path.read_text(encoding="utf-8")
    assert "проверка кириллицы" in text
