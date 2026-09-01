"""Учёт веса позиций: наименование, ящики, средний и точный вес.

Хранится отдельной книгой data/weight_log.xlsx, а не в файлах заказов —
записи не связаны с конкретной обработкой и их удобно открыть и поправить
вручную в Excel. Колонка ID скрыта от пользователя и нужна только для того,
чтобы удалить конкретную строку, даже если несколько позиций совпадают по
названию.
"""

import uuid
from datetime import datetime

from openpyxl import Workbook, load_workbook

from modules.paths import WEIGHT_LOG_FILE

COLUMNS = (
    "ID",
    "Дата",
    "Наименование",
    "Кол-во ящиков",
    "Средний вес ящика, кг",
    "Точный вес, кг",
    "Итого, кг",
    "Заказ",
    "Маршрут",
)


def _open_workbook():
    if WEIGHT_LOG_FILE.exists():
        return load_workbook(WEIGHT_LOG_FILE)

    workbook = Workbook()
    workbook.active.title = "Вес"
    workbook.active.append(COLUMNS)
    return workbook


def _save_workbook(workbook) -> None:
    WEIGHT_LOG_FILE.parent.mkdir(parents=True, exist_ok=True)
    workbook.save(WEIGHT_LOG_FILE)


def load_weight_rows() -> list[dict]:
    """Записи из data/weight_log.xlsx в порядке добавления."""

    if not WEIGHT_LOG_FILE.exists():
        return []

    sheet = load_workbook(WEIGHT_LOG_FILE).active
    rows = []

    for row in sheet.iter_rows(min_row=2, values_only=True):
        row_id, date, name, box_count, avg_weight, exact_weight, total = row[:7]
        order_file, route = (row[7:9] + (None, None))[:2]

        if row_id is None:
            continue

        rows.append(
            {
                "id": row_id,
                "date": date or "",
                "name": name or "",
                "box_count": box_count or 0,
                "avg_weight": avg_weight or 0,
                "exact_weight": exact_weight,
                "total": total or 0,
                "order_file": order_file or "",
                "route": route or "",
            }
        )

    return rows


def add_weight_row(
    name: str,
    box_count: float,
    avg_weight: float,
    exact_weight: float | None,
    order_file: str = "",
    route: str = "",
) -> dict:
    """Добавляет строку и возвращает её.

    Итог — это точный вес, если позицию взвесили, иначе кол-во ящиков,
    умноженное на средний вес ящика. order_file и route — необязательная
    привязка к обработанному заказу и маршруту, для группировки записей.
    """

    entry = {
        "id": uuid.uuid4().hex,
        "date": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "name": name,
        "box_count": box_count,
        "avg_weight": avg_weight,
        "exact_weight": exact_weight,
        "total": exact_weight if exact_weight is not None else box_count * avg_weight,
        "order_file": order_file,
        "route": route,
    }

    workbook = _open_workbook()
    workbook.active.append(
        [
            entry["id"],
            entry["date"],
            entry["name"],
            entry["box_count"],
            entry["avg_weight"],
            entry["exact_weight"],
            entry["total"],
            entry["order_file"],
            entry["route"],
        ]
    )
    _save_workbook(workbook)

    return entry


def delete_weight_row(row_id: str) -> None:
    """Удаляет строку по id, если она есть в книге."""

    if not WEIGHT_LOG_FILE.exists():
        return

    workbook = _open_workbook()
    sheet = workbook.active

    for row in sheet.iter_rows(min_row=2):
        if row[0].value == row_id:
            sheet.delete_rows(row[0].row)
            _save_workbook(workbook)
            return


def update_weight_row(
    row_id: str,
    name: str,
    box_count: float,
    avg_weight: float,
    exact_weight: float | None,
    order_file: str = "",
    route: str = "",
) -> dict | None:
    """Обновляет существующую строку по id и возвращает её новую версию.

    Дата и id исходной записи сохраняются. Возвращает None, если строка не
    найдена. Пишет через sheet.cell(...) вместо ячеек из iter_rows — так
    правка не падает на книге, сохранённой до появления колонок Заказ и
    Маршрут (в ней короче строк, чем ожидает текущая схема).
    """

    if not WEIGHT_LOG_FILE.exists():
        return None

    workbook = _open_workbook()
    sheet = workbook.active

    for row in sheet.iter_rows(min_row=2):
        if row[0].value != row_id:
            continue

        row_number = row[0].row
        total = exact_weight if exact_weight is not None else box_count * avg_weight
        date = sheet.cell(row=row_number, column=2).value

        sheet.cell(row=row_number, column=3, value=name)
        sheet.cell(row=row_number, column=4, value=box_count)
        sheet.cell(row=row_number, column=5, value=avg_weight)
        sheet.cell(row=row_number, column=6, value=exact_weight)
        sheet.cell(row=row_number, column=7, value=total)
        sheet.cell(row=row_number, column=8, value=order_file)
        sheet.cell(row=row_number, column=9, value=route)
        _save_workbook(workbook)

        return {
            "id": row_id,
            "date": date or "",
            "name": name,
            "box_count": box_count,
            "avg_weight": avg_weight,
            "exact_weight": exact_weight,
            "total": total,
            "order_file": order_file,
            "route": route,
        }

    return None


def last_avg_weight_for(name: str) -> float | None:
    """Средний вес ящика из самой последней записи с таким наименованием.

    Подсказка для формы: одно и то же наименование часто взвешивают
    регулярно, и вспоминать вес ящика каждый раз заново неудобно.
    """

    normalized = name.strip().lower()
    if not normalized:
        return None

    match = None
    for row in load_weight_rows():
        if row["name"].strip().lower() == normalized:
            match = row

    return match["avg_weight"] if match else None
