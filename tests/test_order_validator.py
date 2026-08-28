import json

import pytest
from openpyxl import Workbook

from modules import order_validator, paths


def test_all_excel_book_suffixes_are_allowed():
    for suffix in (".xlsx", ".xlsm", ".xlsb", ".xls", ".xltx", ".xltm"):
        assert suffix in order_validator.ALLOWED_SUFFIXES

    assert ".csv" not in order_validator.ALLOWED_SUFFIXES


STORES = {
    "route_1": ["фм 10", "фм 14", "фм 17"],
    "route_2": ["фм 13", "фм 32"],
    "route_3": [],
    "route_4": [],
}


@pytest.fixture(autouse=True)
def _stores_in_tmp(tmp_path, monkeypatch):
    """Подкладывает справочник магазинов во временную папку."""

    city = tmp_path / "stores_city.json"
    region = tmp_path / "stores_region.json"

    city.write_text(json.dumps({k: [] for k in STORES}, ensure_ascii=False), encoding="utf-8")
    region.write_text(json.dumps(STORES, ensure_ascii=False), encoding="utf-8")

    monkeypatch.setattr(
        order_validator,
        "stores_file_for",
        lambda mode: city if mode == "Город" else region,
    )


def _order_file(tmp_path, stores, name="заказ.xlsx"):
    """Файл со структурой настоящего заказа.

    Пайплайн безусловно вырезает строку №2 и столбцы №2-3 как служебные,
    поэтому магазины должны начинаться с четвёртого столбца — иначе часть
    из них не доживёт до сопоставления.
    """

    wb = Workbook()
    ws = wb.active

    ws.append(["Товар", "служебный1", "служебный2", *stores])
    ws.append(["служебная строка", "", "", *[""] * len(stores)])
    ws.append(["Товар A", "", "", *[1] * len(stores)])

    path = tmp_path / name
    wb.save(path)
    return path


def test_real_order_is_accepted(tmp_path):
    path = _order_file(tmp_path, ["фм 10", "фм 14", "фм 17", "фм 13"])

    verdict = order_validator.validate_order_file(path)

    assert verdict["ok"]
    assert verdict["mode"] == "Область"
    assert verdict["matches"] >= 4
    assert verdict["reason"] == ""


def test_foreign_excel_is_rejected(tmp_path):
    """Главный сценарий: прислали Excel, но не заказ — обработка не должна пойти."""

    wb = Workbook()
    ws = wb.active
    ws.append(["Наименование", "Цена", "Количество"])
    ws.append(["Гвозди", 100, 5])
    ws.append(["Шурупы", 200, 3])

    path = tmp_path / "прайс.xlsx"
    wb.save(path)

    verdict = order_validator.validate_order_file(path)

    assert not verdict["ok"]
    assert "Не похоже на заказ" in verdict["reason"]
    assert verdict["matches"] == 0


def test_file_with_too_few_matches_is_rejected(tmp_path):
    """Одно случайное совпадение — ещё не заказ."""

    path = _order_file(tmp_path, ["фм 10"])

    verdict = order_validator.validate_order_file(path)

    assert not verdict["ok"]
    assert verdict["matches"] < order_validator.MIN_STORE_MATCHES


def test_corrupted_file_is_rejected_without_crash(tmp_path):
    """Битый файл с правильным расширением не должен ронять проверку."""

    path = tmp_path / "битый.xlsx"
    # начинается как zip (xlsx — это zip), но дальше мусор
    path.write_bytes(b"\x50\x4b\x03\x04" + b"not a real xlsx" * 10)

    verdict = order_validator.validate_order_file(path)

    assert not verdict["ok"]
    assert "повреждён" in verdict["reason"]


def test_wrong_extension_is_rejected(tmp_path):
    path = tmp_path / "документ.pdf"
    path.write_bytes(b"%PDF-1.4")

    verdict = order_validator.validate_order_file(path)

    assert not verdict["ok"]
    assert "Не Excel-файл" in verdict["reason"]


def test_empty_file_is_rejected(tmp_path):
    path = tmp_path / "пустой.xlsx"
    path.write_bytes(b"")

    verdict = order_validator.validate_order_file(path)

    assert not verdict["ok"]
    assert "пустой" in verdict["reason"]


def test_missing_file_is_rejected(tmp_path):
    verdict = order_validator.validate_order_file(tmp_path / "нет-такого.xlsx")

    assert not verdict["ok"]
    assert "не найден" in verdict["reason"].lower()


def test_oversized_file_is_rejected(tmp_path, monkeypatch):
    monkeypatch.setattr(order_validator, "MAX_FILE_MB", 0.0001)

    path = _order_file(tmp_path, ["фм 10", "фм 14", "фм 17"])

    verdict = order_validator.validate_order_file(path)

    assert not verdict["ok"]
    assert "слишком большой" in verdict["reason"]


def test_city_order_detects_city_mode(tmp_path, monkeypatch):
    """Режим определяется по тому, в каком справочнике больше совпадений."""

    city = tmp_path / "stores_city.json"
    city.write_text(
        json.dumps({"route_1": ["м1", "м2", "м3"], "route_2": [], "route_3": [], "route_4": []}),
        encoding="utf-8",
    )

    path = _order_file(tmp_path, ["м1", "м2", "м3"], name="город.xlsx")

    verdict = order_validator.validate_order_file(path)

    assert verdict["ok"]
    assert verdict["mode"] == "Город"
