from colorama import init, Fore, Style

init(autoreset=True)


def _format_preview_number(value):
    return f"{value:,.0f}".replace(",", " ")


def _format_file_size(value):
    size = float(value or 0)

    for unit in ("Б", "КБ", "МБ", "ГБ"):
        if size < 1024 or unit == "ГБ":
            return f"{int(size)} {unit}" if unit == "Б" else f"{size:.1f} {unit}"
        size /= 1024

    return "0 Б"


def format_preview(preview):
    """Формирует текст предварительного просмотра без побочных эффектов."""

    lines = [
        "ПРЕДВАРИТЕЛЬНЫЙ ПРОСМОТР",
        "=" * 35,
        f"Файл: {preview['file_name']}",
        f"Формат и размер: {preview['file_extension']}, "
        f"{_format_file_size(preview['file_size'])}",
        f"Лист: {preview['sheet_name']} (листов в книге: {preview['sheet_count']})",
        f"Тип: {preview['document_type']}",
        f"Режим: {preview.get('mode') or 'не указан'}",
        f"Строк заказа: {preview['order_rows']}",
        f"Найдено совпадений: {preview['total_found']}",
        "",
        "ИТОГИ ПО МАРШРУТАМ",
    ]

    for route in preview["route_rows"]:
        lines.append(
            f"{route['name']}: "
            f"строк — {route['rows']}, "
            f"совпадений — {route['matches']}, "
            f"объём — {_format_preview_number(route['total'])}"
        )

        if route.get("stores"):
            lines.append(f"  Магазины: {', '.join(route['stores'])}")

    lines.extend(
        [
            f"Общий объём: {_format_preview_number(preview['grand_total'])}",
            f"Конфликтов: {preview['conflict_count']}",
            f"Неизвестных магазинов: {len(preview['unknown_stores'])}",
        ]
    )

    warnings = preview.get("warnings", [])

    if warnings:
        lines.extend(["", "ПРЕДУПРЕЖДЕНИЯ:"])
        lines.extend(f"⚠ {warning}" for warning in warnings)

    if preview.get("unknown_stores"):
        lines.extend(["", "Неизвестные магазины:"])
        lines.extend(f"- {store}" for store in preview["unknown_stores"])

    if preview.get("conflicts"):
        lines.extend(["", "Конфликтующие адреса:"])
        lines.extend(
            f"- {item['cell']} | {item['text']} | {', '.join(item['routes'])}"
            for item in preview["conflicts"]
        )

    lines.extend(["", "Для запуска обработки требуется явное подтверждение."])

    return "\n".join(lines)


def format_summary(output_file, stats, log_file):
    """Формирует текст итоговой сводки по результатам обработки."""

    lines = []

    lines.append(f"Создан файл: {output_file}")

    lines.append("")
    lines.append("Найдено адресов:")

    for route, count in stats["route_count"].items():
        lines.append(f"{route}: {count}")

    if "route_totals" in stats:

        lines.append("")
        lines.append("=" * 35)
        lines.append("      ИТОГИ ПО МАРШРУТАМ")
        lines.append("=" * 35)

        grand_total = sum(stats["route_totals"].values())

        for route, total in stats["route_totals"].items():

            percent = (
                total / grand_total * 100
                if grand_total > 0
                else 0
            )

            lines.append(
                f"{route}: "
                f"{total:,.0f}".replace(",", " ")
                + f" ({percent:.1f}%)"
            )

        lines.append("=" * 35)
        lines.append(
            f"Общий итог: {grand_total:,.0f}".replace(",", " ")
        )

    lines.append("")
    lines.append(f"Конфликтов найдено: {stats['conflict_count']}")
    lines.append(f"Неизвестных магазинов: {len(stats['unknown_stores'])}")

    if stats["unknown_stores"]:

        lines.append("")
        lines.append("Неизвестные магазины:")

        for store in stats["unknown_stores"]:
            lines.append(store)

    if stats["conflict_count"]:

        lines.append("")
        lines.append("Ошибочные адреса:")

        for item in stats["conflict_list"]:
            lines.append(
                f'{item["ячейка"]} | {item["текст"]} | {item["маршруты"]}'
            )

    lines.append("")
    lines.append(f"Лог сохранён: {log_file}")

    return "\n".join(lines)


def print_summary(output_file, stats, log_file):

    text = format_summary(
        output_file,
        stats,
        log_file
    )

    route_header = (
        "=" * 35 + "\n"
        + "      ИТОГИ ПО МАРШРУТАМ\n"
        + "=" * 35
    )

    green_route_header = (
        Fore.GREEN + "=" * 35 + Style.RESET_ALL + "\n"
        + Fore.GREEN + "      ИТОГИ ПО МАРШРУТАМ" + Style.RESET_ALL + "\n"
        + Fore.GREEN + "=" * 35 + Style.RESET_ALL
    )

    text = text.replace(
        route_header,
        green_route_header
    )

    print(
        Fore.GREEN +
        "==================================="
    )
    print(
        Fore.GREEN +
        "      ОБРАБОТКА ЗАВЕРШЕНА"
    )
    print(
        Fore.GREEN +
        "==================================="
    )

    print()
    print(text)