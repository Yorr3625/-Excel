from pathlib import Path

from modules import paths
from modules.config import load_settings, load_stores, build_groups
from modules.history import load_processed_files, record_processing
from modules.styles import (
    green_fill,
    yellow_fill,
    blue_fill,
    purple_fill,
    conflict_fill,
)
from modules.file_selector import select_order_file
from modules.pipeline import process_order
from modules.reporter import print_summary


def main():

    settings = load_settings()
    input_file = select_order_file()

    print(f"\nВыбран файл: {Path(input_file).name}")

    confirm = input(
        "\nНачать обработку? (Y/N): "
    ).strip().lower()

    if confirm != "y":
        print("Обработка отменена.")
        return

    processed_files = load_processed_files()

    filename = Path(input_file).name

    if filename in processed_files:

        print("\n⚠ ВНИМАНИЕ!")
        print("Файл уже обрабатывался ранее.")

        print(
            f"Дата обработки: "
            f"{processed_files[filename]}"
        )

        confirm = input(
            "\nПовторно обработать файл? (Y/N): "
        ).strip().lower()

        if confirm != "y":
            print("Обработка отменена.")
            return
    print("\n========================")
    print(" Выберите вариант")
    print("========================")
    print("1 - Город")
    print("2 - Область")

    mode = input("\nВаш выбор: ").strip()

    if mode == "1":
        mode_name = "Город"
    elif mode == "2":
        mode_name = "Область"
    else:
        print("Неверный выбор!")
        return

    stores_file = paths.stores_file_for(mode_name)

    print(f"\nВыбран режим: {mode_name}")
    print(f"Файл магазинов: {stores_file}")

    stores = load_stores(stores_file)
    fills = [green_fill, yellow_fill, blue_fill, purple_fill]
    groups = build_groups(stores, fills)

    output_file, log_file, stats = process_order(
        input_file,
        settings,
        groups,
        conflict_fill,
    )

    print_summary(output_file, stats, log_file)
    record_processing(filename, stats)


if __name__ == "__main__":
    try:
        main()
    except Exception:
        import traceback

        print("\nОШИБКА:")
        traceback.print_exc()