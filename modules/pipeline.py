from datetime import datetime

from openpyxl import load_workbook

from modules.excel_cleaner import (
    remove_unused_rows_and_cols,
    delete_columns_by_text,
    delete_total_rows,
)
from modules.route_finder import find_and_mark_routes
from modules.route_sheets import create_route_sheets, add_sum_column_to_all_sheets
from modules.output_writer import build_output_path, open_result
from modules.logger import write_log


# тексты, по которым нужно удалять целые столбцы
DELETE_TEXT = [
    "Ищенко БЕЗ НДС",
]


def process_order(input_file, settings, groups, conflict_fill):
    """
    Выполняет полный цикл обработки одного файла заказа:
    очистка данных -> поиск и раскраска маршрутов -> создание листов
    по маршрутам -> сохранение файла -> запись лога.

    Возвращает (output_file, log_file, stats).
    """

    wb = load_workbook(input_file)
    ws = wb.active

    remove_unused_rows_and_cols(ws)
    delete_columns_by_text(ws, DELETE_TEXT)
    delete_total_rows(ws)

    stats = find_and_mark_routes(ws, groups, conflict_fill)

    now = datetime.now()
    output_file, date_folder = build_output_path(now)

    create_route_sheets(wb, ws, groups)
    route_totals = add_sum_column_to_all_sheets(wb)
    stats["route_totals"] = route_totals
    wb.save(output_file)

    open_result(output_file, settings)

    log_file = write_log(date_folder, now, input_file, output_file, stats)

    return output_file, log_file, stats
