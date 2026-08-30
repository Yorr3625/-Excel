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
from modules.order_preview import PreviewError, build_order_preview
from modules.pipeline import process_order
from modules.reporter import format_preview, print_summary


def main():
    settings = load_settings()
    input_file = select_order_file()

    print(f"\nВыбран файл: {Path(input_file).name}")

    processed_files = load_processed_files()
    filename = Path(input_file).name

    processed_at = processed_files.get(filename, "")

    if processed_at:
        print("\n⚠ ВНИМАНИЕ!")
        print("Файл уже обрабатывался ранее.")
        print(f"Дата обработки: {processed_at}")

        confirm = input("\nПовторно обработать файл? (Y/N): ").strip().lower()
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

    try:
        preview = build_order_preview(
            input_file,
            groups,
            conflict_fill,
            mode_name,
        )
    except PreviewError as error:
        print(f"\nОШИБКА предварительного просмотра: {error}")
        return

    if processed_at:
        preview["warnings"].append(
            f"Файл уже обрабатывался {processed_at}. "
            "Повторная обработка обновит статистику."
        )

    print("\n" + format_preview(preview))
    confirm = input("\nНачать обработку после просмотра? (Y/N): ").strip().lower()

    if confirm != "y":
        print("Обработка отменена.")
        return

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
