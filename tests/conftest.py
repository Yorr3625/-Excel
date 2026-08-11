import pytest
from openpyxl import Workbook

from modules.styles import green_fill, yellow_fill, conflict_fill

__all__ = ["groups", "sample_order_workbook"]


@pytest.fixture
def groups():
    """Два маршрута с именами магазинов, взятыми из реального stores.json
    (в т.ч. пара "фм 4" / "фм 42", проверяющая совпадение по целому слову)."""

    return [
        {"name": "Маршрут №1", "names": ["фм 4", "м1"], "fill": green_fill},
        {"name": "Маршрут №2", "names": ["фм 42", "м2"], "fill": yellow_fill},
    ]


@pytest.fixture
def sample_order_workbook():
    """Строит книгу с шапкой заказа: колонка товара + по колонке на магазин
    каждого маршрута, плюс служебные строки/столбцы, встречающиеся в реальных
    файлах заказа (строка №2, столбцы №2-3, строка "Итого")."""

    wb = Workbook()
    ws = wb.active

    ws.append(["Товар", "служебный1", "служебный2", "фм 4", "фм 42"])
    ws.append(["служебная строка", "", "", "", ""])
    ws.append(["Товар A", "", "", 5, 3])
    ws.append(["Товар B", "", "", 0, 2])
    ws.append(["Итого", "", "", 5, 5])

    return wb
