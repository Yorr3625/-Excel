from modules.config import (
    build_groups,
    load_settings,
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
