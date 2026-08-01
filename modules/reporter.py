def print_summary(output_file, stats, log_file):
    """Печатает в консоль итоговую сводку по результатам обработки."""

    print("======================")
    print("Обработка завершена")
    print("======================")
    print(f"Создан файл: {output_file}")

    print()
    print("Найдено адресов:")

    for route, count in stats["route_count"].items():
        print(f"{route}: {count}")

    print()
    print(f"Конфликтов найдено: {stats['conflict_count']}")
    print(f"Неизвестных магазинов: {len(stats['unknown_stores'])}")

    if stats["unknown_stores"]:

        print()
        print("Неизвестные магазины:")

        for store in stats["unknown_stores"]:
            print(store)

    if stats["conflict_count"]:

        print()
        print("Ошибочные адреса:")

        for item in stats["conflict_list"]:
            print(f'{item["ячейка"]} | {item["текст"]} | {item["маршруты"]}')

    print()
    print(f"Лог сохранён: {log_file}")
