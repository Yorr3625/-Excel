from datetime import datetime

from openpyxl import load_workbook

from modules.config import load_settings, load_stores, build_groups
from modules.styles import (
    green_fill,
    yellow_fill,
    blue_fill,
    purple_fill,
    conflict_fill,
)
from modules.file_selector import select_order_file
from modules.excel_cleaner import remove_unused_rows_and_cols, delete_columns_by_text
from modules.route_finder import find_and_mark_routes
from modules.route_sheets import create_route_sheets
from modules.output_writer import build_output_path, open_result
from modules.logger import write_log
from modules.reporter import print_summary


# тексты, по которым нужно удалять целые столбцы
DELETE_TEXT = [
    "Ищенко БЕЗ НДС",
]


def main():

    settings = load_settings()
    input_file = select_order_file()

    stores = load_stores()
    fills = [green_fill, yellow_fill, blue_fill, purple_fill]
    groups = build_groups(stores, fills)

    wb = load_workbook(input_file)
    ws = wb.active

    # очистка исходных данных
    remove_unused_rows_and_cols(ws)
    delete_columns_by_text(ws, DELETE_TEXT)

    # поиск и раскраска адресов по маршрутам
    stats = find_and_mark_routes(ws, groups, conflict_fill)

    # сохранение результата
    now = datetime.now()
    output_file, date_folder = build_output_path(now)

    create_route_sheets(wb, ws, groups)
    wb.save(output_file)

    open_result(output_file, settings)

    # лог и вывод в консоль
    log_file = write_log(date_folder, now, input_file, output_file, stats)
    print_summary(output_file, stats, log_file)


if __name__ == "__main__":
    main()
