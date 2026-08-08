import json
from pathlib import Path
from datetime import datetime

from modules.config import load_settings, load_stores, build_groups
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



LOG_FILE = "processed_files.json"


def load_processed_files():
    if not Path(LOG_FILE).exists():
        return {}

    try:
        with open(LOG_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except:
        return {}


def save_processed_file(filename):
    data = load_processed_files()

    data[filename] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    with open(LOG_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=4)

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

    stores = load_stores()
    fills = [green_fill, yellow_fill, blue_fill, purple_fill]
    groups = build_groups(stores, fills)

    output_file, log_file, stats = process_order(
        input_file,
        settings,
        groups,
        conflict_fill,
    )

    print_summary(output_file, stats, log_file)
    save_processed_file(filename)

if __name__ == "__main__":
    main()

KEYWORDS = [
    "итого",
    "итог",
    "всего",
    "итого:",
    "итог:"
]

rows_to_delete = []

