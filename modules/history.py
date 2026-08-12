"""История обработок: какие файлы обработаны и сколько вывезено по маршрутам.

Общая для всех трёх интерфейсов — консоли (main.py), окна на tkinter
(gui_app.py) и веб-дашборда. Раньше запись истории файлов была продублирована
в main.py и в дашборде, а объём по маршрутам писал только дашборд — из-за
чего график «Вывезенный объём» не учитывал обработки из консоли и tkinter.
"""

import json
from datetime import datetime

from modules.paths import PROCESSED_FILES_FILE, VOLUME_HISTORY_FILE


ROUTE_KEYS = ("route_1", "route_2", "route_3", "route_4")


def _read_json(path, default):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return default


def _write_json(path, data, indent):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(data, ensure_ascii=False, indent=indent),
        encoding="utf-8",
    )


def load_processed_files() -> dict:
    """Словарь {имя файла: когда обработан}."""

    return _read_json(PROCESSED_FILES_FILE, {})


def save_processed_file(filename: str) -> None:
    data = load_processed_files()
    data[filename] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    _write_json(PROCESSED_FILES_FILE, data, indent=4)


def load_volume_history() -> list:
    """Список записей вида {"date": ..., "route_1": ..., ...}."""

    return _read_json(VOLUME_HISTORY_FILE, [])


def save_volume_record(route_totals) -> None:
    """Записывает суммы по маршрутам за сегодня (для графика на Dashboard)."""

    totals = list(route_totals)

    while len(totals) < len(ROUTE_KEYS):
        totals.append(0)

    record = {"date": datetime.now().strftime("%Y-%m-%d")}
    record.update(zip(ROUTE_KEYS, totals))

    records = load_volume_history()
    records.append(record)
    _write_json(VOLUME_HISTORY_FILE, records, indent=2)


def record_processing(filename: str, stats: dict) -> None:
    """Единая точка: сохранить факт обработки файла и объём по маршрутам.

    stats — то, что вернул modules.pipeline.process_order.
    """

    save_processed_file(filename)
    save_volume_record(list(stats.get("route_totals", {}).values()))
