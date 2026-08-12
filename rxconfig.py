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

# Файлы, которые дашборд заводит сам по мере работы. Создаём их пустыми
# заранее: Reflex сверяет каждый исключённый путь через samefile() и
# падает с FileNotFoundError, если файла ещё нет (на свежей копии
# репозитория их нет).
_GENERATED_FILES = {
    "processed_files.json": "{}",
    "volume_history.json": "[]",
    "route_backups.json": "{}",
}

# Эти файлы приложение только читает и перезаписывает; создавать их
# пустыми нельзя — без реальных настроек и списков магазинов обработка
# не запустится.
_CONFIG_FILES = [
    "settings.json",
    "stores.json",
    "stores_city.json",
    "stores_region.json",
]

for _dir in _RUNTIME_DIRS:
    Path(_dir).mkdir(exist_ok=True)

for _name, _empty in _GENERATED_FILES.items():
    if not Path(_name).exists():
        Path(_name).write_text(_empty, encoding="utf-8")

os.environ.setdefault(
    "REFLEX_HOT_RELOAD_EXCLUDE_PATHS",
    ":".join(
        _RUNTIME_DIRS
        + [name for name in (*_GENERATED_FILES, *_CONFIG_FILES) if Path(name).exists()]
    ),
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
