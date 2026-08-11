import os
from pathlib import Path

import reflex as rx


# Папки и файлы, которые приложение само создаёт и перезаписывает при
# обработке заказов (excel-файлы, логи, json с настройками/историей).
# Без этого исключения dev-сервер (uvicorn --reload) следит за всей
# папкой проекта без фильтра по расширениям и перезапускает бэкенд на
# каждую такую запись, из-за чего сбрасывается состояние открытой
# страницы (пропадает сводка обработки, сбрасываются переключатели).
_RUNTIME_DIRS = ["orders", "processed_orders", "logs", "tracking_data"]
_RUNTIME_FILES = [
    "processed_files.json",
    "settings.json",
    "stores.json",
    "stores_city.json",
    "stores_region.json",
]

for _dir in _RUNTIME_DIRS:
    Path(_dir).mkdir(exist_ok=True)

os.environ.setdefault(
    "REFLEX_HOT_RELOAD_EXCLUDE_PATHS",
    ":".join(_RUNTIME_DIRS + _RUNTIME_FILES),
)


config = rx.Config(
    app_name="orders_dashboard",
    plugins=[
        rx.plugins.RadixThemesPlugin(),
    ],
    disable_plugins=[
        rx.plugins.SitemapPlugin,
    ],
)
