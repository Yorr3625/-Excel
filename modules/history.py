"""История обработок: какие файлы обработаны и сколько вывезено по маршрутам.

Общая для всех трёх интерфейсов — консоли (main.py), окна на tkinter
(gui_app.py) и веб-дашборда. Раньше запись истории файлов была продублирована
в main.py и в дашборде, а объём по маршрутам писал только дашборд — из-за
чего график «Вывезенный объём» не учитывал обработки из консоли и tkinter.
"""

import json
from datetime import datetime

from modules.paths import PROCESSED_FILES_FILE, VOLUME_HISTORY_FILE


ROUTE_KEYS = tuple(f"route_{i}" for i in range(1, 9))


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
    """Словарь {имя файла: когда обработан впервые}."""

    return _read_json(PROCESSED_FILES_FILE, {})


def was_processed(filename: str) -> str:
    """Когда файл обрабатывался, или пустая строка, если ещё не обрабатывался."""

    return load_processed_files().get(filename, "")


def save_processed_file(filename: str) -> None:
    """Отмечает файл обработанным.

    Время первой обработки не перезаписывается: иначе повторная обработка
    старого заказа переносила бы его в «сегодня» и завышала счётчик
    заказов за день.
    """

    data = load_processed_files()

    if filename in data:
        return

    data[filename] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    _write_json(PROCESSED_FILES_FILE, data, indent=4)


def load_volume_history() -> list:
    """Список записей вида {"date": ..., "route_1": ..., ...}."""

    return _read_json(VOLUME_HISTORY_FILE, [])


def save_volume_record(route_totals, filename: str = "") -> None:
    """Записывает суммы по маршрутам (для графика на Dashboard).

    На один файл заказа приходится одна запись: повторная обработка
    обновляет суммы, а не добавляет их к прежним. Иначе один и тот же
    заказ, обработанный дважды, удваивал объём на графике.

    Дата первой обработки сохраняется — повторный прогон считается
    исправлением, а не новой отгрузкой, и не должен переносить объём
    на другой день.
    """

    totals = list(route_totals)

    while len(totals) < len(ROUTE_KEYS):
        totals.append(0)

    records = load_volume_history()

    if filename:
        for record in records:
            if record.get("file") == filename:
                record.update(zip(ROUTE_KEYS, totals))
                _write_json(VOLUME_HISTORY_FILE, records, indent=2)
                return

    record = {"date": datetime.now().strftime("%Y-%m-%d"), "file": filename}
    record.update(zip(ROUTE_KEYS, totals))

    records.append(record)
    _write_json(VOLUME_HISTORY_FILE, records, indent=2)


def record_processing(filename: str, stats: dict) -> None:
    """Единая точка: сохранить факт обработки файла и объём по маршрутам.

    stats — то, что вернул modules.pipeline.process_order.
    """

    save_processed_file(filename)
    save_volume_record(list(stats.get("route_totals", {}).values()), filename)
