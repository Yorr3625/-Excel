from colorama import init, Fore, Style

init(autoreset=True)


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