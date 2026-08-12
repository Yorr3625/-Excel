"""Все пути проекта в одном месте.

Пути относительные: приложение запускается из корня проекта — так делают
start.bat, start_dashboard.bat и `reflex run`. Раньше эти пути были
разбросаны строковыми литералами по модулям и дашборду, из-за чего любое
перемещение папки требовало правок в десятке мест.

    config/ — то, что настраивает пользователь (настройки, списки магазинов)
    data/   — то, что программа накапливает сама (заказы, результаты, логи)
"""

from pathlib import Path


CONFIG_DIR = Path("config")
DATA_DIR = Path("data")

# --- config/: настройки и справочники ---
SETTINGS_FILE = CONFIG_DIR / "settings.json"
STORES_FILE = CONFIG_DIR / "stores.json"
STORES_CITY_FILE = CONFIG_DIR / "stores_city.json"
STORES_REGION_FILE = CONFIG_DIR / "stores_region.json"

# --- data/: рабочие папки ---
ORDERS_FOLDER = DATA_DIR / "orders"
PROCESSED_FOLDER = DATA_DIR / "processed_orders"
LOGS_FOLDER = DATA_DIR / "logs"
UPLOADS_FOLDER = DATA_DIR / "uploaded_files"
TRACKING_FOLDER = DATA_DIR / "tracking_data"

# --- data/: файлы, которые накапливает дашборд ---
PROCESSED_FILES_FILE = DATA_DIR / "processed_files.json"
VOLUME_HISTORY_FILE = DATA_DIR / "volume_history.json"
ROUTE_BACKUPS_FILE = DATA_DIR / "route_backups.json"


def stores_file_for(mode: str) -> Path:
    """Файл со списками магазинов для режима «Город» / «Область»."""

    return STORES_CITY_FILE if mode == "Город" else STORES_REGION_FILE
