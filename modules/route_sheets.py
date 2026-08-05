import re

from openpyxl.utils import get_column_letter


SUM_HEADER = "Сумма"


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


def add_sum_column_to_all_sheets(wb):
    """Adds or updates the row sum column on every worksheet."""

    for ws in wb.worksheets:
        _add_sum_column(ws)


def _add_sum_column(ws):
    """Adds or updates the row sum column as the second worksheet column."""

    if not _has_sum_column(ws):
        ws.insert_cols(2)

    ws.cell(row=1, column=2, value=SUM_HEADER)

    last_col = _last_used_column(ws)

    for row in range(2, ws.max_row + 1):

        if last_col >= 3:
            ws.cell(
                row=row,
                column=2,
                value=f"=SUM(C{row}:{get_column_letter(last_col)}{row})",
            )
        else:
            ws.cell(row=row, column=2, value=None)


def _has_sum_column(ws):
    """Checks whether column B already contains the sum column."""

    header = str(ws.cell(row=1, column=2).value or "").strip().lower()

    if header == SUM_HEADER.lower():
        return True

    for row in range(2, ws.max_row + 1):
        value = ws.cell(row=row, column=2).value

        if isinstance(value, str) and value.strip().upper().startswith("=SUM("):
            return True

    return False


def _last_used_column(ws):
    """Returns the rightmost column that has a non-empty cell."""

    for col in range(ws.max_column, 2, -1):
        for row in range(1, ws.max_row + 1):
            if ws.cell(row=row, column=col).value is not None:
                return col

    return 2
