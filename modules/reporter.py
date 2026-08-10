def format_summary(output_file, stats, log_file):
    """Формирует текст итоговой сводки по результатам обработки (без вывода)."""

    lines = []

    lines.append("======================")
    lines.append("Обработка завершена")
    lines.append("======================")
    lines.append(f"Создан файл: {output_file}")

    lines.append("")
    lines.append("Найдено адресов:")

    for route, count in stats["route_count"].items():
        lines.append(f"{route}: {count}")

    if "route_totals" in stats:

        lines.append("")
        lines.append("Суммы маршрутов:")

        grand_total = 0

        grand_total = 0

        for route, total in stats["route_totals"].items():

            if route == "Лист1":
                continue

            lines.append(f"{route}: {total:,.0f}".replace(",", " "))
            grand_total += total

        lines.append("-" * 30)
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
            lines.append(f'{item["ячейка"]} | {item["текст"]} | {item["маршруты"]}')

    lines.append("")
    lines.append(f"Лог сохранён: {log_file}")

    return "\n".join(lines)


def print_summary(output_file, stats, log_file):
    """Печатает в консоль итоговую сводку по результатам обработки."""

    print(format_summary(output_file, stats, log_file))
