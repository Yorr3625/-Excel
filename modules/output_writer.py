import os

from modules.paths import PROCESSED_FOLDER


def build_output_path(now):
    """Строит путь для сохранения обработанного файла: processed_orders/ДД.ММ.ГГ/заказ_обработан_ЧЧ-ММ-СС.xlsx"""

    date_folder = now.strftime("%d.%m.%y")
    time_file = now.strftime("%H-%M-%S")

    output_folder = os.path.join(PROCESSED_FOLDER, date_folder)
    os.makedirs(output_folder, exist_ok=True)

    output_file = os.path.join(
        output_folder,
        f"заказ_обработан_{time_file}.xlsx",
    )

    return output_file, date_folder


def open_result(output_file, settings):
    """Открывает готовый файл или папку с ним, согласно настройкам."""

    if settings.get("open_file_after_processing"):
        os.startfile(output_file)

    elif settings.get("open_folder_after_processing"):
        os.startfile(os.path.dirname(output_file))
