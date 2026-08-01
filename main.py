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


def main():

    settings = load_settings()
    input_file = select_order_file()

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


if __name__ == "__main__":
    main()
