"""Наименования товаров из файла заказа — для автоподсказки во вкладке «Вес».

Наименование всегда в первом столбце листа заказа и не меняется всей
остальной обработкой (pipeline.py/route_sheets.py оставляют его нетронутым
при разбивке по маршрутам), поэтому его можно читать прямо из исходного
файла в data/orders, не запуская обработку. Переиспользует ту же чистку
шапки/итоговой строки, что и pipeline.prepare_order, — только без поиска
маршрутов, он тут не нужен.
"""

from modules.excel_cleaner import delete_total_rows, remove_unused_rows_and_cols
from modules.excel_io import load_workbook
from modules.paths import ORDERS_FOLDER


def order_position_names(filename: str) -> list[str]:
    """Наименования товаров из заказа filename, без повторов, по порядку строк.

    Возвращает [] если файл не указан, не найден или не открылся — тогда
    во вкладке «Вес» просто не будет автоподсказки, без падения интерфейса.
    """

    filename = (filename or "").strip()
    if not filename:
        return []

    path = ORDERS_FOLDER / filename
    if not path.exists():
        return []

    try:
        workbook = load_workbook(path)
        sheet = workbook.active
        remove_unused_rows_and_cols(sheet)
        delete_total_rows(sheet)
    except Exception:
        return []

    names = []
    seen = set()

    for (value,) in sheet.iter_rows(min_row=2, min_col=1, max_col=1, values_only=True):
        if not value:
            continue

        name = str(value).strip()
        key = name.casefold()

        if not name or key in seen:
            continue

        seen.add(key)
        names.append(name)

    return names
