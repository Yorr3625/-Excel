import os
import json

def load_settings():

    with open(
        "settings.json",
        "r",
        encoding="utf-8"
    ) as file:

        return json.load(file)

ORDERS_FOLDER = "Заказы"


def select_order_file():

    # создаём папку если её нет
    if not os.path.exists(ORDERS_FOLDER):

        os.makedirs(ORDERS_FOLDER)


    files = []


    for file in os.listdir(ORDERS_FOLDER):

        if file.endswith((".xlsx", ".xlsm")):

            files.append(file)



    if not files:

        print("В папке 'Заказы' нет файлов Excel")
        input("Нажмите Enter для выхода...")
        exit()



    print("\nДоступные заказы:\n")


    for i, file in enumerate(files, start=1):

        print(f"{i}. {file}")



    while True:

        try:

            choice = int(
                input("\nВыберите номер файла: ")
            )


            if 1 <= choice <= len(files):

                selected = files[choice - 1]

                return os.path.join(
                    ORDERS_FOLDER,
                    selected
                )


        except ValueError:

            pass


        print("Неверный выбор, попробуйте снова")

import json
import os
import re
from datetime import datetime
from route_sheets import create_route_sheets
from openpyxl import load_workbook

from routes import (
    green_fill,
    yellow_fill,
    blue_fill,
    purple_fill,
    conflict_fill
)


# ==========================
# НАСТРОЙКИ
# ==========================

input_file = select_order_file()


# ==========================
# ЗАГРУЗКА СПИСКОВ
# ==========================

with open("stores.json", "r", encoding="utf-8") as f:
    routes = json.load(f)


groups = [
    {
        "name": "Маршрут №1",
        "names": routes["route_1"],
        "fill": green_fill
    },
    {
        "name": "Маршрут №2",
        "names": routes["route_2"],
        "fill": yellow_fill
    },
    {
        "name": "Маршрут №3",
        "names": routes["route_3"],
        "fill": blue_fill
    },
    {
        "name": "Маршрут №4",
        "names": routes["route_4"],
        "fill": purple_fill
    }
]


# ==========================
# ОТКРЫТИЕ EXCEL
# ==========================

wb = load_workbook(input_file)
ws = wb.active


# ==========================
# УДАЛЕНИЕ НЕНУЖНЫХ ДАННЫХ
# ==========================

# удалить строку №2
ws.delete_rows(2)

# удалить столбцы №2 и №3
ws.delete_cols(2, 2)

# ==========================
# УДАЛЕНИЕ СТОЛБЦОВ ПО ТЕКСТУ
# ==========================

delete_text = [
    "Ищенко БЕЗ НДС"
]


cols_to_delete = []


for row in ws.iter_rows():

    for cell in row:

        if cell.value:

            value = str(cell.value).lower()

            for text in delete_text:

                if text.lower() in value:

                    cols_to_delete.append(cell.column)
                    break


# удаляем с конца, чтобы номера столбцов не сбились
for col_num in sorted(set(cols_to_delete), reverse=True):

    ws.delete_cols(col_num)
# ==========================
# СЧЕТЧИКИ
# ==========================

conflict_count = 0

route_count = {
    "Маршрут №1": 0,
    "Маршрут №2": 0,
    "Маршрут №3": 0,
    "Маршрут №4": 0
}

conflict_list = []

total_found = 0


# ==========================
# ПОИСК АДРЕСОВ
# ==========================

for row in ws.iter_rows():

    for cell in row:

        text = str(cell.value or "").lower()

        matches = []


        for group in groups:

            for name in group["names"]:

                name = name.lower()

                # защита от ФМ 4 -> ФМ 42
                pattern = r'\b' + re.escape(name) + r'\b'


                if re.search(pattern, text):

                    matches.append(group)
                    break



        # один маршрут
        if len(matches) == 1:

            cell.fill = matches[0]["fill"]

            route_count[matches[0]["name"]] += 1

            total_found += 1



        # конфликт
        elif len(matches) > 1:

            cell.fill = conflict_fill

            conflict_count += 1

            conflict_list.append(
                {
                    "ячейка": cell.coordinate,
                    "текст": cell.value,
                    "маршруты": [
                        x["name"] for x in matches
                    ]
                }
            )


def create_route_sheets(wb, ws, groups):

    import re


    for group in groups:

        route_name = group["name"]
        stores = group["names"]


        # копируем весь лист
        new_ws = wb.copy_worksheet(ws)

        new_ws.title = route_name


        delete_columns = []


        # начинаем с 2-го столбца!
        # первый столбец оставляем всегда
        for col in range(2, new_ws.max_column + 1):

            header = str(
                new_ws.cell(1, col).value or ""
            ).lower()


            is_route = False


            for store in stores:

                pattern = (
                    r'\b'
                    + re.escape(store.lower())
                    + r'\b'
                )


                if re.search(pattern, header):

                    is_route = True
                    break


            # если это столбец другого маршрута
            if not is_route:

                delete_columns.append(col)



        # удаляем справа налево
        for col in sorted(delete_columns, reverse=True):

            new_ws.delete_cols(col)

        # ==========================
        # ДОБАВЛЯЕМ КОЛОНКУ СУММА
        # ==========================

        new_ws.insert_cols(2)

        new_ws.cell(
            row=1,
            column=2,
            value="Сумма"
        )


        from openpyxl.utils import get_column_letter


        # формула SUM по горизонтали
        for row in range(2, new_ws.max_row + 1):

            last_col = new_ws.max_column


            if last_col >= 3:

                new_ws.cell(
                    row=row,
                    column=2,
                    value=(
                        f"=SUM(C{row}:"
                        f"{get_column_letter(last_col)}{row})"
                    )
                )


# ==========================
# СОХРАНЕНИЕ ГОТОВОГО ФАЙЛА
# ==========================

now = datetime.now()

date_folder = now.strftime("%d.%m.%y")
time_file = now.strftime("%H-%M-%S")


output_folder = os.path.join(
    "готовые_заказы",
    date_folder
)


os.makedirs(
    output_folder,
    exist_ok=True
)


output_file = os.path.join(
    output_folder,
    f"заказ_обработан_{time_file}.xlsx"
)


# создаём листы маршрутов
create_route_sheets(
    wb,
    ws,
    groups
)


# сохраняем файл
wb.save(output_file)

import os


settings = load_settings()


if settings["open_file_after_processing"]:

    os.startfile(output_file)



elif settings["open_folder_after_processing"]:

    os.startfile(
        os.path.dirname(output_file)
    )

# ==========================
# ЛОГИ
# ==========================

log_folder = os.path.join(
    "логи",
    date_folder
)


os.makedirs(
    log_folder,
    exist_ok=True
)


log_file = os.path.join(
    log_folder,
    "лог.txt"
)



with open(log_file, "a", encoding="utf-8") as log:

    log.write("\n\n")
    log.write("==============================\n")
    log.write(
        f"ОБРАБОТКА {now.strftime('%H:%M:%S')}\n"
    )
    log.write("==============================\n\n")


    log.write(
        f"Дата: {now.strftime('%d.%m.%Y %H:%M:%S')}\n"
    )

    log.write(
        f"Файл: {input_file}\n"
    )

    log.write(
        f"Результат: {output_file}\n\n"
    )


    log.write("Найдено адресов:\n")


    for route, count in route_count.items():

        log.write(
            f"{route}: {count}\n"
        )


    log.write(
        f"\nВсего найдено: {total_found}\n"
    )


    log.write(
        f"Конфликтов: {conflict_count}\n"
    )


    if conflict_count > 0:

        log.write(
            "\nОшибочные адреса:\n"
        )


        for item in conflict_list:

            log.write(
                f'{item["ячейка"]} | '
                f'{item["текст"]} | '
                f'{item["маршруты"]}\n'
            )


# ==========================
# ВЫВОД
# ==========================

print("======================")
print("Обработка завершена")
print("======================")

print(f"Создан файл: {output_file}")

print()
print("Найдено адресов:")

for route, count in route_count.items():
    print(f"{route}: {count}")

print()
print(f"Конфликтов найдено: {conflict_count}")

if conflict_count:

    print()
    print("Ошибочные адреса:")

    for item in conflict_list:

        print(
            f'{item["ячейка"]} | '
            f'{item["текст"]} | '
            f'{item["маршруты"]}'
        )


print()
print(f"Лог сохранён: {log_file}")