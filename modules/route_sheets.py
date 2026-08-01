import re

from openpyxl.utils import get_column_letter


def create_route_sheets(wb, ws, groups):
    """
    Для каждой группы (маршрута) создаёт отдельный лист-копию исходного
    листа, оставляя только столбцы, относящиеся к этому маршруту,
    и добавляет колонку "Сумма" с формулой SUM по строке.
    """

    for group in groups:

        route_name = group["name"]
        stores = group["names"]

        # копируем весь лист
        new_ws = wb.copy_worksheet(ws)
        new_ws.title = route_name

        delete_columns = _find_columns_to_delete(new_ws, stores)

        # удаляем справа налево, чтобы номера столбцов не сбились
        for col in sorted(delete_columns, reverse=True):
            new_ws.delete_cols(col)

        _add_sum_column(new_ws)


def _find_columns_to_delete(ws, stores):
    """Определяет столбцы, не относящиеся к данному маршруту (кроме 1-го)."""

    delete_columns = []

    # начинаем со 2-го столбца - первый оставляем всегда
    for col in range(2, ws.max_column + 1):

        header = str(ws.cell(1, col).value or "").lower()
        is_route_column = False

        for store in stores:

            pattern = r"\b" + re.escape(store.lower()) + r"\b"

            if re.search(pattern, header):
                is_route_column = True
                break

        if not is_route_column:
            delete_columns.append(col)

    return delete_columns


def _add_sum_column(ws):
    """Вставляет колонку "Сумма" вторым столбцом с формулой SUM по строке."""

    ws.insert_cols(2)
    ws.cell(row=1, column=2, value="Сумма")

    for row in range(2, ws.max_row + 1):

        last_col = ws.max_column

        if last_col >= 3:
            ws.cell(
                row=row,
                column=2,
                value=f"=SUM(C{row}:{get_column_letter(last_col)}{row})",
            )
