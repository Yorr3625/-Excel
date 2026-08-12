import os
from datetime import datetime

from modules.logger import write_log
from modules.paths import LOGS_FOLDER


def _stats(**overrides):
    stats = {
        "route_count": {"Маршрут №1": 2, "Маршрут №2": 1},
        "total_found": 3,
        "conflict_count": 0,
        "conflict_list": [],
        "unknown_stores": [],
    }
    stats.update(overrides)
    return stats


def test_write_log_creates_dated_file_with_expected_content(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    now = datetime(2026, 8, 11, 9, 30, 3)

    log_file = write_log("11.08.26", now, "orders/заказ.xlsx", "processed_orders/out.xlsx", _stats())

    assert log_file == os.path.join(LOGS_FOLDER, "11.08.26", "лог.txt")
    text = open(log_file, encoding="utf-8").read()

    assert "orders/заказ.xlsx" in text
    assert "processed_orders/out.xlsx" in text
    assert "Маршрут №1: 2" in text
    assert "Всего найдено: 3" in text
    assert "Конфликтов: 0" in text


def test_write_log_appends_instead_of_overwriting(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    now = datetime(2026, 8, 11, 9, 30, 3)

    write_log("11.08.26", now, "a.xlsx", "out_a.xlsx", _stats())
    log_file = write_log("11.08.26", now, "b.xlsx", "out_b.xlsx", _stats())

    text = open(log_file, encoding="utf-8").read()
    assert text.count("ОБРАБОТКА") == 2
    assert "a.xlsx" in text
    assert "b.xlsx" in text


def test_write_log_includes_conflicts_and_unknown_stores_when_present(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    now = datetime(2026, 8, 11, 9, 30, 3)

    stats = _stats(
        conflict_count=1,
        conflict_list=[{"ячейка": "B2", "текст": "фм 4 фм 42", "маршруты": ["Маршрут №1", "Маршрут №2"]}],
        unknown_stores=["Неизвестный магазин"],
    )

    log_file = write_log("11.08.26", now, "a.xlsx", "out.xlsx", stats)
    text = open(log_file, encoding="utf-8").read()

    assert "Ошибочные адреса:" in text
    assert "B2 | фм 4 фм 42 | ['Маршрут №1', 'Маршрут №2']" in text
    assert "Неизвестные магазины:" in text
    assert "Неизвестный магазин" in text
