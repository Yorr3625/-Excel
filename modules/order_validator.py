"""Проверка, что присланный файл — действительно заказ, а не любой Excel.

Нужна для писем: отправитель может вложить прайс, накладную или вообще
чужую таблицу. Обрабатывать такое нельзя — пайплайн рассчитан на структуру
заказа и на постороннем файле в лучшем случае выдаст пустой результат.

Признак заказа простой и надёжный: в заказе перечислены магазины из
config/stores_*.json. У постороннего файла совпадений будет ноль, у
настоящего — десятки.
"""

from pathlib import Path

from modules.config import build_groups, load_stores
from modules.paths import stores_file_for
from modules.pipeline import detect_mode
from modules.styles import blue_fill, conflict_fill, green_fill, purple_fill, yellow_fill


ALLOWED_SUFFIXES = (".xlsx", ".xlsm")

# Ниже этого числа найденных магазинов файл считаем не заказом. Реальные
# заказы дают десятки совпадений, случайное срабатывание на постороннем
# файле маловероятно, но одного-двух совпадений для запуска мало.
MIN_STORE_MATCHES = 3

# Защита от присланного «Excel» на сотни мегабайт.
MAX_FILE_MB = 25


def _fills():
    return [green_fill, yellow_fill, blue_fill, purple_fill]


def validate_order_file(path) -> dict:
    """Проверяет файл и возвращает вердикт.

    Ответ: {
        "ok": bool,            — можно ли обрабатывать
        "reason": str,         — понятная человеку причина отказа ("" если ok)
        "mode": str,           — определённый режим ("Город"/"Область")
        "matches": int,        — сколько магазинов найдено в лучшем режиме
        "scores": dict,        — совпадения по каждому режиму
    }
    """

    path = Path(path)
    verdict = {"ok": False, "reason": "", "mode": "", "matches": 0, "scores": {}}

    if not path.exists():
        verdict["reason"] = "Файл не найден"
        return verdict

    if path.suffix.lower() not in ALLOWED_SUFFIXES:
        verdict["reason"] = f"Не Excel-файл ({path.suffix or 'без расширения'})"
        return verdict

    size_mb = path.stat().st_size / (1024 * 1024)

    if size_mb > MAX_FILE_MB:
        verdict["reason"] = f"Файл слишком большой ({size_mb:.0f} МБ)"
        return verdict

    if path.stat().st_size == 0:
        verdict["reason"] = "Файл пустой"
        return verdict

    try:
        mode_groups = {
            mode: build_groups(load_stores(stores_file_for(mode)), _fills())
            for mode in ("Город", "Область")
        }
    except (OSError, ValueError, KeyError) as error:
        verdict["reason"] = f"Не удалось прочитать списки магазинов: {error}"
        return verdict

    try:
        mode, scores = detect_mode(path, mode_groups, conflict_fill)
    except Exception:
        # openpyxl падает на битых файлах и на всём, что лишь притворяется
        # xlsx — для нас это просто «не заказ», разбираться не нужно.
        verdict["reason"] = "Не удалось открыть как Excel — файл повреждён или это не таблица"
        return verdict

    verdict["mode"] = mode
    verdict["scores"] = scores
    verdict["matches"] = scores.get(mode, 0)

    if verdict["matches"] < MIN_STORE_MATCHES:
        verdict["reason"] = (
            "Не похоже на заказ: не нашлось магазинов из справочника "
            f"(совпадений — Город: {scores.get('Город', 0)}, "
            f"Область: {scores.get('Область', 0)})"
        )
        return verdict

    verdict["ok"] = True
    return verdict
