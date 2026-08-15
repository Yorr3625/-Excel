import os

import reflex as rx

from modules import paths


# Дашборд постоянно пишет в data/ (excel-результаты, логи, json с историей)
# и в config/ (настройки, списки магазинов). Dev-сервер Reflex следит за
# всей папкой проекта без фильтра по расширениям и перезапускал бы бэкенд
# на каждую такую запись, сбрасывая состояние открытой страницы (пропадала
# сводка обработки, слетали переключатели). Исключаем обе папки целиком —
# так список не надо поддерживать при появлении новых файлов.
for _dir in (
    paths.CONFIG_DIR,
    paths.DATA_DIR,
    paths.ORDERS_FOLDER,
    paths.INVOICES_FOLDER,
    paths.PROCESSED_FOLDER,
    paths.LOGS_FOLDER,
    paths.UPLOADS_FOLDER,
    paths.TRACKING_FOLDER,
):
    _dir.mkdir(parents=True, exist_ok=True)

os.environ.setdefault(
    "REFLEX_HOT_RELOAD_EXCLUDE_PATHS",
    ":".join(str(_dir) for _dir in (paths.CONFIG_DIR, paths.DATA_DIR)),
)

# По умолчанию Reflex складывает загруженные файлы в uploaded_files/ в
# корне проекта — уводим внутрь data/, к остальным рабочим папкам.
os.environ.setdefault("REFLEX_UPLOADED_FILES_DIR", str(paths.UPLOADS_FOLDER))


config = rx.Config(
    app_name="orders_dashboard",
    plugins=[
        rx.plugins.RadixThemesPlugin(),
    ],
    disable_plugins=[
        rx.plugins.SitemapPlugin,
    ],
)
