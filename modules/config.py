import json


def load_settings(path="settings.json"):
    """Загружает settings.json (настройки поведения программы)."""

    with open(path, "r", encoding="utf-8") as file:
        return json.load(file)


def load_stores(path="stores.json"):
    """Загружает stores.json (список магазинов по маршрутам)."""

    with open(path, "r", encoding="utf-8") as file:
        return json.load(file)


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
