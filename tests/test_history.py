import json
from datetime import datetime

import pytest

from modules import history, paths


@pytest.fixture(autouse=True)
def _isolated_data_dir(tmp_path, monkeypatch):
    """Уводит историю во временную папку, чтобы тесты не трогали data/."""

    monkeypatch.setattr(paths, "PROCESSED_FILES_FILE", tmp_path / "processed_files.json")
    monkeypatch.setattr(paths, "VOLUME_HISTORY_FILE", tmp_path / "volume_history.json")
    monkeypatch.setattr(history, "PROCESSED_FILES_FILE", tmp_path / "processed_files.json")
    monkeypatch.setattr(history, "VOLUME_HISTORY_FILE", tmp_path / "volume_history.json")


def test_load_returns_empty_when_files_are_missing():
    assert history.load_processed_files() == {}
    assert history.load_volume_history() == []


def test_load_survives_broken_json():
    history.PROCESSED_FILES_FILE.write_text("{не json", encoding="utf-8")
    history.VOLUME_HISTORY_FILE.write_text("[не json", encoding="utf-8")

    assert history.load_processed_files() == {}
    assert history.load_volume_history() == []


def test_save_processed_file_keeps_previous_entries():
    history.save_processed_file("первый.xlsx")
    history.save_processed_file("второй.xlsx")

    data = history.load_processed_files()

    assert set(data) == {"первый.xlsx", "второй.xlsx"}


def test_save_volume_record_writes_totals_per_route():
    history.save_volume_record([100, 200, 300, 400])

    records = history.load_volume_history()

    assert len(records) == 1
    assert records[0]["route_1"] == 100
    assert records[0]["route_4"] == 400
    assert "date" in records[0]


def test_save_volume_record_pads_missing_routes():
    """Маршрутов может прийти меньше четырёх — остальные должны стать нулями."""

    history.save_volume_record([50])

    record = history.load_volume_history()[0]

    assert record["route_1"] == 50
    assert record["route_2"] == 0
    assert record["route_4"] == 0


def test_record_processing_writes_both_files():
    """Главное, ради чего заведён общий модуль: объём пишется вместе с историей.

    Раньше объём сохранял только веб-дашборд, поэтому обработка из консоли
    или tkinter не попадала в график.
    """

    stats = {"route_totals": {"Маршрут №1": 10, "Маршрут №2": 20, "Маршрут №3": 30, "Маршрут №4": 40}}

    history.record_processing("заказ.xlsx", stats)

    assert "заказ.xlsx" in history.load_processed_files()

    record = history.load_volume_history()[0]
    assert record["route_1"] == 10
    assert record["route_3"] == 30


def _stats(*totals):
    return {"route_totals": dict(zip(["Маршрут №1", "Маршрут №2", "Маршрут №3", "Маршрут №4"], totals))}


def test_reprocessing_does_not_duplicate_volume():
    """Повторная обработка того же файла не должна удваивать объём.

    Из-за этого график «Вывезенный объём» показывал завышенные суммы:
    каждая запись просто добавлялась в конец списка.
    """

    history.record_processing("заказ.xlsx", _stats(100, 200, 300, 400))
    history.record_processing("заказ.xlsx", _stats(100, 200, 300, 400))

    records = history.load_volume_history()

    assert len(records) == 1
    assert records[0]["route_1"] == 100


def test_reprocessing_updates_totals_in_place():
    """Повтор — это исправление: суммы заменяются, а не складываются."""

    history.record_processing("заказ.xlsx", _stats(100, 200, 300, 400))
    history.record_processing("заказ.xlsx", _stats(11, 22, 33, 44))

    records = history.load_volume_history()

    assert len(records) == 1
    assert records[0]["route_1"] == 11
    assert records[0]["route_4"] == 44


def test_reprocessing_keeps_original_date():
    """Дата первой обработки не должна съезжать на день повторного прогона."""

    history.record_processing("заказ.xlsx", _stats(1, 2, 3, 4))
    first_date = history.load_volume_history()[0]["date"]

    history.record_processing("заказ.xlsx", _stats(9, 9, 9, 9))

    records = history.load_volume_history()

    assert len(records) == 1
    assert records[0]["date"] == first_date


def test_different_files_are_recorded_separately():
    history.record_processing("первый.xlsx", _stats(1, 1, 1, 1))
    history.record_processing("второй.xlsx", _stats(2, 2, 2, 2))

    assert len(history.load_volume_history()) == 2


def test_reprocessing_keeps_first_processing_time(monkeypatch):
    """Повтор не переносит старый заказ в «сегодня» — счётчик за день не растёт.

    Время подменяется явно: обе записи иначе попадают в одну секунду и
    тест проходил бы даже со сломанным кодом.
    """

    class _FakeDatetime:
        current = datetime(2026, 8, 1, 10, 0, 0)

        @classmethod
        def now(cls):
            return cls.current

    monkeypatch.setattr(history, "datetime", _FakeDatetime)

    history.save_processed_file("заказ.xlsx")
    assert history.load_processed_files()["заказ.xlsx"] == "2026-08-01 10:00:00"

    _FakeDatetime.current = datetime(2026, 8, 20, 15, 30, 0)
    history.save_processed_file("заказ.xlsx")

    assert history.load_processed_files()["заказ.xlsx"] == "2026-08-01 10:00:00"


def test_was_processed_reports_known_files():
    assert history.was_processed("заказ.xlsx") == ""

    history.save_processed_file("заказ.xlsx")

    assert history.was_processed("заказ.xlsx")
    assert history.was_processed("другой.xlsx") == ""


def test_legacy_records_without_file_are_left_alone():
    """В истории уже есть записи, сделанные до появления поля file."""

    history.VOLUME_HISTORY_FILE.write_text(
        json.dumps([{"date": "2026-08-12", "route_1": 5, "route_2": 0, "route_3": 0, "route_4": 0}]),
        encoding="utf-8",
    )

    history.record_processing("новый.xlsx", _stats(1, 2, 3, 4))

    records = history.load_volume_history()

    assert len(records) == 2
    assert records[0]["route_1"] == 5


def test_record_processing_creates_parent_directory(tmp_path, monkeypatch):
    """Папки data/ может ещё не быть — запись не должна падать."""

    target = tmp_path / "нет-такой-папки" / "processed_files.json"
    monkeypatch.setattr(history, "PROCESSED_FILES_FILE", target)
    monkeypatch.setattr(history, "VOLUME_HISTORY_FILE", target.parent / "volume_history.json")

    history.record_processing("заказ.xlsx", {"route_totals": {}})

    assert json.loads(target.read_text(encoding="utf-8"))
