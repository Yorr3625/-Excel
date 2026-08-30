"""Read-only analysis of an order before the processing pipeline runs."""

from pathlib import Path

from modules.pipeline import prepare_order
from modules.route_sheets import add_sum_column_to_all_sheets, create_route_sheets


class PreviewError(Exception):
    """Raised when an order cannot be loaded or analysed for preview."""


def _has_order_value(ws, row, first_order_column):
    """Return whether a cleaned row contains a value in an order column."""

    return any(
        ws.cell(row=row, column=column).value not in (None, "")
        for column in range(first_order_column, ws.max_column + 1)
    )


def _count_order_rows(ws):
    """Count rows that the route-sheet builder can retain as order rows."""

    if ws.max_column < 2:
        return 0

    return sum(
        _has_order_value(ws, row, 2)
        for row in range(2, ws.max_row + 1)
    )


def _count_route_rows(ws):
    """Count data rows retained on a generated route sheet."""

    count = 0

    for row in range(2, ws.max_row + 1):
        value = ws.cell(row=row, column=2).value

        if (
            isinstance(value, str)
            and value.strip().upper().startswith("=SUM(")
            and str(ws.cell(row=row, column=1).value or "").strip().upper()
            not in {"ИТОГО", "ИТОГ", "ВСЕГО"}
        ):
            count += 1

    return count


def _format_conflict(item):
    """Convert a route-finder conflict into data safe for all interfaces."""

    return {
        "cell": str(item.get("ячейка", "")),
        "text": str(item.get("текст", "")),
        "routes": [str(route) for route in item.get("маршруты", [])],
    }


def _build_warnings(stats, order_rows, grand_total):
    warnings = []

    if not stats["total_found"]:
        warnings.append("Не найдено совпадений с магазинами из выбранного режима.")

    if stats["conflict_count"]:
        warnings.append(
            f"Найдено конфликтующих адресов: {stats['conflict_count']}."
        )

    if stats["unknown_stores"]:
        warnings.append(
            "В шапке есть неизвестные магазины: "
            f"{len(stats['unknown_stores'])}."
        )

    if not order_rows:
        warnings.append("После очистки не найдено строк с заказом.")

    if not grand_total:
        warnings.append("Общий объём равен нулю или числовые значения не найдены.")

    return warnings


def build_order_preview(input_file, groups, conflict_fill, mode=""):
    """Build a serializable, side-effect-free summary of an order.

    The workbook is loaded and modified only in memory. The same preparation,
    route-sheet creation and total calculation used by ``process_order`` are
    reused, but no output file, log or history record is written.
    """

    try:
        input_path = Path(input_file)
        file_size = input_path.stat().st_size
        wb, ws, stats = prepare_order(input_path, groups, conflict_fill)
        source_sheet_count = len(wb.worksheets)
        order_rows = _count_order_rows(ws)

        create_route_sheets(wb, ws, groups)
        route_totals = add_sum_column_to_all_sheets(wb)
    except Exception as error:
        raise PreviewError(f"Не удалось построить предварительный просмотр: {error}") from error

    normalized_totals = {
        group["name"]: route_totals.get(group["name"], 0)
        for group in groups
    }
    grand_total = sum(normalized_totals.values())

    route_rows = []

    for group in groups:
        name = group["name"]
        route_sheet = wb[name]
        route_rows.append(
            {
                "name": name,
                "matches": int(stats["route_count"].get(name, 0)),
                "stores": list(stats.get("route_stores", {}).get(name, [])),
                "rows": _count_route_rows(route_sheet),
                "total": normalized_totals[name],
            }
        )

    conflicts = [_format_conflict(item) for item in stats["conflict_list"]]
    unknown_stores = [str(store) for store in stats["unknown_stores"]]

    return {
        "file_name": input_path.name,
        "file_extension": input_path.suffix.casefold() or "без расширения",
        "file_size": file_size,
        "sheet_name": ws.title,
        "sheet_count": source_sheet_count,
        "mode": mode,
        "document_type": "Похоже на Excel-заказ" if stats["total_found"] else "Заказ не подтверждён",
        "order_rows": order_rows,
        "total_found": int(stats["total_found"]),
        "route_rows": route_rows,
        "route_totals": normalized_totals,
        "grand_total": grand_total,
        "conflict_count": int(stats["conflict_count"]),
        "conflicts": conflicts,
        "unknown_stores": unknown_stores,
        "warnings": _build_warnings(stats, order_rows, grand_total),
    }
