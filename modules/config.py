import json

from modules import paths

DEFAULT_ROUTE_COUNT = 4
MAX_ROUTES = 8


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


def build_groups(stores, fills, route_count=DEFAULT_ROUTE_COUNT):
    """
    Собирает список групп маршрутов вида:
    {"name": "Маршрут №1", "names": [...], "fill": green_fill}

    fills — список заливок, минимум route_count штук. Магазины берутся по
    ключу route_1..route_N; отсутствующий в stores ключ (маршрут только что
    добавлен и ещё не сохранён) даёт пустой список, а не падение.
    """

    groups = []

    for index in range(route_count):
        key = f"route_{index + 1}"
        groups.append(
            {
                "name": f"Маршрут №{index + 1}",
                "names": stores.get(key, []),
                "fill": fills[index],
            }
        )

    return groups


def load_route_count(path=paths.ROUTES_FILE) -> int:
    """Сколько маршрутов сейчас активно (config/routes.json, {"count": N}).

    Число маршрутов не выводится из ключей stores*.json — там могут быть
    уже подготовленные, но ещё не показанные пользователю route_N (см.
    add_route) — а хранится отдельно, чтобы «Добавить маршрут» было ровно
    одной операцией. При отсутствии файла — старые инсталляции без него —
    возвращает DEFAULT_ROUTE_COUNT, что соответствует прежним 4 маршрутам.
    """

    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        count = int(data.get("count", DEFAULT_ROUTE_COUNT))
    except (OSError, ValueError, TypeError, json.JSONDecodeError):
        return DEFAULT_ROUTE_COUNT

    return max(1, min(MAX_ROUTES, count))


def save_route_count(count: int, path=paths.ROUTES_FILE) -> None:
    """Сохраняет число активных маршрутов в config/routes.json."""

    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps({"count": max(1, min(MAX_ROUTES, count))}, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
