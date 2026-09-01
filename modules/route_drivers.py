"""Водитель и район каждого маршрута.

Нужны для колонтитула на печатных листах маршрутов, для редактирования на
странице «Заказы» и для подписи во вкладке «Вес». Район маршрута фиксирован
(какие районы возит какая машина, не меняется день ото дня), а имя водителя
хранится в config/route_drivers.json и может быть изменено — например, при
замене водителя на маршруте.
"""

import json
import re

from modules.paths import ROUTE_DRIVERS_FILE

ROUTE_KEYS = ("route_1", "route_2", "route_3", "route_4")
ROUTE_AREAS = ("Текстильщик", "Центр", "Заперевальная", "Металдоны")
DEFAULT_DRIVERS = {
    "route_1": "----",
    "route_2": "Азер",
    "route_3": "Фарид",
    "route_4": "Раван",
}

_NAME_PATTERN = re.compile(r"№\s*(\d+)")


def load_route_drivers() -> dict:
    """Словарь {"route_1": "Имя водителя", ...}.

    При отсутствии файла или повреждённом JSON возвращает значения по
    умолчанию — так правка на диске никогда не роняет страницу «Заказы» или
    обработку заказа.
    """

    if ROUTE_DRIVERS_FILE.exists():
        try:
            data = json.loads(ROUTE_DRIVERS_FILE.read_text(encoding="utf-8"))
            return {key: str(data.get(key, DEFAULT_DRIVERS[key])) for key in ROUTE_KEYS}
        except (OSError, json.JSONDecodeError):
            pass

    return dict(DEFAULT_DRIVERS)


def save_route_drivers(drivers: dict) -> None:
    """Сохраняет имена водителей по маршрутам в config/route_drivers.json."""

    data = {key: str(drivers.get(key, DEFAULT_DRIVERS[key])) for key in ROUTE_KEYS}
    ROUTE_DRIVERS_FILE.parent.mkdir(parents=True, exist_ok=True)
    ROUTE_DRIVERS_FILE.write_text(
        json.dumps(data, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def route_index_from_name(route_name: str) -> int | None:
    """Номер маршрута (с 0) из названия вида «Маршрут №2», иначе None."""

    match = _NAME_PATTERN.search(route_name or "")
    if not match:
        return None

    index = int(match.group(1)) - 1
    return index if 0 <= index < len(ROUTE_KEYS) else None


def route_header_text(index: int, driver: str) -> str:
    """Текст колонтитула: «Маршрут №N (Водитель) - Район»."""

    return f"Маршрут №{index + 1} ({driver}) - {ROUTE_AREAS[index]}"


def route_header_for_name(route_name: str, drivers: dict | None = None) -> str | None:
    """Текст колонтитула по названию листа/группы маршрута.

    Возвращает None, если номер маршрута не распознан в названии — тогда
    колонтитул просто не выставляется, вместо падения обработки.
    """

    index = route_index_from_name(route_name)
    if index is None:
        return None

    drivers = drivers if drivers is not None else load_route_drivers()
    driver = drivers.get(ROUTE_KEYS[index], DEFAULT_DRIVERS[ROUTE_KEYS[index]])

    return route_header_text(index, driver)
