import json

from modules import paths


def load_settings(path=paths.SETTINGS_FILE):
    """Загружает config/settings.json (настройки поведения программы)."""

    with open(path, "r", encoding="utf-8") as file:
        return json.load(file)


def load_stores(path=paths.STORES_FILE):
    """Загружает список магазинов по маршрутам (config/stores*.json)."""

    with open(path, "r", encoding="utf-8") as file:
        return json.load(file)


def save_settings(data, path=paths.SETTINGS_FILE):
    """Сохраняет настройки в config/settings.json."""

    with open(path, "w", encoding="utf-8") as file:
        json.dump(data, file, ensure_ascii=False, indent=2)


def save_stores(data, path=paths.STORES_FILE):
    """Сохраняет список магазинов по маршрутам в config/stores*.json."""

    with open(path, "w", encoding="utf-8") as file:
        json.dump(data, file, ensure_ascii=False, indent=2)


def build_groups(stores, fills):
    """
    Собирает список групп маршрутов вида:
    {"name": "Маршрут №1", "names": [...], "fill": green_fill}

    fills — список заливок в порядке route_1..route_4.
    """

    route_keys = ["route_1", "route_2", "route_3", "route_4"]

    groups = []

    for index, key in enumerate(route_keys):
        groups.append(
            {
                "name": f"Маршрут №{index + 1}",
                "names": stores[key],
                "fill": fills[index],
            }
        )

    return groups
