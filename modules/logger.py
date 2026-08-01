import os


def write_log(date_folder, now, input_file, output_file, stats):
    """Дописывает информацию об обработке в лог-файл logs/ДД.ММ.ГГ/лог.txt"""

    log_folder = os.path.join("logs", date_folder)
    os.makedirs(log_folder, exist_ok=True)

    log_file = os.path.join(log_folder, "лог.txt")

    with open(log_file, "a", encoding="utf-8") as log:

        log.write("\n\n")
        log.write("==============================\n")
        log.write(f"ОБРАБОТКА {now.strftime('%H:%M:%S')}\n")
        log.write("==============================\n\n")

        log.write(f"Дата: {now.strftime('%d.%m.%Y %H:%M:%S')}\n")
        log.write(f"Файл: {input_file}\n")
        log.write(f"Результат: {output_file}\n\n")

        log.write("Найдено адресов:\n")

        for route, count in stats["route_count"].items():
            log.write(f"{route}: {count}\n")

        log.write(f"\nВсего найдено: {stats['total_found']}\n")
        log.write(f"Конфликтов: {stats['conflict_count']}\n")
        log.write(f"Неизвестных магазинов: {len(stats['unknown_stores'])}\n")

        if stats["conflict_count"] > 0:

            log.write("\nОшибочные адреса:\n")

            for item in stats["conflict_list"]:
                log.write(
                    f'{item["ячейка"]} | {item["текст"]} | {item["маршруты"]}\n'
                )

        if stats["unknown_stores"]:

            log.write("\nНеизвестные магазины:\n")

            for store in stats["unknown_stores"]:
                log.write(f"{store}\n")

    return log_file
