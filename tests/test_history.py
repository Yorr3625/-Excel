import json

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


def test_record_processing_creates_parent_directory(tmp_path, monkeypatch):
    """Папки data/ может ещё не быть — запись не должна падать."""

    target = tmp_path / "нет-такой-папки" / "processed_files.json"
    monkeypatch.setattr(history, "PROCESSED_FILES_FILE", target)
    monkeypatch.setattr(history, "VOLUME_HISTORY_FILE", target.parent / "volume_history.json")

    history.record_processing("заказ.xlsx", {"route_totals": {}})

    assert json.loads(target.read_text(encoding="utf-8"))
