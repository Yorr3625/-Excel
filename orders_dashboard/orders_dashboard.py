from pathlib import Path
from datetime import datetime, timedelta
import asyncio
import json
import os
import traceback

import reflex as rx
from starlette.applications import Starlette
from starlette.requests import Request
from starlette.responses import JSONResponse
from starlette.routing import Route

from modules import driver_data, paths
from modules.backup import (
    BackupError,
    create_backup,
    list_backups,
    load_backup_directory,
    restore_backup,
    save_backup_directory,
)
from modules.config import build_groups, load_settings, load_stores, save_settings, save_stores
from modules.excel_io import EXCEL_MIME_TYPES, is_excel_file
from modules.history import (
    load_processed_files,
    load_volume_history,
    record_processing,
    was_processed,
)
from modules.mail_watcher import (
    KIND_INVOICES,
    KIND_MESSAGE,
    KIND_ORDERS,
    MailErrorEntry,
    append_mail_error,
    check_mail,
    check_mail_connection,
    check_mail_with_retry,
    clear_mail_error_log,
    is_configured,
    link_invoice,
    load_mail_config,
    load_mail_error_log,
    load_mail_items,
    save_mail_credentials as save_mail_credentials_config,
    sources as mail_sources_config,
    split_invoice_candidates,
    unlink_invoice,
)
from modules.pipeline import detect_mode, process_order as run_pipeline
from modules.order_preview import PreviewError, build_order_preview
from modules.styles import blue_fill, conflict_fill, green_fill, purple_fill, yellow_fill
from modules.version import APP_NAME, APP_VERSION, Release, load_changelog
from modules.updater import check_for_update as check_remote_update, update_project
from modules.tracking_sim import (
    ROUTE_COLORS,
    ROUTE_KEYS,
    ROUTE_LABELS,
    advance_tick,
    build_map_svg,
    init_vehicles,
)


async def gps_ping(request: Request):
    try:
        payload = await request.json()
    except (ValueError, json.JSONDecodeError):
        return JSONResponse({"ok": False, "error": "bad json"}, status_code=400)

    if not isinstance(payload, dict):
        return JSONResponse({"ok": False, "error": "bad payload"}, status_code=400)

    vehicle = payload.get("vehicle", "")

    if not driver_data.is_valid_vehicle(vehicle):
        return JSONResponse({"ok": False, "error": "unknown vehicle"}, status_code=400)

    driver_data.append_gps(
        vehicle,
        payload.get("lat"),
        payload.get("lon"),
        payload.get("speed"),
    )
    return JSONResponse({"ok": True})


custom_api = Starlette(routes=[Route("/api/gps-ping", gps_ping, methods=["POST"])])


FA_ICON_MAP = {
    "layout_dashboard": "FaGauge",
    "package": "FaBox",
    "route": "FaRoute",
    "truck": "FaTruck",
    "history": "FaClockRotateLeft",
    "settings": "FaGear",
    "boxes": "FaBoxesStacked",
    "sun": "FaSun",
    "moon": "FaMoon",
    "upload": "FaUpload",
    "file_spreadsheet": "FaFileExcel",
    "file_pdf": "FaFilePdf",
    "chart_no_axes_column": "FaChartColumn",
    "map": "FaMap",
    "award": "FaAward",
    "list": "FaList",
    "map_pin": "FaLocationDot",
    "mail": "FaEnvelope",
    "inbox": "FaInbox",
    "refresh": "FaRotate",
    "circle_x": "FaCircleXmark",
    "x": "FaXmark",
    "plus": "FaPlus",
    "camera": "FaCamera",
    "circle_check": "FaCircleCheck",
    "circle": "FaCircle",
    "store": "FaStore",
    "fuel": "FaGasPump",
    "triangle_alert": "FaTriangleExclamation",
    "key": "FaKey",
    "info": "FaCircleInfo",
    "save": "FaFloppyDisk",
    "folder": "FaFolderOpen",
}


class FaIcon(rx.Component):
    """Font Awesome 6 icon, loaded from the react-icons/fa6 package."""

    library = "react-icons/fa6"
    tag = "FaCircleQuestion"

    size: rx.Var[int]
    color: rx.Var[str]

    @classmethod
    def create(cls, **props):
        name = props.pop("tag", "")
        props["tag"] = FA_ICON_MAP.get(name, "FaCircleQuestion")
        return super().create(**props)


fa_icon = FaIcon.create


ACCENT = "#1f883d"
ACCENT_HOVER = "#1a7f37"
MAIL_APP_PASSWORD_URL = "https://myaccount.google.com/apppasswords"
UPLOAD_ID = "order_upload"
INVOICE_UPLOAD_ID = "invoice_upload"
VOLUME_CHART_DAYS = 31
ROUTE_BACKUPS_FILE = paths.ROUTE_BACKUPS_FILE
MAX_ROUTE_BACKUPS = 20
VOLUME_ROUTE_LABELS = ["Маршрут 1", "Маршрут 2", "Маршрут 3", "Маршрут 4"]
SUPPORTED_EXCEL_LABEL = ".xlsx, .xlsm, .xlsb, .xls, .xltx, .xltm"
VERSION_HISTORY = load_changelog()

NAV_ITEMS = [
    ("Dashboard", "layout_dashboard"),
    ("Заказы", "package"),
    ("Почта", "mail"),
    ("Маршруты", "route"),
    ("Трекинг", "truck"),
    ("История", "history"),
    ("Настройки", "settings"),
    ("Версия", "info"),
    ("Резервные копии", "save"),
]

ICON_TINTS = {
    "green": (ACCENT, "rgba(31, 136, 61, 0.16)"),
    "blue": ("#2f6fed", "rgba(47, 111, 237, 0.16)"),
    "violet": ("#7c5cff", "rgba(124, 92, 255, 0.16)"),
}

SETTINGS_LABELS = {
    "open_file_after_processing": (
        "Открывать файл после обработки",
        "Открыть готовый Excel-файл сразу после обработки.",
    ),
    "open_folder_after_processing": (
        "Открывать папку после обработки",
        "Открыть папку с результатом, если файл не открывается.",
    ),
    "create_logs": (
        "Вести лог обработки",
        "Сохранять текстовый лог каждой обработки в папку logs.",
    ),
    "save_backup": (
        "Сохранять резервную копию",
        "Хранить резервную копию исходного файла перед обработкой.",
    ),
    "show_errors": (
        "Показывать ошибки",
        "Выводить подробный текст ошибки обработки на экран.",
    ),
}


def load_route_backups():
    if not ROUTE_BACKUPS_FILE.exists():
        return {}

    try:
        return json.loads(ROUTE_BACKUPS_FILE.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}


def append_route_backup(source: str, routes: dict, note: str) -> str:
    """Кладёт копию маршрутов в начало списка и возвращает её подпись."""

    data = load_route_backups()
    items = data.get(source, [])

    # Подпись — это и значение в выпадающем списке, и ключ поиска при
    # восстановлении, поэтому она должна быть уникальной: две копии,
    # созданные в одну секунду, иначе стали бы неразличимы.
    base_label = f"{datetime.now():%d.%m.%Y %H:%M:%S} — {note}"
    existing = {item.get("label") for item in items}
    label = base_label
    suffix = 2

    while label in existing:
        label = f"{base_label} ({suffix})"
        suffix += 1

    items.insert(0, {"label": label, "routes": routes})
    data[source] = items[:MAX_ROUTE_BACKUPS]

    ROUTE_BACKUPS_FILE.write_text(
        json.dumps(data, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    return label


def routes_dict(route_stores) -> dict:
    """Списки маршрутов (по индексам) -> структура для stores_*.json."""

    return {key: list(names) for key, names in zip(ROUTE_KEYS, route_stores)}


def build_volume_chart_data():
    daily = {}

    for record in load_volume_history():
        date = record.get("date")
        if not date:
            continue

        bucket = daily.setdefault(date, [0.0, 0.0, 0.0, 0.0])
        for index, key in enumerate(("route_1", "route_2", "route_3", "route_4")):
            bucket[index] += float(record.get(key) or 0)

    today = datetime.now().date()
    chart = []

    for offset in range(VOLUME_CHART_DAYS - 1, -1, -1):
        day = today - timedelta(days=offset)
        totals = daily.get(day.strftime("%Y-%m-%d"), [0.0, 0.0, 0.0, 0.0])

        point = {"date": day.strftime("%d.%m")}
        for label, total in zip(VOLUME_ROUTE_LABELS, totals):
            point[label] = round(total)

        chart.append(point)

    return chart


def format_number(value):
    return f"{float(value):,.0f}".replace(",", " ")


def format_bytes(value):
    size = float(value or 0)
    for unit in ("Б", "КБ", "МБ", "ГБ"):
        if size < 1024 or unit == "ГБ":
            return f"{size:.1f} {unit}" if unit != "Б" else f"{int(size)} {unit}"
        size /= 1024

    return "0 Б"

class State(rx.State):
    selected_file: str = "Файл не выбран"
    uploaded_file_path: str = ""
    mode: str = "Область"
    mode_auto_note: str = ""
    mode_detection_warning: str = ""
    duplicate_note: str = ""
    theme: str = "dark"
    status: str = "Ожидает загрузки файла"
    is_processing: bool = False
    is_previewing: bool = False
    preview_ready: bool = False
    preview_source: str = ""
    preview_mode: str = ""
    preview_status: str = ""
    preview_file_info: str = ""
    preview_sheet_info: str = ""
    preview_document_type: str = ""
    preview_order_rows: int = 0
    preview_match_count: int = 0
    preview_grand_total: str = "0"
    preview_route_rows: list[str] = []
    preview_found_stores: list[str] = []
    preview_warnings: list[str] = []
    preview_conflicts: list[str] = []
    preview_unknown_stores: list[str] = []
    output_file: str = ""
    log_file: str = ""
    grand_total: str = "0"
    route_totals: list[str] = ["0", "0", "0", "0"]
    conflict_count: int = 0
    unknown_count: int = 0
    error_text: str = ""
    history_1_file: str = "Нет обработок"
    history_1_time: str = ""
    history_2_file: str = "Нет обработок"
    history_2_time: str = ""
    history_3_file: str = "Нет обработок"
    history_3_time: str = ""

    orders_today_count: int = 0
    orders_total_count: int = 0
    stores_total_count: int = 0
    volume_chart_data: list[dict] = []

    current_version: str = APP_VERSION
    version_history: list[Release] = VERSION_HISTORY
    remote_version: str = ""
    update_status: str = "Проверка ещё не выполнялась."
    checking_update: bool = False
    updating_app: bool = False
    update_available: bool = False

    current_page: str = "Dashboard"

    routes_source: str = "Область"
    # Списки по маршрутам (индексы 0..3 соответствуют ROUTE_KEYS).
    route_stores: list[list[str]] = [[], [], [], []]
    new_store_inputs: list[str] = ["", "", "", ""]
    routes_status: str = ""
    route_backup_labels: list[str] = []
    selected_route_backup: str = ""

    backup_directory: str = ""
    backup_items: list[dict] = []
    backup_labels: list[str] = []
    backup_status: str = ""
    selected_backup: str = ""
    restore_confirmation_open: bool = False

    tracking_source: str = "Область"
    tracking_running: bool = False
    vehicles: list[dict] = []
    tracking_event_log: list[str] = []

    mail_configured: bool = False
    mail_credentials_editing: bool = False
    mail_email: str = ""
    mail_app_password: str = ""
    mail_credentials_status: str = ""
    mail_checking: bool = False
    mail_connection_checking: bool = False
    mail_status: str = ""
    mail_error: str = ""
    mail_last_check: str = "Ещё не выполнялась"
    mail_error_log: list[MailErrorEntry] = []
    mail_new_orders_count: int = 0
    mail_notification: str = ""
    mail_items: list[dict] = []
    mail_all_items: list[dict] = []
    mail_sources: list[str] = ["Все"]
    mail_source: str = "Все"
    mail_kind_filter: str = "Все сообщения"
    mail_auto: bool = False
    mail_interval: int = 10

    history_items: list[dict] = []
    order_details_open: bool = False
    selected_order: str = ""
    selected_order_time: str = ""
    selected_order_time_label: str = "Обработан"
    order_detail_tab: str = "Накладные"
    order_invoices: list[dict] = []
    available_invoices: list[dict] = []
    other_invoices: list[dict] = []
    available_invoices_title: str = "Непривязанные накладные"
    available_invoices_empty: str = "Новых непривязанных накладных нет"
    invoice_date_hint: str = ""
    invoice_search: str = ""
    order_detail_status: str = ""

    tracking_view: str = "Симуляция"
    real_vehicles: list[dict] = []
    real_watching: bool = False

    settings_data: dict[str, bool] = {
        "open_file_after_processing": True,
        "open_folder_after_processing": False,
        "create_logs": True,
        "save_backup": True,
        "show_errors": True,
    }
    settings_status: str = ""

    def set_page(self, page: str):
        self.current_page = page

        if page == "Маршруты":
            self.load_routes()
        elif page == "Настройки":
            self.load_settings_form()
        elif page == "Резервные копии":
            self.load_backups()
        elif page == "Трекинг" and not self.vehicles:
            self.init_tracking()
        elif page == "Почта":
            self.refresh_mail_config()

    def load_backups(self):
        self.backup_status = ""
        self.backup_directory = str(load_backup_directory())
        self.refresh_backups()

    def refresh_backups(self):
        try:
            self.backup_items = [
                {
                    "name": item.name,
                    "created_at": item.created_at.replace("T", " ")[:19],
                    "size": format_bytes(item.size_bytes),
                    "files": item.file_count,
                    "valid": item.valid,
                    "error": item.error,
                    "contains_secrets": item.contains_secrets,
                }
                for item in list_backups(self.backup_directory or None)
            ]
            self.backup_labels = [item["name"] for item in self.backup_items if item["valid"]]
        except BackupError as error:
            self.backup_items = []
            self.backup_labels = []
            self.backup_status = str(error)

    def set_backup_directory(self, value: str):
        self.backup_directory = value
        self.backup_status = ""

    def save_backup_directory_form(self):
        try:
            directory = save_backup_directory(self.backup_directory)
            self.backup_directory = str(directory)
            self.refresh_backups()
            self.backup_status = "Папка резервных копий сохранена"
        except BackupError as error:
            self.backup_status = str(error)

    def create_full_backup(self):
        try:
            info = create_backup(self.backup_directory or None, reason="вручную")
            self.refresh_backups()
            self.selected_backup = info.name
            self.backup_status = f"Копия создана: {info.name}"
        except BackupError as error:
            self.backup_status = str(error)

    def set_selected_backup(self, value: str):
        self.selected_backup = value
        self.restore_confirmation_open = False

    def ask_restore_backup(self):
        if not self.selected_backup:
            self.backup_status = "Сначала выберите резервную копию"
            return
        selected = next(
            (item for item in self.backup_items if item["name"] == self.selected_backup),
            None,
        )
        if not selected or not selected["valid"]:
            self.backup_status = "Выбранная копия повреждена или недоступна"
            return
        self.restore_confirmation_open = True

    def cancel_restore_backup(self):
        self.restore_confirmation_open = False

    def confirm_restore_backup(self):
        if self.selected_backup not in self.backup_labels:
            self.restore_confirmation_open = False
            self.backup_status = "Выбранная копия больше недоступна"
            return

        archive = Path(self.backup_directory).resolve() / self.selected_backup
        try:
            result = restore_backup(archive)
            self.restore_confirmation_open = False
            self.load_history()
            self.load_settings_form()
            self.load_routes()
            self.refresh_mail_config()
            self.backup_directory = str(load_backup_directory())
            self.refresh_backups()
            safety = (
                f" Страховочная копия: {result.safety_backup.name}."
                if result.safety_backup
                else ""
            )
            self.backup_status = f"Состояние восстановлено из {self.selected_backup}.{safety}"
        except BackupError as error:
            self.restore_confirmation_open = False
            self.backup_status = str(error)

    @rx.event(background=True)
    async def check_for_update(self):
        """Проверяет версию в GitHub, не блокируя интерфейс дашборда."""

        async with self:
            if self.checking_update or self.updating_app:
                return
            self.checking_update = True
            self.remote_version = ""
            self.update_available = False
            self.update_status = "Проверяю обновления..."

        try:
            result = await asyncio.to_thread(
                check_remote_update,
                self.current_version,
            )
        except Exception:
            async with self:
                self.checking_update = False
                self.update_status = "Не удалось проверить обновления."
            return

        async with self:
            self.checking_update = False
            self.remote_version = result.latest_version
            self.update_available = result.ok and result.update_available
            self.update_status = result.message

    @rx.event(background=True)
    async def update_application(self):
        """Устанавливает найденное обновление только через fast-forward Git."""

        async with self:
            if self.updating_app or self.checking_update:
                return
            if not self.update_available:
                self.update_status = "Сначала проверьте наличие новой версии."
                return
            self.updating_app = True
            self.update_status = "Загружаю обновление..."

        try:
            result = await asyncio.to_thread(update_project)
        except Exception:
            async with self:
                self.updating_app = False
                self.update_status = "Не удалось установить обновление."
            return

        async with self:
            self.updating_app = False
            self.update_status = result.message
            if not result.ok or not result.changed:
                return
            self.update_status = (
                f"{result.message} Если страница не перезагрузилась, "
                "закройте окно и снова запустите start_dashboard.bat."
            )

        return rx.call_script(
            "setTimeout(() => window.location.reload(), 1200);"
        )

    def refresh_mail_config(self):
        config = load_mail_config()
        self.mail_configured = is_configured(config)
        self.mail_email = str(config.get("email", ""))
        self.mail_app_password = ""
        self.mail_interval = max(int(config.get("check_interval_minutes", 10)), 1)
        self.mail_sources = ["Все"] + [item["name"] for item in mail_sources_config(config)]

        if self.mail_source not in self.mail_sources:
            self.mail_source = "Все"

        self._reload_mail_items()
        self.mail_error_log = load_mail_error_log()

        if not self.mail_configured:
            self.mail_credentials_editing = True
            self.mail_status = "Почта не настроена"

    def set_mail_email(self, value: str):
        self.mail_email = value
        self.mail_credentials_status = ""

    def set_mail_app_password(self, value: str):
        self.mail_app_password = value
        self.mail_credentials_status = ""

    def edit_mail_credentials(self):
        self.mail_credentials_editing = True
        self.mail_app_password = ""
        self.mail_credentials_status = ""

    def save_mail_credentials_form(self):
        ok, message = save_mail_credentials_config(
            self.mail_email,
            self.mail_app_password,
        )
        self.mail_credentials_status = message

        if not ok:
            return

        self.mail_app_password = ""
        self.mail_credentials_editing = False
        self.refresh_mail_config()
        self.mail_status = "Данные сохранены. Нажмите «Проверить почту»"

    @staticmethod
    def _mail_item_for_view(item: dict) -> dict:
        verdict = item.get("verdict") or {}
        kind = item.get("kind", KIND_MESSAGE)
        return {
            "file": item.get("file") or "Без вложения",
            "path": item.get("path", ""),
            "sender": item.get("sender", ""),
            "subject": item.get("subject", ""),
            "received": item.get("received_display", "Дата не указана"),
            "source": item.get("source_name", "Другое"),
            "person": item.get("source_person", ""),
            "kind": kind,
            "kind_label": {
                KIND_ORDERS: "Заказ",
                KIND_INVOICES: "Накладная",
                KIND_MESSAGE: "Письмо",
            }.get(kind, "Письмо"),
            "is_order": kind == KIND_ORDERS and bool(verdict.get("ok")),
            "is_invoice": kind == KIND_INVOICES,
            "has_file": bool(item.get("path")),
            "reason": verdict.get("reason", ""),
            "mode": verdict.get("mode", ""),
            "matches": verdict.get("matches", 0),
            "order_file": item.get("order_file", ""),
            "date_relation": item.get("date_relation", ""),
        }

    def _filter_mail_items(self):
        items = self.mail_all_items

        if self.mail_source != "Все":
            items = [item for item in items if item["source"] == self.mail_source]

        if self.mail_kind_filter == "Только заказы":
            items = [item for item in items if item["is_order"]]
        elif self.mail_kind_filter == "Только непривязанные накладные":
            items = [
                item
                for item in items
                if item["is_invoice"] and not item["order_file"]
            ]

        self.mail_items = items

    def _reload_mail_items(self):
        self.mail_all_items = [
            self._mail_item_for_view(item) for item in load_mail_items()
        ]
        self._filter_mail_items()

    def set_mail_source(self, source: str):
        self.mail_source = source
        self._filter_mail_items()

    def set_mail_kind_filter(self, value: str):
        self.mail_kind_filter = value
        self._filter_mail_items()

    def _apply_mail_result(self, result: dict):
        """Раскладывает ответ check_mail по состоянию. Только внутри `async with self`."""

        self.mail_error_log = load_mail_error_log()

        if not result["ok"]:
            self.mail_error = result["error"]
            self.mail_status = "Проверка не удалась"
            return

        self.mail_error = ""
        self._reload_mail_items()
        found = result["items"]
        suitable = sum(
            1
            for item in found
            if item.get("kind") == KIND_ORDERS
            and (item.get("verdict") or {}).get("ok")
        )
        invoices = sum(1 for item in found if item.get("kind") == KIND_INVOICES)

        if suitable:
            self.mail_new_orders_count += suitable
            self.mail_notification = (
                f"Новых заказов: {self.mail_new_orders_count}. "
                "Они готовы к обработке."
            )

        if not found:
            self.mail_status = "Новых писем нет"
        else:
            self.mail_status = (
                f"Найдено: {len(found)} · заказов: {suitable} · накладных: {invoices}"
            )

        attempts = int(result.get("attempts", 1))
        if attempts > 1:
            self.mail_status += f" · попыток: {attempts}"

    async def _run_mail_check(self, with_retry: bool = False):
        """Выполняет ручную или автоматическую проверку вне потока Reflex."""

        async with self:
            if self.mail_checking or self.mail_connection_checking:
                return

            self.mail_checking = True
            self.mail_error = ""
            self.mail_status = (
                "Проверяю почту с автоматическим повтором..."
                if with_retry
                else "Проверяю почту..."
            )

        operation = check_mail_with_retry if with_retry else check_mail

        try:
            result = await asyncio.to_thread(operation)
        except Exception as error:
            append_mail_error("Проверка почты", error)
            async with self:
                self.mail_checking = False
                self.mail_last_check = datetime.now().strftime("%d.%m.%Y %H:%M:%S")
                self.mail_error_log = load_mail_error_log()
                self.mail_error = "Неожиданная ошибка при проверке почты"
                self.mail_status = "Ошибка при проверке почты"
            return

        async with self:
            self.mail_checking = False
            self.mail_last_check = datetime.now().strftime("%d.%m.%Y %H:%M:%S")
            self._apply_mail_result(result)

    @rx.event(background=True)
    async def check_mail_connection_now(self):
        """Проверяет вход и доступ к папке, не загружая письма."""

        async with self:
            if self.mail_checking or self.mail_connection_checking:
                return
            self.mail_connection_checking = True
            self.mail_error = ""
            self.mail_status = "Проверяю соединение..."

        try:
            result = await asyncio.to_thread(check_mail_connection)
        except Exception as error:
            append_mail_error("Проверка соединения", error)
            result = {
                "ok": False,
                "error": "Неожиданная ошибка при проверке соединения",
            }

        async with self:
            self.mail_connection_checking = False
            self.mail_last_check = datetime.now().strftime("%d.%m.%Y %H:%M:%S")
            self.mail_error_log = load_mail_error_log()
            self.mail_error = "" if result["ok"] else result["error"]
            self.mail_status = (
                "Соединение установлено"
                if result["ok"]
                else "Проверка соединения не удалась"
            )

    @rx.event(background=True)
    async def check_mail_now(self):
        """Разовая проверка по кнопке без длительных повторов."""

        await self._run_mail_check()

    def clear_mail_notification(self):
        self.mail_new_orders_count = 0
        self.mail_notification = ""

    def clear_mail_errors(self):
        clear_mail_error_log()
        self.mail_error_log = []

    def toggle_mail_auto(self, enabled: bool):
        self.mail_auto = enabled

        if enabled:
            return State.watch_mail

    @rx.event(background=True)
    async def watch_mail(self):
        """Периодическая проверка, пока дашборд открыт и переключатель включён."""

        while True:
            async with self:
                if not self.mail_auto:
                    return
                interval = self.mail_interval

            await asyncio.sleep(max(interval, 1) * 60)

            async with self:
                if not self.mail_auto:
                    return

            await self._run_mail_check(with_retry=True)

    def take_mail_order(self, path: str, filename: str, received: str):
        """Берёт найденный файл в обработку на странице «Заказы»."""

        self.selected_file = filename
        self.uploaded_file_path = path
        self.output_file = ""
        self.log_file = ""
        self.error_text = ""
        self.status = f"Файл из почты: {filename}"

        processed_at = was_processed(filename)
        self.duplicate_note = (
            f"Этот файл уже обрабатывался {processed_at}. "
            "Повторная обработка обновит суммы, а не добавит их ещё раз."
            if processed_at
            else ""
        )

        self.detect_and_set_mode()
        self.current_page = "Заказы"
        self._show_order_details(filename, received, "Получен")

    def open_mail_attachment(self, path: str):
        attachment = Path(path)

        if not attachment.exists():
            self.mail_error = f"Файл не найден: {path}"
            return

        try:
            os.startfile(attachment.resolve())
        except OSError as error:
            self.mail_error = f"Не удалось открыть файл: {error}"

    def _show_order_details(
        self,
        filename: str,
        displayed_at: str,
        time_label: str,
    ):
        self.selected_order = filename
        self.selected_order_time = displayed_at
        self.selected_order_time_label = time_label
        self.order_detail_tab = "Накладные"
        self.order_detail_status = ""
        self.invoice_search = ""
        self.order_details_open = True
        self._refresh_order_invoices()

    def open_order_details(self, filename: str, processed_at: str):
        if filename == "Нет обработок":
            return

        self._show_order_details(filename, processed_at, "Обработан")

    def close_order_details(self):
        self.order_details_open = False

    def set_order_detail_tab(self, value: str):
        self.order_detail_tab = value

    def _refresh_order_invoices(self):
        mail_items = load_mail_items()
        invoices = [
            self._mail_item_for_view(item)
            for item in mail_items
            if item.get("kind") == KIND_INVOICES
        ]
        self.order_invoices = [
            item for item in invoices if item["order_file"] == self.selected_order
        ]

        order_date, order_mode, suggested, other = split_invoice_candidates(
            mail_items,
            self.selected_order,
        )

        if order_date is None:
            self.available_invoices_title = "Непривязанные накладные"
            self.available_invoices_empty = "Новых непривязанных накладных нет"
            self.invoice_date_hint = (
                "Дата получения заказа в почте не найдена — "
                "показаны все непривязанные накладные."
            )
            self.available_invoices = [
                self._mail_item_for_view(item) for item in other
            ]
            self.other_invoices = []
            self._filter_invoice_candidates()
            return

        next_day = order_date + timedelta(days=1)
        expected_files = {
            "Город": "городской файл «ФМ 40, МДВ»",
            "Область": (
                "областные файлы по группам: Кировское / Торез / Шахтерск, "
                "Горловка и Макеевка / Харцызск"
            ),
        }.get(order_mode, "накладные подходящего типа")
        self.available_invoices_title = (
            f"Подходящие накладные · {order_mode}"
            if order_mode
            else "Подходящие накладные"
        )
        self.available_invoices_empty = (
            f"За {order_date:%d.%m.%Y} и {next_day:%d.%m.%Y} "
            "подходящих непривязанных накладных нет"
        )
        self.invoice_date_hint = (
            f"Заказ получен {order_date:%d.%m.%Y}. Ищем {expected_files} "
            f"за этот день или за {next_day:%d.%m.%Y}."
        )
        self.available_invoices = [
            self._mail_item_for_view(item) for item in suggested
        ]
        self.other_invoices = [
            self._mail_item_for_view(item) for item in other
        ]
        self._filter_invoice_candidates()

    def set_invoice_search(self, value: str):
        self.invoice_search = value
        self._refresh_order_invoices()

    def _filter_invoice_candidates(self):
        query = self.invoice_search.strip().casefold()

        if not query:
            return

        def matches(item: dict) -> bool:
            searchable = " ".join((
                str(item.get("file", "")),
                str(item.get("source", "")),
                str(item.get("subject", "")),
                str(item.get("person", "")),
            )).casefold()
            return query in searchable

        self.available_invoices = [
            item for item in self.available_invoices if matches(item)
        ]
        self.other_invoices = [
            item for item in self.other_invoices if matches(item)
        ]
        self.available_invoices_empty = (
            f"По запросу «{self.invoice_search.strip()}» накладные не найдены"
        )

    def attach_invoice(self, path: str):
        if link_invoice(path, self.selected_order):
            self.order_detail_status = "Накладная привязана к заказу"
        else:
            self.order_detail_status = "Не удалось найти накладную"

        self._refresh_order_invoices()
        self._reload_mail_items()

    def detach_invoice(self, path: str):
        if unlink_invoice(path):
            self.order_detail_status = "Накладная отвязана"
        else:
            self.order_detail_status = "Не удалось найти накладную"

        self._refresh_order_invoices()
        self._reload_mail_items()

    @property
    def stores_file(self) -> Path:
        return paths.stores_file_for(self.routes_source)

    def load_routes(self):
        data = load_stores(self.stores_file)
        self.route_stores = [list(data.get(key, [])) for key in ROUTE_KEYS]
        self.routes_status = ""
        self.refresh_route_backups()

    def refresh_route_backups(self):
        data = load_route_backups()
        self.route_backup_labels = [
            item.get("label", "") for item in data.get(self.routes_source, [])
        ]

        if self.selected_route_backup not in self.route_backup_labels:
            self.selected_route_backup = ""

    def set_selected_route_backup(self, value: str):
        self.selected_route_backup = value

    def create_route_backup(self):
        label = append_route_backup(
            self.routes_source,
            routes_dict(self.route_stores),
            "вручную",
        )

        self.refresh_route_backups()
        self.selected_route_backup = label
        self.routes_status = f"Копия создана: {label}"

    def restore_route_backup(self):
        if not self.selected_route_backup:
            self.routes_status = "Сначала выберите копию в списке"
            return

        data = load_route_backups()

        for item in data.get(self.routes_source, []):
            if item.get("label") != self.selected_route_backup:
                continue

            routes = item.get("routes", {})
            self.route_stores = [list(routes.get(key, [])) for key in ROUTE_KEYS]
            self.routes_status = (
                f"Загружена копия «{self.selected_route_backup}». "
                "Нажмите «Сохранить маршруты», чтобы применить её."
            )
            return

        self.routes_status = "Копия не найдена — обновите список"
        self.refresh_route_backups()

    def set_routes_source(self, value: str):
        self.routes_source = value
        self.load_routes()

    def set_new_store(self, index: int, value: str):
        inputs = list(self.new_store_inputs)
        inputs[index] = value
        self.new_store_inputs = inputs

    def add_store(self, index: int):
        value = self.new_store_inputs[index].strip()

        if value and value not in self.route_stores[index]:
            routes = [list(names) for names in self.route_stores]
            routes[index].append(value)
            self.route_stores = routes

        inputs = list(self.new_store_inputs)
        inputs[index] = ""
        self.new_store_inputs = inputs

    def remove_store(self, index: int, name: str):
        routes = [list(names) for names in self.route_stores]
        routes[index] = [item for item in routes[index] if item != name]
        self.route_stores = routes

    def save_routes(self):
        stores_file = self.stores_file

        # Прежнее содержимое файла уходит в копию — так к нему можно
        # вернуться через выпадающий список, если новая версия не подошла.
        try:
            previous = load_stores(stores_file)
        except (OSError, ValueError):
            previous = None

        if previous:
            append_route_backup(self.routes_source, previous, "перед сохранением")

        save_stores(routes_dict(self.route_stores), stores_file)

        self.refresh_route_backups()
        self.routes_status = f"Сохранено в {stores_file}"

    def load_settings_form(self):
        data = load_settings()
        self.settings_data = {key: bool(data.get(key, False)) for key in SETTINGS_LABELS}
        self.settings_status = ""

    def toggle_setting(self, key: str, value: bool):
        self.settings_data = {**self.settings_data, key: value}

    def save_settings_form(self):
        save_settings(dict(self.settings_data))
        self.settings_status = "Настройки сохранены"

    def init_tracking(self):
        stores_file = paths.stores_file_for(self.tracking_source)
        self.vehicles = init_vehicles(stores_file)
        self.tracking_event_log = []

    def set_tracking_source(self, value: str):
        self.tracking_running = False
        self.tracking_source = value
        self.init_tracking()

    def reset_tracking(self):
        self.tracking_running = False
        self.init_tracking()

    def stop_tracking(self):
        self.tracking_running = False

    @rx.event(background=True)
    async def start_tracking(self):
        async with self:
            if self.tracking_running or not self.vehicles:
                return
            self.tracking_running = True

        while True:
            await asyncio.sleep(1.0)

            async with self:
                if not self.tracking_running:
                    return

                updated, events = advance_tick(self.vehicles)
                self.vehicles = updated

                if events:
                    self.tracking_event_log = (events + self.tracking_event_log)[:40]

    @rx.var
    def map_svg(self) -> str:
        return build_map_svg(self.vehicles)

    @rx.var
    def ranked_vehicles(self) -> list[dict]:
        return sorted(self.vehicles, key=lambda v: v["score"], reverse=True)

    @rx.var
    def tracking_total_distance(self) -> str:
        return format_number(sum(v["distance_km"] for v in self.vehicles))

    @rx.var
    def tracking_total_fuel(self) -> str:
        return format_number(sum(v["fuel_l"] for v in self.vehicles))

    @rx.var
    def tracking_total_cost(self) -> str:
        return format_number(sum(v["cost"] for v in self.vehicles))

    @rx.var
    def tracking_total_harsh(self) -> int:
        return sum(v["harsh_count"] for v in self.vehicles)

    @rx.var
    def tracking_avg_score(self) -> int:
        if not self.vehicles:
            return 100
        return round(sum(v["score"] for v in self.vehicles) / len(self.vehicles))

    def set_tracking_view(self, value: str):
        self.tracking_view = value

        if value == "Реальные данные":
            self.refresh_real_data()
        else:
            self.real_watching = False

    def refresh_real_data(self):
        items = []

        for index, key in enumerate(ROUTE_KEYS):
            data = driver_data.load_today(key)
            stops = data["stops"] if data else []
            last = data.get("last_position") if data else None

            items.append({
                "route_index": index,
                "label": ROUTE_LABELS[index],
                "color": ROUTE_COLORS[index],
                "stops": stops,
                "done_count": sum(1 for s in stops if s["status"] == "done"),
                "total_count": len(stops),
                "has_position": last is not None,
                "last_lat": last["lat"] if last else 0,
                "last_lon": last["lon"] if last else 0,
                "last_ts": last["ts"] if last else "",
            })

        self.real_vehicles = items

    @rx.event(background=True)
    async def watch_real_data(self):
        async with self:
            if self.real_watching:
                return
            self.real_watching = True

        while True:
            await asyncio.sleep(5.0)

            async with self:
                if not self.real_watching or self.tracking_view != "Реальные данные":
                    self.real_watching = False
                    return

                self.refresh_real_data()

    def load_history(self):
        data = load_processed_files()
        all_items = sorted(data.items(), key=lambda item: item[1], reverse=True)
        self.history_items = [
            {"file": filename, "time": processed_at}
            for filename, processed_at in all_items
        ]
        items = all_items[:3]
        placeholders = [("Нет обработок", "")] * 3
        items = items + placeholders[len(items):]

        self.history_1_file, self.history_1_time = items[0]
        self.history_2_file, self.history_2_time = items[1]
        self.history_3_file, self.history_3_time = items[2]

        self.orders_total_count = len(data)
        today = datetime.now().strftime("%Y-%m-%d")
        self.orders_today_count = sum(1 for ts in data.values() if ts.startswith(today))

        self.refresh_stores_total()
        self.volume_chart_data = build_volume_chart_data()

        if not self.vehicles:
            self.init_tracking()

    def refresh_stores_total(self):
        total = 0

        for filename in (paths.STORES_CITY_FILE, paths.STORES_REGION_FILE):
            try:
                store_data = load_stores(filename)
            except (OSError, json.JSONDecodeError):
                continue

            total += sum(len(names) for names in store_data.values())

        self.stores_total_count = total

    def _reset_preview(self):
        self.is_previewing = False
        self.preview_ready = False
        self.preview_source = ""
        self.preview_mode = ""
        self.preview_status = ""
        self.preview_file_info = ""
        self.preview_sheet_info = ""
        self.preview_document_type = ""
        self.preview_order_rows = 0
        self.preview_match_count = 0
        self.preview_grand_total = "0"
        self.preview_route_rows = []
        self.preview_found_stores = []
        self.preview_warnings = []
        self.preview_conflicts = []
        self.preview_unknown_stores = []

    async def handle_upload(self, files: list[rx.UploadFile]):
        if not files:
            self.status = "Сначала выберите Excel-файл"
            return

        for file in files:
            filename = getattr(file, "filename", None) or file.name

            if not is_excel_file(filename):
                self.status = (
                    f"Неподдерживаемый формат файла: {Path(filename).suffix or 'без расширения'}"
                )
                return

            data = await file.read()
            upload_dir = rx.get_upload_dir()
            upload_dir.mkdir(parents=True, exist_ok=True)
            output_path = upload_dir / Path(filename).name
            output_path.write_bytes(data)

            self._reset_preview()
            self.selected_file = output_path.name
            self.uploaded_file_path = str(output_path)
            self.status = f"Файл загружен: {output_path.name}"
            self.output_file = ""
            self.log_file = ""
            self.error_text = ""

            # Консольная версия предупреждает о повторной обработке —
            # в дашборде такого предупреждения не было.
            processed_at = was_processed(output_path.name)
            self.duplicate_note = (
                f"Этот файл уже обрабатывался {processed_at}. "
                "Повторная обработка обновит суммы, а не добавит их ещё раз."
                if processed_at
                else ""
            )

            self.detect_and_set_mode()

    def detect_and_set_mode(self):
        self.mode_auto_note = ""
        self.mode_detection_warning = ""

        try:
            fills = [green_fill, yellow_fill, blue_fill, purple_fill]
            mode_groups = {
                mode: build_groups(load_stores(paths.stores_file_for(mode)), fills)
                for mode in ("Город", "Область")
            }

            mode, scores = detect_mode(self.uploaded_file_path, mode_groups, conflict_fill)

            self.mode = mode
            score_note = (
                f"совпадений — Город: {scores['Город']}, "
                f"Область: {scores['Область']}"
            )

            if scores["Город"] == scores["Область"]:
                self.mode_detection_warning = (
                    "Режим определён неоднозначно: оба справочника дали "
                    f"одинаковый результат ({score_note}). Проверьте режим вручную."
                )
                self.mode_auto_note = self.mode_detection_warning
            else:
                self.mode_auto_note = (
                    f"Определено автоматически: «{mode}» ({score_note})"
                )

        except Exception:
            self.mode_detection_warning = (
                "Не удалось определить режим автоматически. Проверьте выбранный режим вручную."
            )
            self.mode_auto_note = self.mode_detection_warning

    def set_mode(self, mode: str):
        self.mode = mode
        self.mode_auto_note = ""
        self.mode_detection_warning = ""
        self._reset_preview()

        if self.uploaded_file_path:
            self.status = "Режим изменён. Постройте предварительный просмотр заново."

    def set_theme(self, theme: str):
        self.theme = theme

    def set_dark_mode(self, enabled: bool):
        self.theme = "dark" if enabled else "light"

    def preview_order(self):
        if not self.uploaded_file_path:
            self.status = "Сначала загрузите Excel-файл"
            return

        self.is_previewing = True
        self.preview_ready = False
        self.preview_status = "Анализ книги..."
        self.status = "Построение предварительного просмотра..."
        self.error_text = ""

        try:
            stores_file = paths.stores_file_for(self.mode)
            stores = load_stores(stores_file)
            fills = [green_fill, yellow_fill, blue_fill, purple_fill]
            groups = build_groups(stores, fills)
            preview = build_order_preview(
                self.uploaded_file_path,
                groups,
                conflict_fill,
                self.mode,
            )

            self.preview_source = self.uploaded_file_path
            self.preview_mode = self.mode
            self.preview_file_info = (
                f"{preview['file_name']} · {preview['file_extension']} · "
                f"{format_bytes(preview['file_size'])}"
            )
            self.preview_sheet_info = (
                f"Активный лист: {preview['sheet_name']} · "
                f"листов в книге: {preview['sheet_count']}"
            )
            self.preview_document_type = preview["document_type"]
            self.preview_order_rows = int(preview["order_rows"])
            self.preview_match_count = int(preview["total_found"])
            self.preview_grand_total = format_number(preview["grand_total"])
            self.preview_route_rows = [
                (
                    f"{route['name']}: строк — {route['rows']}, "
                    f"совпадений — {route['matches']}, "
                    f"объём — {format_number(route['total'])}"
                )
                for route in preview["route_rows"]
            ]
            found_stores = [
                f"{route['name']}: {store}"
                for route in preview["route_rows"]
                for store in route["stores"]
            ]
            self.preview_found_stores = found_stores[:20]
            self.preview_warnings = list(preview["warnings"])

            if self.mode_detection_warning:
                self.preview_warnings.append(self.mode_detection_warning)
            if self.duplicate_note:
                self.preview_warnings.append(self.duplicate_note)

            self.preview_unknown_stores = list(preview["unknown_stores"][:20])
            self.preview_conflicts = [
                (
                    f"{item['cell']} | {item['text']} | "
                    f"{', '.join(item['routes'])}"
                )
                for item in preview["conflicts"][:20]
            ]

            hidden_found = len(found_stores) - len(self.preview_found_stores)
            hidden_unknown = len(preview["unknown_stores"]) - len(self.preview_unknown_stores)
            hidden_conflicts = len(preview["conflicts"]) - len(self.preview_conflicts)

            if hidden_found:
                self.preview_warnings.append(
                    f"Ещё найденных магазинов не показано: {hidden_found}."
                )
            if hidden_unknown:
                self.preview_warnings.append(
                    f"Ещё неизвестных магазинов не показано: {hidden_unknown}."
                )
            if hidden_conflicts:
                self.preview_warnings.append(
                    f"Ещё конфликтов не показано: {hidden_conflicts}."
                )

            self.preview_ready = True
            self.preview_status = "Предварительный просмотр готов"
            self.status = "Проверьте сводку и подтвердите обработку"

        except PreviewError as error:
            self._reset_preview()
            self.preview_status = "Не удалось построить предварительный просмотр"
            self.status = "Ошибка предварительного просмотра"
            self.error_text = str(error)
        except Exception:
            self._reset_preview()
            self.preview_status = "Не удалось построить предварительный просмотр"
            self.status = "Ошибка предварительного просмотра"
            self.error_text = traceback.format_exc()
        finally:
            self.is_previewing = False

    def process_order(self):
        if not self.uploaded_file_path:
            self.status = "Сначала загрузите Excel-файл"
            return

        if (
            not self.preview_ready
            or self.preview_source != self.uploaded_file_path
            or self.preview_mode != self.mode
        ):
            self.status = "Сначала постройте предварительный просмотр для этого режима"
            return

        self.is_processing = True
        self.status = "Обработка заказа..."
        self.error_text = ""

        try:
            stores_file = paths.stores_file_for(self.mode)
            settings = load_settings()

            stores = load_stores(stores_file)
            fills = [green_fill, yellow_fill, blue_fill, purple_fill]
            groups = build_groups(stores, fills)

            output_file, log_file, stats = run_pipeline(
                self.uploaded_file_path,
                settings,
                groups,
                conflict_fill,
            )

            route_totals = list(stats.get("route_totals", {}).values())
            while len(route_totals) < 4:
                route_totals.append(0)

            self.route_totals = [format_number(total) for total in route_totals]
            self.grand_total = format_number(sum(route_totals))
            self.conflict_count = int(stats.get("conflict_count", 0))
            self.unknown_count = len(stats.get("unknown_stores", []))
            self.output_file = str(output_file)
            self.log_file = str(log_file)
            self.status = "Обработка завершена"

            record_processing(self.selected_file, stats)
            processed_at = was_processed(self.selected_file)
            self.duplicate_note = (
                f"Этот файл уже обрабатывался {processed_at}. "
                "Повторная обработка обновит суммы, а не добавит их ещё раз."
            )
            self.load_history()
            self._reset_preview()

        except Exception:
            self.status = "Ошибка обработки"
            self.error_text = traceback.format_exc()

        finally:
            self.is_processing = False


def theme_value(light: str, dark: str):
    return rx.cond(State.theme == "light", light, dark)


def page_bg():
    return theme_value("#f6f8fa", "#0b0f14")


def surface():
    return theme_value("#ffffff", "#111820")


def surface_alt():
    return theme_value("#f1f4f7", "#16212b")


def border():
    return theme_value("#d9e1e8", "#24313d")


def text():
    return theme_value("#101820", "#f3f6f8")


def muted():
    return theme_value("#66717d", "#8b98a5")


def button_base(**props):
    return {
        "height": "44px",
        "border_radius": "9px",
        "font_weight": "700",
        "transition": "160ms ease",
        "cursor": "pointer",
        **props,
    }


def primary_button(label: str, on_click=None, width: str = "230px", disabled=False):
    return rx.button(
        label,
        on_click=on_click,
        width=width,
        disabled=disabled,
        color="white",
        background=ACCENT,
        _hover={"background": ACCENT_HOVER},
        **button_base()
    )


def secondary_button(label: str, on_click=None, width: str = "156px", disabled=False):
    return rx.button(
        label,
        on_click=on_click,
        width=width,
        disabled=disabled,
        color=text(),
        background=surface_alt(),
        border=f"1px solid {border()}",
        _hover={"background": theme_value("#e4ebf1", "#223140")},
        **button_base()
    )


def nav_button(label: str, icon: str):
    active = State.current_page == label

    children = [
        fa_icon(tag=icon, size=17),
        rx.text(label, font_size="14px"),
    ]
    if label == "Почта":
        children.extend([
            rx.spacer(),
            rx.cond(
                State.mail_new_orders_count > 0,
                rx.badge(
                    State.mail_new_orders_count,
                    color_scheme="red",
                    variant="solid",
                    border_radius="999px",
                ),
                rx.box(),
            ),
        ])

    return rx.button(
        *children,
        on_click=State.set_page(label),
        width="100%",
        justify_content="flex-start",
        gap="10px",
        color=rx.cond(active, "white", muted()),
        background=rx.cond(active, ACCENT, "transparent"),
        _hover={"background": rx.cond(active, ACCENT_HOVER, theme_value("#edf2f7", "#16212b"))},
        **button_base(height="42px", font_weight=rx.cond(active, "700", "500"))
    )


def segment_button(label: str, current, on_click):
    active = current == label

    return rx.button(
        label,
        on_click=on_click,
        height="36px",
        min_width="96px",
        border_radius="7px",
        color=rx.cond(active, "white", muted()),
        background=rx.cond(active, ACCENT, "transparent"),
        border=rx.cond(active, f"1px solid {ACCENT}", "1px solid transparent"),
        box_shadow=rx.cond(active, "0 0 0 3px rgba(31, 136, 61, 0.18)", "none"),
        _hover={
            "background": rx.cond(active, ACCENT_HOVER, theme_value("#e4ebf1", "#223140"))
        },
        font_weight=rx.cond(active, "700", "600"),
    )


def segmented_control(values: list[str], current, setter):
    return rx.hstack(
        *[
            segment_button(value, current, setter(value))
            for value in values
        ],
        spacing="1",
        padding="4px",
        border=f"1px solid {border()}",
        border_radius="10px",
        background=surface_alt(),
        width="fit-content",
    )


def muted_text(*parts, size="12px"):
    return rx.text(*parts, color=muted(), font_size=size)


def stat_card(icon: str, tint_key: str, title: str, value, hint_node):
    color, tint_bg = ICON_TINTS[tint_key]

    return rx.hstack(
        rx.box(
            fa_icon(tag=icon, size=20, color=color),
            display="flex",
            align_items="center",
            justify_content="center",
            width="44px",
            height="44px",
            min_width="44px",
            border_radius="12px",
            background=tint_bg,
        ),
        rx.vstack(
            rx.text(value, color=text(), font_size="26px", font_weight="800", line_height="1.1"),
            rx.text(title, color=muted(), font_size="13px", font_weight="600"),
            hint_node,
            align="start",
            spacing="1",
        ),
        spacing="4",
        align="center",
        padding="18px",
        border=f"1px solid {border()}",
        border_radius="14px",
        background=surface(),
        box_shadow=theme_value("0 1px 3px rgba(16, 24, 32, 0.06)", "none"),
        width="100%",
    )


def sidebar_logo():
    return rx.hstack(
        rx.box(
            fa_icon(tag="boxes", size=18, color="white"),
            display="flex",
            align_items="center",
            justify_content="center",
            width="34px",
            height="34px",
            border_radius="9px",
            background=ACCENT,
        ),
        rx.vstack(
            rx.heading("Orders", color=text(), size="5", line_height="1.1"),
            rx.text("Обработка заказов v2.0", color=muted(), font_size="11px"),
            align="start",
            spacing="0",
        ),
        spacing="3",
        align="center",
        width="100%",
    )


def theme_switch_row():
    return rx.hstack(
        rx.cond(
            State.theme == "light",
            fa_icon(tag="sun", size=16, color=muted()),
            fa_icon(tag="moon", size=16, color=muted()),
        ),
        rx.text("Тёмная тема", color=text(), font_size="13px", font_weight="600"),
        rx.spacer(),
        rx.switch(
            checked=State.theme == "dark",
            on_change=State.set_dark_mode,
            color_scheme="green",
        ),
        width="100%",
        align="center",
        spacing="2",
        padding="12px 14px",
        border=f"1px solid {border()}",
        border_radius="12px",
        background=surface_alt(),
    )


def sidebar():
    return rx.vstack(
        sidebar_logo(),
        rx.vstack(
            muted_text("ГЛАВНОЕ МЕНЮ", size="11px"),
            rx.vstack(
                *[nav_button(label, icon) for label, icon in NAV_ITEMS],
                spacing="2",
                width="100%",
            ),
            align="start",
            spacing="3",
            width="100%",
        ),
        rx.spacer(),
        theme_switch_row(),
        align="start",
        spacing="6",
        width="250px",
        min_width="250px",
        height="100vh",
        padding="28px 14px 18px",
        background=theme_value("#ffffff", "#090d12"),
        border_right=f"1px solid {border()}",
    )


def upload_area():
    return rx.upload(
        rx.hstack(
            rx.box(
                fa_icon(tag="upload", size=18, color=ICON_TINTS["green"][0]),
                display="flex",
                align_items="center",
                justify_content="center",
                width="40px",
                height="40px",
                min_width="40px",
                border_radius="10px",
                background=ICON_TINTS["green"][1],
            ),
            rx.vstack(
                rx.text("1. Выберите Excel-файл", color=text(), font_size="15px", font_weight="800"),
                rx.text(f"Поддерживаются форматы: {SUPPORTED_EXCEL_LABEL}", color=muted(), font_size="12px"),
                rx.vstack(
                    rx.foreach(
                        rx.selected_files(UPLOAD_ID),
                        lambda file: rx.text(file, color=ACCENT, font_size="13px", font_weight="700"),
                    ),
                    align="start",
                    spacing="1",
                    width="100%",
                ),
                rx.text("Загруженный файл: ", State.selected_file, color=muted(), font_size="12px"),
                align="start",
                spacing="2",
                width="100%",
            ),
            spacing="3",
            align="start",
            width="100%",
        ),
        id=UPLOAD_ID,
        accept=EXCEL_MIME_TYPES,
        max_files=1,
        border=f"1px dashed {border()}",
        border_radius="10px",
        background=surface_alt(),
        padding="18px",
        width="100%",
        cursor="pointer",
    )


def order_panel():
    return rx.vstack(
        rx.hstack(
            rx.vstack(
                rx.heading("Новый заказ", color=text(), size="5"),
                rx.text("Выберите файл, загрузите его, затем укажите режим обработки.", color=muted(), font_size="13px"),
                align="start",
                spacing="1",
            ),
            rx.spacer(),
            width="100%",
            align="center",
        ),
        upload_area(),
        rx.hstack(
            rx.vstack(
                rx.text("2. Загрузите выбранный файл", color=text(), font_size="14px", font_weight="800"),
                rx.text("После загрузки файл будет доступен для обработки.", color=muted(), font_size="12px"),
                align="start",
                spacing="1",
            ),
            rx.spacer(),
            secondary_button(
                "Загрузить выбранный",
                width="190px",
                on_click=State.handle_upload(rx.upload_files(upload_id=UPLOAD_ID)),
            ),
            width="100%",
            align="center",
            padding="14px 16px",
            border=f"1px solid {border()}",
            border_radius="10px",
            background=surface_alt(),
        ),
        rx.cond(
            State.duplicate_note != "",
            rx.hstack(
                fa_icon(tag="triangle_alert", size=15, color="#f5a623"),
                rx.text(State.duplicate_note, color=text(), font_size="12px"),
                spacing="2",
                align="center",
                width="100%",
                padding="10px 14px",
                border="1px solid rgba(245, 166, 35, 0.35)",
                border_radius="10px",
                background="rgba(245, 166, 35, 0.10)",
            ),
            rx.box(),
        ),
        rx.hstack(
            rx.vstack(
                rx.text("3. Режим обработки", color=text(), font_size="14px", font_weight="800"),
                segmented_control(["Город", "Область"], State.mode, State.set_mode),
                rx.cond(
                    State.mode_auto_note != "",
                    rx.text(State.mode_auto_note, color=muted(), font_size="12px"),
                    rx.box(),
                ),
                align="start",
                spacing="2",
            ),
            rx.spacer(),
            secondary_button(
                rx.cond(State.is_previewing, "Анализ...", "Показать просмотр"),
                on_click=State.preview_order,
                width="190px",
                disabled=State.is_processing,
            ),
            width="100%",
            align="center",
            padding="14px 16px",
            border=f"1px solid {border()}",
            border_radius="10px",
            background=surface_alt(),
        ),
        rx.cond(
            State.preview_ready,
            order_preview_panel(),
            rx.box(),
        ),
        primary_button(
            rx.cond(State.is_processing, "Обработка...", "Подтвердить обработку"),
            on_click=State.process_order,
            disabled=State.is_processing,
            width="100%",
        ),
        rx.text(State.status, color=muted(), font_size="13px"),
        rx.cond(State.output_file != "", processing_summary(), rx.box()),
        rx.cond(
            State.error_text != "",
            rx.code_block(
                State.error_text,
                language="python",
                width="100%",
                max_height="260px",
                overflow_y="auto",
            ),
            rx.box(),
        ),
        spacing="5",
        padding="24px",
        border=f"1px solid {border()}",
        border_radius="14px",
        background=surface(),
        box_shadow=theme_value("0 1px 3px rgba(16, 24, 32, 0.06)", "none"),
        width="100%",
    )


def result_metric(label: str, value):
    return rx.vstack(
        rx.text(label, color=muted(), font_size="12px"),
        rx.text(value, color=text(), font_size="22px", font_weight="800"),
        align="start",
        spacing="1",
        padding="14px",
        border=f"1px solid {border()}",
        border_radius="10px",
        background=surface_alt(),
        width="100%",
    )


def route_result(label: str, value):
    return rx.hstack(
        rx.text(label, color=text(), font_size="14px", font_weight="700"),
        rx.spacer(),
        rx.text(value, color=text(), font_size="14px", font_weight="800"),
        width="100%",
        padding="11px 12px",
        border_radius="9px",
        background=surface_alt(),
    )


def preview_metric(label: str, value):
    return rx.vstack(
        rx.text(label, color=muted(), font_size="12px"),
        rx.text(value, color=text(), font_size="20px", font_weight="800"),
        align="start",
        spacing="1",
        padding="12px",
        border=f"1px solid {border()}",
        border_radius="10px",
        background=surface_alt(),
        width="100%",
    )


def order_preview_panel():
    return rx.vstack(
        rx.hstack(
            rx.vstack(
                rx.heading("Предварительный просмотр", color=text(), size="4"),
                rx.text(State.preview_status, color=muted(), font_size="12px"),
                align="start",
                spacing="1",
            ),
            rx.spacer(),
            secondary_button(
                "Обновить просмотр",
                on_click=State.preview_order,
                width="190px",
                disabled=State.is_previewing,
            ),
            width="100%",
            align="center",
        ),
        rx.text(State.preview_file_info, color=text(), font_size="13px", font_weight="700"),
        rx.text(State.preview_sheet_info, color=muted(), font_size="12px"),
        rx.text(
            "Режим: ",
            State.preview_mode,
            color=text(),
            font_size="13px",
            font_weight="700",
        ),
        rx.text(
            rx.cond(
                State.preview_document_type != "",
                State.preview_document_type,
                "",
            ),
            color=text(),
            font_size="13px",
        ),
        rx.grid(
            preview_metric("Строк заказа", State.preview_order_rows),
            preview_metric("Найдено совпадений", State.preview_match_count),
            preview_metric("Общий объём", State.preview_grand_total),
            columns="3",
            spacing="3",
            width="100%",
        ),
        rx.vstack(
            rx.text("По маршрутам", color=text(), font_size="13px", font_weight="800"),
            rx.foreach(
                State.preview_route_rows,
                lambda route: rx.text(route, color=text(), font_size="13px"),
            ),
            align="start",
            spacing="1",
            width="100%",
        ),
        rx.cond(
            State.preview_found_stores.length() > 0,
            rx.vstack(
                rx.text("Найденные магазины", color=text(), font_size="13px", font_weight="800"),
                rx.foreach(
                    State.preview_found_stores,
                    lambda store: rx.text(store, color=muted(), font_size="12px"),
                ),
                align="start",
                spacing="1",
                width="100%",
            ),
            rx.box(),
        ),
        rx.cond(
            State.preview_warnings.length() > 0,
            rx.vstack(
                rx.text("Предупреждения", color="#f5a623", font_size="13px", font_weight="800"),
                rx.foreach(
                    State.preview_warnings,
                    lambda warning: rx.text(f"⚠ {warning}", color=text(), font_size="12px"),
                ),
                align="start",
                spacing="1",
                width="100%",
                padding="10px 12px",
                border="1px solid rgba(245, 166, 35, 0.35)",
                border_radius="10px",
                background="rgba(245, 166, 35, 0.10)",
            ),
            rx.box(),
        ),
        rx.cond(
            State.preview_unknown_stores.length() > 0,
            rx.vstack(
                rx.text("Неизвестные магазины", color=text(), font_size="13px", font_weight="800"),
                rx.foreach(
                    State.preview_unknown_stores,
                    lambda store: rx.text(store, color=muted(), font_size="12px"),
                ),
                align="start",
                spacing="1",
                width="100%",
            ),
            rx.box(),
        ),
        rx.cond(
            State.preview_conflicts.length() > 0,
            rx.vstack(
                rx.text("Конфликты", color=text(), font_size="13px", font_weight="800"),
                rx.foreach(
                    State.preview_conflicts,
                    lambda item: rx.text(item, color=muted(), font_size="12px"),
                ),
                align="start",
                spacing="1",
                width="100%",
            ),
            rx.box(),
        ),
        padding="16px",
        border=f"1px solid {border()}",
        border_radius="10px",
        background=surface_alt(),
        align="start",
        spacing="3",
        width="100%",
    )


def processing_summary():
    return rx.vstack(
        rx.grid(
            result_metric("Общий итог", State.grand_total),
            result_metric("Конфликты", State.conflict_count),
            result_metric("Неизвестные магазины", State.unknown_count),
            columns="3",
            spacing="3",
            width="100%",
        ),
        rx.vstack(
            *[
                route_result(f"Маршрут №{index + 1}", State.route_totals[index])
                for index in range(len(ROUTE_KEYS))
            ],
            spacing="2",
            width="100%",
        ),
        rx.vstack(
            rx.text("Готовый файл", color=muted(), font_size="12px"),
            rx.text(State.output_file, color=text(), font_size="13px", word_break="break-all"),
            rx.text("Лог", color=muted(), font_size="12px", margin_top="8px"),
            rx.text(State.log_file, color=text(), font_size="13px", word_break="break-all"),
            align="start",
            spacing="1",
            width="100%",
        ),
        spacing="4",
        width="100%",
    )


def history_panel():
    return rx.vstack(
        rx.hstack(
            fa_icon(tag="history", size=17, color=text()),
            rx.heading("Последние обработки", color=text(), size="4"),
            spacing="2",
            align="center",
        ),
        rx.vstack(
            history_row(State.history_1_file, State.history_1_time),
            history_row(State.history_2_file, State.history_2_time),
            history_row(State.history_3_file, State.history_3_time),
            spacing="2",
            width="100%",
        ),
        align="start",
        spacing="4",
        padding="24px",
        border=f"1px solid {border()}",
        border_radius="14px",
        background=surface(),
        box_shadow=theme_value("0 1px 3px rgba(16, 24, 32, 0.06)", "none"),
        width="100%",
    )


def history_row(filename, time):
    return rx.hstack(
        rx.box(
            fa_icon(tag="file_spreadsheet", size=16, color=muted()),
            display="flex",
            align_items="center",
            justify_content="center",
            width="34px",
            height="34px",
            min_width="34px",
            border_radius="9px",
            background=surface(),
        ),
        rx.vstack(
            rx.text(filename, color=text(), font_weight="700", font_size="14px"),
            rx.text("Обработка заказа", color=muted(), font_size="12px"),
            align="start",
            spacing="1",
        ),
        rx.spacer(),
        rx.text(time, color=muted(), font_size="13px"),
        spacing="3",
        align="center",
        width="100%",
        padding="12px",
        border_radius="10px",
        background=surface_alt(),
        cursor="pointer",
        on_click=State.open_order_details(filename, time),
        _hover={"background": theme_value("#e8edf2", "#1c2a36")},
    )


def page_shell(*children):
    return rx.vstack(
        *children,
        align="start",
        spacing="5",
        width="100%",
        min_height="100vh",
        padding="28px",
        background=page_bg(),
    )


def topbar(title: str, subtitle: str, actions=None):
    return rx.hstack(
        rx.vstack(
            rx.heading(title, color=text(), size="7"),
            rx.text(subtitle, color=muted(), font_size="13px"),
            align="start",
            spacing="1",
        ),
        rx.spacer(),
        *(actions or []),
        width="100%",
        align="center",
    )


def panel_shell(*children):
    return rx.vstack(
        *children,
        align="start",
        spacing="4",
        padding="24px",
        border=f"1px solid {border()}",
        border_radius="14px",
        background=surface(),
        box_shadow=theme_value("0 1px 3px rgba(16, 24, 32, 0.06)", "none"),
        width="100%",
    )


def panel_title(icon: str, title: str):
    return rx.hstack(
        fa_icon(tag=icon, size=17, color=text()),
        rx.heading(title, color=text(), size="4"),
        spacing="2",
        align="center",
    )


def volume_chart_panel():
    return panel_shell(
        panel_title("chart_no_axes_column", "Вывезенный объём"),
        muted_text(f"Сумма по маршрутам за последние {VOLUME_CHART_DAYS} дней", size="12px"),
        rx.recharts.responsive_container(
            rx.recharts.bar_chart(
                rx.recharts.cartesian_grid(stroke_dasharray="3 3", stroke=border()),
                rx.recharts.x_axis(data_key="date", stroke=muted(), interval=2),
                rx.recharts.y_axis(stroke=muted()),
                rx.recharts.tooltip(),
                rx.recharts.legend(),
                rx.recharts.bar(data_key="Маршрут 1", stack_id="a", fill=ROUTE_COLORS[0]),
                rx.recharts.bar(data_key="Маршрут 2", stack_id="a", fill=ROUTE_COLORS[1]),
                rx.recharts.bar(data_key="Маршрут 3", stack_id="a", fill=ROUTE_COLORS[2]),
                rx.recharts.bar(data_key="Маршрут 4", stack_id="a", fill=ROUTE_COLORS[3]),
                data=State.volume_chart_data,
                margin={"left": 0, "right": 8, "top": 4, "bottom": 0},
            ),
            width="100%",
            height=280,
        ),
    )


def dashboard_tracking_preview():
    return panel_shell(
        rx.hstack(
            panel_title("truck", "Трекинг машин"),
            rx.spacer(),
            rx.cond(
                State.tracking_running,
                rx.badge("В движении", color_scheme="green", variant="soft"),
                rx.badge("Остановлено", color_scheme="gray", variant="soft"),
            ),
            width="100%",
            align="center",
        ),
        rx.box(
            rx.html(State.map_svg),
            width="100%",
            border_radius="10px",
            background=surface_alt(),
            padding="12px",
            overflow="hidden",
        ),
        secondary_button(
            "Открыть Трекинг",
            on_click=State.set_page("Трекинг"),
            width="100%",
        ),
    )


def overview_page():
    return page_shell(
        topbar(
            "Dashboard",
            "Обзор: заказы, магазины и маршруты — и переход в нужный раздел.",
        ),
        rx.grid(
            stat_card(
                "package", "green",
                "Заказы сегодня", State.orders_today_count,
                muted_text("Всего обработано: ", State.orders_total_count),
            ),
            stat_card(
                "store", "blue",
                "Магазинов в базе", State.stores_total_count,
                muted_text("Город + Область"),
            ),
            stat_card(
                "route", "violet",
                "Маршрутов", 4,
                muted_text("готовы к выгрузке"),
            ),
            columns="3",
            spacing="4",
            width="100%",
        ),
        rx.grid(
            volume_chart_panel(),
            dashboard_tracking_preview(),
            columns="2",
            spacing="4",
            width="100%",
            align_items="start",
        ),
    )


def orders_page():
    return page_shell(
        topbar(
            "Заказы",
            "Загрузите файл заказа, выберите режим обработки и запустите обработку.",
        ),
        order_panel(),
    )


def history_page():
    return page_shell(
        topbar("История", "Нажмите на заказ, чтобы открыть его накладные и дополнительные данные."),
        panel_shell(
            panel_title("history", "Обработанные заказы"),
            rx.cond(
                State.history_items.length() > 0,
                rx.vstack(
                    rx.foreach(
                        State.history_items,
                        lambda item: history_row(item["file"], item["time"]),
                    ),
                    spacing="2",
                    width="100%",
                ),
                rx.text("Обработанных заказов пока нет", color=muted(), font_size="13px"),
            ),
        ),
    )




def order_invoice_row(item, linked: bool):
    return rx.vstack(
        rx.hstack(
            fa_icon(tag="file_pdf", size=16, color="#3b82f6"),
            rx.text(item["file"], color=text(), font_size="13px", font_weight="700"),
            rx.spacer(),
            rx.text(item["received"], color=muted(), font_size="11px"),
            width="100%",
            align="center",
        ),
        rx.hstack(
            rx.text("Источник: ", item["source"], color=muted(), font_size="12px"),
            rx.cond(
                item["date_relation"] != "",
                rx.badge(
                    item["date_relation"],
                    color_scheme="green",
                    variant="soft",
                ),
                rx.box(),
            ),
            spacing="2",
            align="center",
        ),
        rx.cond(
            item["subject"] != "",
            rx.text("Тема: ", item["subject"], color=muted(), font_size="12px"),
            rx.box(),
        ),
        rx.hstack(
            secondary_button(
                "Открыть PDF",
                on_click=State.open_mail_attachment(item["path"]),
                width="130px",
            ),
            secondary_button(
                "Отвязать" if linked else "Привязать",
                on_click=(
                    State.detach_invoice(item["path"])
                    if linked
                    else State.attach_invoice(item["path"])
                ),
                width="120px",
            ),
            spacing="2",
        ),
        align="start",
        spacing="2",
        width="100%",
        padding="14px",
        border=f"1px solid {border()}",
        border_radius="10px",
        background=surface_alt(),
    )


def order_details_drawer():
    return rx.cond(
        State.order_details_open,
        rx.fragment(
            rx.box(
                position="fixed",
                inset="0",
                background="rgba(0, 0, 0, 0.48)",
                z_index="90",
                on_click=State.close_order_details,
            ),
            rx.vstack(
                rx.hstack(
                    rx.vstack(
                        rx.text("ЗАКАЗ", color=muted(), font_size="11px", font_weight="700"),
                        rx.heading(State.selected_order, color=text(), size="5"),
                        rx.text(
                            State.selected_order_time_label,
                            ": ",
                            State.selected_order_time,
                            color=muted(),
                            font_size="12px",
                        ),
                        align="start",
                        spacing="1",
                    ),
                    rx.spacer(),
                    rx.button(
                        fa_icon(tag="x", size=16),
                        on_click=State.close_order_details,
                        variant="ghost",
                        color=muted(),
                        cursor="pointer",
                    ),
                    width="100%",
                    align="start",
                ),
                segmented_control(
                    ["Накладные", "Дополнительно"],
                    State.order_detail_tab,
                    State.set_order_detail_tab,
                ),
                rx.cond(
                    State.order_detail_tab == "Накладные",
                    rx.vstack(
                        rx.heading("Привязанные накладные", color=text(), size="4"),
                        rx.cond(
                            State.order_invoices.length() > 0,
                            rx.vstack(
                                rx.foreach(
                                    State.order_invoices,
                                    lambda item: order_invoice_row(item, True),
                                ),
                                spacing="2",
                                width="100%",
                            ),
                            rx.text("К этому заказу накладные пока не привязаны", color=muted(), font_size="13px"),
                        ),
                        rx.divider(),
                        rx.heading(State.available_invoices_title, color=text(), size="4"),
                        rx.text(
                            State.invoice_date_hint,
                            color=muted(),
                            font_size="12px",
                        ),
                        rx.input(
                            value=State.invoice_search,
                            on_change=State.set_invoice_search,
                            placeholder="Поиск по файлу, источнику или теме",
                            width="100%",
                            height="42px",
                        ),
                        rx.cond(
                            State.available_invoices.length() > 0,
                            rx.vstack(
                                rx.foreach(
                                    State.available_invoices,
                                    lambda item: order_invoice_row(item, False),
                                ),
                                spacing="2",
                                width="100%",
                            ),
                            rx.text(
                                State.available_invoices_empty,
                                color=muted(),
                                font_size="13px",
                            ),
                        ),
                        rx.cond(
                            State.other_invoices.length() > 0,
                            rx.vstack(
                                rx.divider(),
                                rx.heading("Другие накладные", color=text(), size="4"),
                                rx.text(
                                    "Дата, тип заказа или группа файла не совпали. При необходимости файл можно привязать вручную.",
                                    color=muted(),
                                    font_size="12px",
                                ),
                                rx.foreach(
                                    State.other_invoices,
                                    lambda item: order_invoice_row(item, False),
                                ),
                                spacing="2",
                                width="100%",
                                align="start",
                            ),
                            rx.box(),
                        ),
                        spacing="3",
                        width="100%",
                        align="start",
                    ),
                    rx.vstack(
                        rx.heading("Дополнительные данные", color=text(), size="4"),
                        rx.text(
                            "Здесь можно будет добавить комментарии, документы и другие разделы заказа.",
                            color=muted(),
                            font_size="13px",
                        ),
                        align="start",
                        spacing="2",
                    ),
                ),
                rx.cond(
                    State.order_detail_status != "",
                    rx.text(State.order_detail_status, color=ACCENT, font_size="12px"),
                    rx.box(),
                ),
                align="start",
                spacing="4",
                position="fixed",
                top="0",
                right="0",
                width=["100%", "560px"],
                height="100vh",
                overflow_y="auto",
                padding="24px",
                background=surface(),
                border_left=f"1px solid {border()}",
                box_shadow="-16px 0 40px rgba(0, 0, 0, 0.22)",
                z_index="100",
            ),
        ),
        rx.box(),
    )


def mail_setup_hint():
    return panel_shell(
        panel_title("key", "Подключение к почте"),
        rx.text(
            "Введите адрес Gmail и ключ приложения — файл настроек создастся автоматически.",
            color=muted(),
            font_size="13px",
        ),
        rx.vstack(
            rx.text(
                "Электронная почта",
                color=text(),
                font_size="13px",
                font_weight="700",
            ),
            rx.input(
                value=State.mail_email,
                on_change=State.set_mail_email,
                placeholder="your-address@gmail.com",
                type="email",
                width="100%",
                height="44px",
            ),
            align="start",
            spacing="2",
            width="100%",
        ),
        rx.vstack(
            rx.text(
                "Ключ приложения (пароль приложения)",
                color=text(),
                font_size="13px",
                font_weight="700",
            ),
            rx.input(
                value=State.mail_app_password,
                on_change=State.set_mail_app_password,
                placeholder="xxxx xxxx xxxx xxxx",
                type="password",
                width="100%",
                height="44px",
            ),
            rx.cond(
                State.mail_configured,
                rx.text(
                    "Оставьте поле пустым, чтобы сохранить действующий ключ.",
                    color=muted(),
                    font_size="12px",
                ),
                rx.text(
                    "Обычный пароль Google не подходит — нужен отдельный ключ приложения.",
                    color=muted(),
                    font_size="12px",
                ),
            ),
            align="start",
            spacing="2",
            width="100%",
        ),
        rx.flex(
            primary_button(
                "Сохранить и подключить",
                on_click=State.save_mail_credentials_form,
                width="230px",
            ),
            rx.link(
                rx.hstack(
                    fa_icon(tag="key", size=14, color=ACCENT),
                    rx.text("Получить ключ приложения Google"),
                    spacing="2",
                    align="center",
                ),
                href=MAIL_APP_PASSWORD_URL,
                target="_blank",
                color=ACCENT,
                font_size="13px",
                font_weight="700",
                text_decoration="none",
            ),
            gap="16px",
            align="center",
            wrap="wrap",
            width="100%",
        ),
        rx.cond(
            State.mail_credentials_status != "",
            rx.text(
                State.mail_credentials_status,
                color=rx.cond(
                    State.mail_credentials_status == "Данные почты сохранены",
                    ACCENT,
                    "#e5484d",
                ),
                font_size="12px",
            ),
            rx.box(),
        ),
        rx.text(
            "Адрес и ключ сохраняются только на этом компьютере в config/mail.json; файл не попадает в git.",
            color=muted(),
            font_size="12px",
        ),
    )


def mail_verdict_badge(is_order):
    return rx.cond(
        is_order,
        rx.hstack(
            fa_icon(tag="circle_check", size=13, color=ACCENT),
            rx.text("Похоже на заказ", color=ACCENT, font_size="12px", font_weight="700"),
            spacing="2",
            align="center",
        ),
        rx.hstack(
            fa_icon(tag="circle_x", size=13, color="#e5484d"),
            rx.text("Не заказ", color="#e5484d", font_size="12px", font_weight="700"),
            spacing="2",
            align="center",
        ),
    )


def mail_item_row(item):
    return rx.vstack(
        rx.hstack(
            rx.cond(
                item["is_invoice"],
                fa_icon(tag="file_pdf", size=15, color=muted()),
                rx.cond(
                    item["has_file"],
                    fa_icon(tag="file_spreadsheet", size=15, color=muted()),
                    fa_icon(tag="mail", size=15, color=muted()),
                ),
            ),
            rx.text(item["file"], color=text(), font_size="14px", font_weight="700"),
            rx.spacer(),
            rx.cond(
                item["is_invoice"],
                rx.badge("Накладная", color_scheme="blue", variant="soft"),
                rx.cond(
                    item["kind"] == KIND_MESSAGE,
                    rx.badge("Письмо", color_scheme="gray", variant="soft"),
                    mail_verdict_badge(item["is_order"]),
                ),
            ),
            width="100%",
            align="center",
            spacing="2",
        ),
        rx.hstack(
            rx.text("Источник: ", item["source"], color=muted(), font_size="12px"),
            rx.text("· ", item["received"], color=muted(), font_size="12px"),
            spacing="1",
        ),
        rx.text("От: ", item["sender"], color=muted(), font_size="12px"),
        rx.cond(
            item["subject"] != "",
            rx.text("Тема: ", item["subject"], color=muted(), font_size="12px"),
            rx.box(),
        ),
        rx.cond(
            item["is_order"],
            rx.hstack(
                rx.text(
                    "Режим: ", item["mode"],
                    " · магазинов найдено: ", item["matches"],
                    color=muted(),
                    font_size="12px",
                ),
                rx.spacer(),
                secondary_button(
                    "Взять в обработку",
                    on_click=State.take_mail_order(
                        item["path"],
                        item["file"],
                        item["received"],
                    ),
                    width="180px",
                ),
                width="100%",
                align="center",
            ),
            rx.cond(
                item["is_invoice"],
                rx.hstack(
                    rx.cond(
                        item["order_file"] != "",
                        rx.text("Привязана к: ", item["order_file"], color=ACCENT, font_size="12px"),
                        rx.text("Ещё не привязана к заказу", color=muted(), font_size="12px"),
                    ),
                    rx.spacer(),
                    secondary_button(
                        "Открыть PDF",
                        on_click=State.open_mail_attachment(item["path"]),
                        width="140px",
                    ),
                    width="100%",
                    align="center",
                ),
                rx.cond(
                    item["reason"] != "",
                    rx.text(item["reason"], color="#e5484d", font_size="12px"),
                    rx.box(),
                ),
            ),
        ),
        align="start",
        spacing="2",
        width="100%",
        padding="14px 16px",
        border=f"1px solid {border()}",
        border_radius="10px",
        background=surface_alt(),
    )


def mail_page():
    return page_shell(
        topbar(
            "Почта",
            "Заказы, пришедшие письмом. Файл скачивается и проверяется, "
            "обработка — по кнопке.",
        ),
        rx.cond(
            State.mail_configured,
            rx.vstack(
                rx.cond(
                    State.mail_credentials_editing,
                    mail_setup_hint(),
                    rx.box(),
                ),
                panel_shell(
                    rx.hstack(
                        panel_title("inbox", "Проверка почты"),
                        rx.spacer(),
                        secondary_button(
                            "Изменить вход",
                            on_click=State.edit_mail_credentials,
                            width="150px",
                        ),
                        rx.hstack(
                            rx.text(
                                "Проверять каждые ", State.mail_interval, " мин",
                                color=muted(),
                                font_size="12px",
                            ),
                            rx.switch(
                                checked=State.mail_auto,
                                on_change=State.toggle_mail_auto,
                                color_scheme="green",
                            ),
                            spacing="2",
                            align="center",
                        ),
                        width="100%",
                        align="center",
                        wrap="wrap",
                    ),
                    rx.flex(
                        secondary_button(
                            rx.cond(
                                State.mail_connection_checking,
                                "Проверяю...",
                                "Проверить соединение",
                            ),
                            on_click=State.check_mail_connection_now,
                            width="210px",
                            disabled=State.mail_checking | State.mail_connection_checking,
                        ),
                        primary_button(
                            rx.cond(State.mail_checking, "Проверяю...", "Проверить почту"),
                            on_click=State.check_mail_now,
                            width="200px",
                            disabled=State.mail_checking | State.mail_connection_checking,
                        ),
                        rx.text(State.mail_status, color=muted(), font_size="13px"),
                        gap="14px",
                        align="center",
                        wrap="wrap",
                        width="100%",
                    ),
                    rx.text(
                        "Последняя проверка: ",
                        State.mail_last_check,
                        color=muted(),
                        font_size="12px",
                    ),
                    rx.cond(
                        State.mail_error != "",
                        rx.text(State.mail_error, color="#e5484d", font_size="12px"),
                        rx.box(),
                    ),
                ),
                rx.cond(
                    State.mail_notification != "",
                    panel_shell(
                        rx.hstack(
                            panel_title("circle_check", "Новые заказы"),
                            rx.spacer(),
                            rx.badge(
                                State.mail_new_orders_count,
                                color_scheme="green",
                                variant="solid",
                            ),
                            secondary_button(
                                "Скрыть",
                                on_click=State.clear_mail_notification,
                                width="100px",
                            ),
                            width="100%",
                            align="center",
                        ),
                        rx.text(
                            State.mail_notification,
                            color=ACCENT,
                            font_size="13px",
                            font_weight="700",
                        ),
                    ),
                    rx.box(),
                ),
                panel_shell(
                    rx.hstack(
                        panel_title("triangle_alert", "Журнал ошибок подключения"),
                        rx.spacer(),
                        secondary_button(
                            "Очистить журнал",
                            on_click=State.clear_mail_errors,
                            width="170px",
                            disabled=State.mail_error_log.length() == 0,
                        ),
                        width="100%",
                        align="center",
                    ),
                    rx.cond(
                        State.mail_error_log.length() > 0,
                        rx.vstack(
                            rx.foreach(
                                State.mail_error_log,
                                lambda entry: rx.vstack(
                                    rx.hstack(
                                        rx.text(
                                            entry["operation"],
                                            color=text(),
                                            font_size="13px",
                                            font_weight="700",
                                        ),
                                        rx.spacer(),
                                        rx.text(
                                            entry["display_time"],
                                            color=muted(),
                                            font_size="11px",
                                        ),
                                        width="100%",
                                    ),
                                    rx.text(
                                        entry["error"],
                                        color="#e5484d",
                                        font_size="12px",
                                    ),
                                    align="start",
                                    spacing="1",
                                    width="100%",
                                    padding="10px 12px",
                                    border=f"1px solid {border()}",
                                    border_radius="8px",
                                    background=surface_alt(),
                                ),
                            ),
                            spacing="2",
                            width="100%",
                            max_height="260px",
                            overflow_y="auto",
                        ),
                        rx.text(
                            "Ошибок подключения пока нет",
                            color=muted(),
                            font_size="13px",
                        ),
                    ),
                ),
                panel_shell(
                    rx.hstack(
                        panel_title("inbox", "Фильтры писем"),
                        rx.spacer(),
                        segmented_control(
                            [
                                "Все сообщения",
                                "Только заказы",
                                "Только непривязанные накладные",
                            ],
                            State.mail_kind_filter,
                            State.set_mail_kind_filter,
                        ),
                        width="100%",
                        align="center",
                    ),
                    rx.flex(
                        rx.foreach(
                            State.mail_sources,
                            lambda source: segment_button(
                                source,
                                State.mail_source,
                                State.set_mail_source(source),
                            ),
                        ),
                        gap="8px",
                        wrap="wrap",
                        width="100%",
                    ),
                ),
                rx.cond(
                    State.mail_items.length() > 0,
                    panel_shell(
                        panel_title("mail", "Письма и вложения"),
                        rx.vstack(
                            rx.foreach(State.mail_items, mail_item_row),
                            spacing="3",
                            width="100%",
                        ),
                    ),
                    rx.box(),
                ),
                spacing="4",
                width="100%",
            ),
            mail_setup_hint(),
        ),
    )


def store_row(name, on_remove):
    return rx.hstack(
        fa_icon(tag="map_pin", size=13, color=muted()),
        rx.text(name, color=text(), font_size="13px"),
        rx.spacer(),
        rx.button(
            fa_icon(tag="x", size=13),
            on_click=on_remove(name),
            size="1",
            variant="ghost",
            color=muted(),
            cursor="pointer",
        ),
        spacing="2",
        width="100%",
        align="center",
        padding="6px 10px",
        border_radius="7px",
        background=surface_alt(),
    )


def route_edit_card(index: int):
    return rx.vstack(
        rx.hstack(
            fa_icon(tag="route", size=15, color=text()),
            rx.text(f"Маршрут №{index + 1}", color=text(), font_size="15px", font_weight="800"),
            spacing="2",
            align="center",
        ),
        rx.vstack(
            rx.foreach(
                State.route_stores[index],
                lambda name: store_row(name, lambda value: State.remove_store(index, value)),
            ),
            spacing="1",
            width="100%",
            max_height="220px",
            overflow_y="auto",
        ),
        rx.hstack(
            rx.input(
                placeholder="Название магазина",
                value=State.new_store_inputs[index],
                on_change=lambda value: State.set_new_store(index, value),
                width="100%",
            ),
            rx.button(
                fa_icon(tag="plus", size=15),
                "Добавить",
                on_click=State.add_store(index),
                height="36px",
            ),
            width="100%",
            spacing="2",
        ),
        align="start",
        spacing="3",
        padding="18px",
        border=f"1px solid {border()}",
        border_radius="12px",
        background=surface(),
        box_shadow=theme_value("0 1px 3px rgba(16, 24, 32, 0.06)", "none"),
        width="100%",
    )


def routes_backup_bar():
    return rx.hstack(
        primary_button("Сохранить маршруты", on_click=State.save_routes, width="210px"),
        secondary_button("Создать копию", on_click=State.create_route_backup, width="165px"),
        rx.spacer(),
        fa_icon(tag="history", size=15, color=muted()),
        rx.select(
            State.route_backup_labels,
            value=State.selected_route_backup,
            on_change=State.set_selected_route_backup,
            placeholder="Резервные копии",
            width="270px",
        ),
        secondary_button("Восстановить", on_click=State.restore_route_backup, width="150px"),
        spacing="3",
        align="center",
        width="100%",
        wrap="wrap",
    )


def routes_page():
    return page_shell(
        topbar(
            "Маршруты",
            "Списки магазинов по маршрутам для режимов Город/Область.",
            actions=[segmented_control(["Город", "Область"], State.routes_source, State.set_routes_source)],
        ),
        rx.grid(
            *[route_edit_card(index) for index in range(len(ROUTE_KEYS))],
            columns="2",
            spacing="4",
            width="100%",
        ),
        routes_backup_bar(),
        rx.cond(
            State.routes_status != "",
            rx.text(State.routes_status, color=muted(), font_size="13px"),
            rx.box(),
        ),
    )


def start_pause_button():
    return rx.cond(
        State.tracking_running,
        secondary_button("Пауза", on_click=State.stop_tracking, width="130px"),
        primary_button("Старт симуляции", on_click=State.start_tracking, width="180px"),
    )


def tracking_controls():
    return rx.hstack(
        segmented_control(["Город", "Область"], State.tracking_source, State.set_tracking_source),
        rx.spacer(),
        start_pause_button(),
        secondary_button("Сброс", on_click=State.reset_tracking, width="110px"),
        spacing="3",
        align="center",
        width="100%",
    )


def tracking_legend_dot(color, label):
    return rx.hstack(
        rx.box(width="10px", height="10px", min_width="10px", border_radius="50%", background=color),
        rx.text(label, color=muted(), font_size="12px"),
        spacing="2",
        align="center",
    )


def tracking_legend():
    return rx.hstack(
        *[tracking_legend_dot(color, label) for label, color in zip(ROUTE_LABELS, ROUTE_COLORS)],
        tracking_legend_dot("#f5a623", "Резкий разгон"),
        tracking_legend_dot("#e5484d", "Резкое торможение"),
        spacing="5",
        wrap="wrap",
        width="100%",
    )


def tracking_map_panel():
    return rx.vstack(
        rx.hstack(
            fa_icon(tag="map", size=17, color=text()),
            rx.heading("Карта маршрутов", color=text(), size="4"),
            spacing="2",
            align="center",
        ),
        rx.box(
            rx.html(State.map_svg),
            width="100%",
            border_radius="10px",
            background=surface_alt(),
            padding="12px",
            overflow="hidden",
        ),
        tracking_legend(),
        align="start",
        spacing="4",
        padding="24px",
        border=f"1px solid {border()}",
        border_radius="14px",
        background=surface(),
        box_shadow=theme_value("0 1px 3px rgba(16, 24, 32, 0.06)", "none"),
        width="100%",
    )


def event_badge(flag):
    return rx.cond(
        flag == "harsh_brake",
        rx.text("Резкое торможение", color="#e5484d", font_size="11px", font_weight="700"),
        rx.cond(
            flag == "harsh_accel",
            rx.text("Резкий разгон", color="#f5a623", font_size="11px", font_weight="700"),
            rx.text("Плавно", color=muted(), font_size="11px"),
        ),
    )


def tracking_progress_bar(percent, color):
    return rx.box(
        rx.box(
            width=f"{percent}%",
            height="100%",
            border_radius="6px",
            background=color,
            transition="width 400ms ease",
        ),
        width="100%",
        height="8px",
        border_radius="6px",
        background=surface_alt(),
        overflow="hidden",
    )


def vehicle_card(v):
    return rx.vstack(
        rx.hstack(
            rx.box(width="10px", height="10px", min_width="10px", border_radius="50%", background=v["color"]),
            rx.text(v["label"], color=text(), font_size="14px", font_weight="800"),
            rx.spacer(),
            event_badge(v["event_flag"]),
            width="100%",
            align="center",
            spacing="2",
        ),
        rx.text(v["status"], color=muted(), font_size="12px"),
        tracking_progress_bar(v["progress_percent"], v["color"]),
        route_result("Скорость", f"{v['speed_kmh']} км/ч"),
        route_result("Рейтинг", v["score"]),
        route_result("Пробег", f"{v['distance_km']} км"),
        route_result("Резкие манёвры", v["harsh_count"]),
        align="start",
        spacing="2",
        padding="16px",
        border=f"1px solid {border()}",
        border_radius="12px",
        background=surface(),
        box_shadow=theme_value("0 1px 3px rgba(16, 24, 32, 0.06)", "none"),
        width="100%",
    )


def rating_row(v):
    return rx.hstack(
        rx.box(width="8px", height="8px", min_width="8px", border_radius="50%", background=v["color"]),
        rx.text(v["label"], color=text(), font_size="13px", font_weight="700"),
        rx.spacer(),
        rx.text(v["harsh_count"], color=muted(), font_size="12px"),
        rx.text(" рывков", color=muted(), font_size="12px"),
        rx.text(v["score"], color=text(), font_size="14px", font_weight="800"),
        spacing="2",
        align="center",
        width="100%",
        padding="10px 12px",
        border_radius="9px",
        background=surface_alt(),
    )


def rating_panel():
    return rx.vstack(
        rx.hstack(
            fa_icon(tag="award", size=17, color=text()),
            rx.heading("Рейтинг водителей", color=text(), size="4"),
            spacing="2",
            align="center",
        ),
        rx.vstack(
            rx.foreach(State.ranked_vehicles, rating_row),
            spacing="2",
            width="100%",
        ),
        align="start",
        spacing="4",
        padding="24px",
        border=f"1px solid {border()}",
        border_radius="14px",
        background=surface(),
        box_shadow=theme_value("0 1px 3px rgba(16, 24, 32, 0.06)", "none"),
        width="100%",
    )


def event_log_panel():
    return rx.vstack(
        rx.hstack(
            fa_icon(tag="list", size=17, color=text()),
            rx.heading("Журнал событий", color=text(), size="4"),
            spacing="2",
            align="center",
        ),
        rx.cond(
            State.tracking_event_log.length() == 0,
            rx.text("Событий пока нет — запустите симуляцию.", color=muted(), font_size="13px"),
            rx.vstack(
                rx.foreach(
                    State.tracking_event_log,
                    lambda entry: rx.text(entry, color=text(), font_size="12px"),
                ),
                spacing="2",
                width="100%",
                max_height="260px",
                overflow_y="auto",
            ),
        ),
        align="start",
        spacing="4",
        padding="24px",
        border=f"1px solid {border()}",
        border_radius="14px",
        background=surface(),
        box_shadow=theme_value("0 1px 3px rgba(16, 24, 32, 0.06)", "none"),
        width="100%",
    )


def tracking_view_toggle():
    return rx.hstack(
        segment_button(
            "Симуляция", State.tracking_view,
            State.set_tracking_view("Симуляция"),
        ),
        segment_button(
            "Реальные данные", State.tracking_view,
            [State.set_tracking_view("Реальные данные"), State.watch_real_data],
        ),
        spacing="1",
        padding="4px",
        border=f"1px solid {border()}",
        border_radius="10px",
        background=surface_alt(),
        width="fit-content",
    )


def simulation_section():
    return rx.vstack(
        tracking_controls(),
        rx.grid(
            stat_card(
                "route", "green",
                "Общий пробег", f"{State.tracking_total_distance} км",
                muted_text("за сессию симуляции"),
            ),
            stat_card(
                "fuel", "blue",
                "Расход топлива", f"{State.tracking_total_fuel} л",
                muted_text("≈ ", State.tracking_total_cost, " ₽"),
            ),
            stat_card(
                "triangle_alert", "violet",
                "Резкие манёвры", State.tracking_total_harsh,
                muted_text("средний рейтинг: ", State.tracking_avg_score),
            ),
            columns="3",
            spacing="4",
            width="100%",
        ),
        tracking_map_panel(),
        rx.grid(
            rx.foreach(State.vehicles, vehicle_card),
            columns="2",
            spacing="4",
            width="100%",
        ),
        rx.grid(
            rating_panel(),
            event_log_panel(),
            columns="2",
            spacing="4",
            width="100%",
            align_items="start",
        ),
        spacing="4",
        width="100%",
    )


def real_stop_row(stop):
    return rx.hstack(
        rx.cond(
            stop["status"] == "done",
            fa_icon(tag="circle_check", size=14, color=ACCENT),
            fa_icon(tag="circle", size=14, color=muted()),
        ),
        rx.text(stop["name"], color=text(), font_size="13px"),
        rx.spacer(),
        rx.cond(
            stop["status"] == "done",
            rx.text(stop["done_at"], color=muted(), font_size="11px"),
            rx.text("ожидание", color=muted(), font_size="11px"),
        ),
        width="100%",
        align="center",
        spacing="2",
        padding="6px 10px",
        border_radius="7px",
        background=surface_alt(),
    )


def real_vehicle_map(v):
    lat = v["last_lat"].to(float)
    lon = v["last_lon"].to(float)
    map_src = (
        f"https://www.openstreetmap.org/export/embed.html?bbox="
        f"{lon - 0.01}%2C{lat - 0.01}%2C{lon + 0.01}%2C{lat + 0.01}"
        f"&marker={lat}%2C{lon}"
    )

    return rx.cond(
        v["has_position"],
        rx.vstack(
            rx.text("Последний сигнал: ", v["last_ts"], color=muted(), font_size="12px"),
            rx.el.iframe(
                src=map_src,
                width="100%",
                height="200px",
                style={"border": "0", "borderRadius": "10px"},
            ),
            spacing="2",
            width="100%",
        ),
        rx.text("GPS ещё не поступал с планшета водителя.", color=muted(), font_size="12px"),
    )


def real_vehicle_card(v):
    return rx.vstack(
        rx.hstack(
            rx.box(width="10px", height="10px", min_width="10px", border_radius="50%", background=v["color"]),
            rx.text(v["label"], color=text(), font_size="15px", font_weight="800"),
            rx.spacer(),
            rx.text(v["done_count"], color=text(), font_size="13px", font_weight="700"),
            rx.text(" / ", color=muted(), font_size="13px"),
            rx.text(v["total_count"], color=muted(), font_size="13px"),
            width="100%",
            align="center",
            spacing="1",
        ),
        real_vehicle_map(v),
        rx.cond(
            v["total_count"].to(int) > 0,
            rx.vstack(
                rx.foreach(v["stops"].to(list[dict]), real_stop_row),
                spacing="2",
                width="100%",
                max_height="200px",
                overflow_y="auto",
            ),
            rx.text("Водитель ещё не открывал чек-лист сегодня.", color=muted(), font_size="12px"),
        ),
        align="start",
        spacing="3",
        padding="16px",
        border=f"1px solid {border()}",
        border_radius="12px",
        background=surface(),
        box_shadow=theme_value("0 1px 3px rgba(16, 24, 32, 0.06)", "none"),
        width="100%",
    )


def real_data_section():
    return rx.vstack(
        rx.hstack(
            rx.text(
                "Данные от водителей за сегодня — открывается на /driver, обновляется каждые ~5 сек.",
                color=muted(), font_size="13px",
            ),
            rx.spacer(),
            secondary_button("Обновить", on_click=State.refresh_real_data, width="120px"),
            width="100%",
            align="center",
        ),
        rx.grid(
            rx.foreach(State.real_vehicles, real_vehicle_card),
            columns="2",
            spacing="4",
            width="100%",
        ),
        spacing="4",
        width="100%",
    )


def tracking_page():
    return page_shell(
        topbar(
            "Трекинг",
            "Симуляция движения машин по маршрутам либо реальные данные от водителей.",
            actions=[tracking_view_toggle()],
        ),
        rx.cond(
            State.tracking_view == "Симуляция",
            simulation_section(),
            real_data_section(),
        ),
    )


def settings_toggle_row(label, hint, value, on_change):
    return rx.hstack(
        rx.vstack(
            rx.text(label, color=text(), font_size="14px", font_weight="700"),
            rx.text(hint, color=muted(), font_size="12px"),
            align="start",
            spacing="1",
        ),
        rx.spacer(),
        rx.switch(checked=value, on_change=on_change, color_scheme="green"),
        width="100%",
        align="center",
        padding="14px 16px",
        border=f"1px solid {border()}",
        border_radius="10px",
        background=surface_alt(),
    )


def version_release_card(release):
    return rx.vstack(
        rx.hstack(
            rx.vstack(
                rx.heading(release["version"], color=text(), size="4"),
                rx.cond(
                    release["date"] != "",
                    rx.badge(release["date"], color_scheme="green", variant="soft"),
                    rx.box(),
                ),
                align="start",
                spacing="2",
            ),
            rx.spacer(),
            fa_icon(tag="history", size=18, color=muted()),
            width="100%",
            align="center",
        ),
        rx.vstack(
            rx.foreach(
                release["changes"],
                lambda change: rx.hstack(
                    fa_icon(tag="circle_check", size=14, color=ACCENT),
                    rx.text(change, color=text(), font_size="13px"),
                    align="start",
                    spacing="2",
                    width="100%",
                ),
            ),
            align="start",
            spacing="2",
            width="100%",
        ),
        align="start",
        spacing="3",
        padding="18px",
        border=f"1px solid {border()}",
        border_radius="12px",
        background=surface_alt(),
        width="100%",
    )


def version_page():
    return page_shell(
        topbar(
            "Версия",
            "Текущая версия приложения и история обновлений.",
        ),
        panel_shell(
            panel_title("info", "Текущая версия"),
            rx.hstack(
                rx.vstack(
                    rx.text(APP_NAME, color=muted(), font_size="13px"),
                    rx.heading(State.current_version, color=text(), size="8"),
                    rx.text(
                        "Версия хранится в modules/version.py. Журнал изменений — в CHANGELOG.md.",
                        color=muted(),
                        font_size="12px",
                    ),
                    align="start",
                    spacing="1",
                ),
                rx.spacer(),
                fa_icon(tag="circle_check", size=32, color=ACCENT),
                width="100%",
                align="center",
            ),
        ),
        panel_shell(
            panel_title("refresh", "Обновления"),
            rx.vstack(
                rx.hstack(
                    rx.vstack(
                        rx.text(
                            "Текущая версия",
                            color=muted(),
                            font_size="12px",
                        ),
                        rx.text(State.current_version, color=text(), font_weight="700"),
                        align="start",
                        spacing="1",
                    ),
                    rx.vstack(
                        rx.text(
                            rx.cond(
                                State.remote_version != "",
                                "Версия на GitHub",
                                "Удалённая версия",
                            ),
                            color=muted(),
                            font_size="12px",
                        ),
                        rx.text(
                            rx.cond(State.remote_version != "", State.remote_version, "—"),
                            color=text(),
                            font_weight="700",
                        ),
                        align="start",
                        spacing="1",
                    ),
                    rx.spacer(),
                    fa_icon(tag="refresh", size=26, color=ACCENT),
                    width="100%",
                    align="center",
                    spacing="6",
                ),
                rx.text(State.update_status, color=muted(), font_size="13px"),
                rx.hstack(
                    primary_button(
                        rx.cond(
                            State.checking_update,
                            "Проверяю...",
                            "Проверить обновления",
                        ),
                        on_click=State.check_for_update,
                        width="220px",
                        disabled=State.checking_update | State.updating_app,
                    ),
                    secondary_button(
                        rx.cond(State.updating_app, "Обновляю...", "Обновить"),
                        on_click=State.update_application,
                        width="150px",
                        disabled=(
                            ~State.update_available
                            | State.checking_update
                            | State.updating_app
                        ),
                    ),
                    spacing="3",
                    wrap="wrap",
                ),
                rx.cond(
                    State.update_available,
                    rx.text(
                        "Новая версия готова к установке. После обновления страница перезагрузится.",
                        color=ACCENT,
                        font_size="12px",
                    ),
                    rx.box(),
                ),
                align="start",
                spacing="3",
                width="100%",
            ),
        ),
        panel_shell(
            panel_title("history", "История обновлений"),
            rx.cond(
                State.version_history.length() > 0,
                rx.vstack(
                    rx.foreach(State.version_history, version_release_card),
                    spacing="3",
                    width="100%",
                ),
                rx.text(
                    "Журнал обновлений пока пуст.",
                    color=muted(),
                    font_size="13px",
                ),
            ),
        ),
    )


def backup_item_row(item):
    return rx.vstack(
        rx.hstack(
            rx.cond(
                item["valid"],
                fa_icon(tag="circle_check", size=16, color=ACCENT),
                fa_icon(tag="triangle_alert", size=16, color="#e5484d"),
            ),
            rx.text(item["name"], color=text(), font_size="13px", font_weight="700"),
            rx.spacer(),
            rx.text(item["created_at"], color=muted(), font_size="11px"),
            width="100%",
            align="center",
            spacing="2",
        ),
        rx.cond(
            item["valid"],
            rx.hstack(
                rx.text("Файлов: ", item["files"], color=muted(), font_size="12px"),
                rx.text("Размер: ", item["size"], color=muted(), font_size="12px"),
                rx.cond(
                    item["contains_secrets"],
                    rx.text(
                        "Содержит config/mail.json — в архиве может быть пароль приложения",
                        color="#f5a623",
                        font_size="12px",
                    ),
                    rx.box(),
                ),
                spacing="3",
                wrap="wrap",
                width="100%",
            ),
            rx.text(item["error"], color="#e5484d", font_size="12px"),
        ),
        align="start",
        spacing="2",
        width="100%",
        padding="12px",
        border=f"1px solid {border()}",
        border_radius="9px",
        background=surface_alt(),
    )


def backup_page():
    return page_shell(
        topbar(
            "Резервные копии",
            "Сохраняйте статистику, историю и настройки перед важными изменениями.",
        ),
        panel_shell(
            panel_title("folder", "Папка хранения"),
            rx.text(
                "В архив попадают JSON-файлы состояния и списки маршрутов. Рабочие Excel-файлы, PDF и логи не копируются.",
                color=muted(),
                font_size="13px",
            ),
            rx.hstack(
                rx.input(
                    value=State.backup_directory,
                    on_change=State.set_backup_directory,
                    placeholder="Путь к папке резервных копий",
                    width="100%",
                    height="42px",
                ),
                primary_button(
                    "Сохранить папку",
                    on_click=State.save_backup_directory_form,
                    width="170px",
                ),
                width="100%",
                align="center",
                spacing="2",
            ),
            rx.text(
                "По умолчанию: data/backups. В веб-дашборде укажите путь на компьютере, где запущено приложение.",
                color=muted(),
                font_size="12px",
            ),
        ),
        panel_shell(
            rx.hstack(
                panel_title("save", "Снимок состояния"),
                rx.spacer(),
                secondary_button(
                    "Обновить список",
                    on_click=State.refresh_backups,
                    width="160px",
                ),
                primary_button(
                    "Создать копию",
                    on_click=State.create_full_backup,
                    width="160px",
                ),
                width="100%",
                align="center",
                wrap="wrap",
            ),
            rx.text(
                "Рекомендуется создавать копию перед обновлением приложения или массовым изменением маршрутов.",
                color=muted(),
                font_size="12px",
            ),
            rx.cond(
                State.backup_items.length() > 0,
                rx.vstack(
                    rx.foreach(State.backup_items, backup_item_row),
                    spacing="2",
                    width="100%",
                    max_height="420px",
                    overflow_y="auto",
                ),
                rx.text("Резервных копий пока нет", color=muted(), font_size="13px"),
            ),
        ),
        panel_shell(
            panel_title("history", "Восстановление"),
            rx.hstack(
                rx.select(
                    State.backup_labels,
                    value=State.selected_backup,
                    on_change=State.set_selected_backup,
                    placeholder="Выберите корректную копию",
                    width="100%",
                ),
                secondary_button(
                    "Восстановить",
                    on_click=State.ask_restore_backup,
                    width="160px",
                    disabled=State.backup_labels.length() == 0,
                ),
                width="100%",
                align="center",
                spacing="2",
            ),
            rx.cond(
                State.restore_confirmation_open,
                rx.vstack(
                    rx.text(
                        "Внимание: восстановление заменит текущую статистику, историю почты, списки маршрутов и настройки. Перед заменой будет создана страховочная копия текущего состояния.",
                        color="#f5a623",
                        font_size="13px",
                        font_weight="700",
                    ),
                    rx.hstack(
                        primary_button(
                            "Да, восстановить",
                            on_click=State.confirm_restore_backup,
                            width="180px",
                        ),
                        secondary_button(
                            "Отмена",
                            on_click=State.cancel_restore_backup,
                            width="120px",
                        ),
                        spacing="2",
                    ),
                    align="start",
                    spacing="3",
                    width="100%",
                    padding="12px",
                    border="1px solid rgba(245, 166, 35, 0.35)",
                    border_radius="9px",
                    background="rgba(245, 166, 35, 0.10)",
                ),
                rx.box(),
            ),
            rx.text(
                "config/mail.json может содержать пароль приложения. Не передавайте такой архив другим людям.",
                color=muted(),
                font_size="12px",
            ),
            rx.cond(
                State.backup_status != "",
                rx.text(State.backup_status, color=muted(), font_size="13px"),
                rx.box(),
            ),
        ),
    )


def settings_page():
    return page_shell(
        topbar("Настройки", "Поведение программы при обработке заказов."),
        rx.vstack(
            *[
                settings_toggle_row(
                    label,
                    hint,
                    State.settings_data[key],
                    lambda checked, key=key: State.toggle_setting(key, checked),
                )
                for key, (label, hint) in SETTINGS_LABELS.items()
            ],
            spacing="3",
            width="100%",
        ),
        rx.hstack(
            primary_button("Сохранить настройки", on_click=State.save_settings_form, width="220px"),
            rx.text(State.settings_status, color=muted(), font_size="13px"),
            spacing="4",
            align="center",
        ),
    )


def main_content():
    return rx.match(
        State.current_page,
        ("Заказы", orders_page()),
        ("Почта", mail_page()),
        ("Маршруты", routes_page()),
        ("Трекинг", tracking_page()),
        ("История", history_page()),
        ("Настройки", settings_page()),
        ("Версия", version_page()),
        ("Резервные копии", backup_page()),
        overview_page(),
    )


def dashboard():
    return rx.fragment(
        rx.hstack(
            sidebar(),
            main_content(),
            align="start",
            spacing="0",
            min_height="100vh",
            background=page_bg(),
        ),
        order_details_drawer(),
    )


DRIVER_VEHICLES = list(zip(ROUTE_KEYS, ROUTE_LABELS, ROUTE_COLORS))

GPS_WATCH_JS = """
(function () {
    if (!navigator.geolocation || window.__driverGpsWatching) { return; }
    window.__driverGpsWatching = true;

    function send(pos) {
        var meta = document.getElementById('driver-vehicle-meta');
        var vehicle = meta ? meta.getAttribute('data-vehicle') : '';
        if (!vehicle) { return; }

        fetch('/api/gps-ping', {
            method: 'POST',
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify({
                vehicle: vehicle,
                lat: pos.coords.latitude,
                lon: pos.coords.longitude,
                speed: pos.coords.speed
            })
        }).catch(function () {});
    }

    navigator.geolocation.watchPosition(send, function () {}, {
        enableHighAccuracy: true,
        maximumAge: 10000,
        timeout: 15000
    });
})();
"""


class DriverState(rx.State):
    vehicle_key: str = ""
    vehicle_label: str = ""
    source: str = "Область"
    stops: list[dict] = []
    active_stop: str = ""
    upload_status: str = ""

    def _stores_file(self) -> Path:
        return paths.stores_file_for(self.source)

    def select_vehicle(self, key: str, label: str):
        self.vehicle_key = key
        self.vehicle_label = label
        self.active_stop = ""
        self.upload_status = ""
        data = driver_data.load_or_init_day(key, self._stores_file())
        self.stops = data["stops"]

    def set_source(self, value: str):
        self.source = value

        if self.vehicle_key:
            data = driver_data.load_or_init_day(self.vehicle_key, self._stores_file())
            self.stops = data["stops"]

    def change_vehicle(self):
        self.vehicle_key = ""
        self.vehicle_label = ""
        self.stops = []
        self.active_stop = ""

    def open_upload(self, name: str):
        self.active_stop = name
        self.upload_status = ""

    def cancel_upload(self):
        self.active_stop = ""

    async def handle_invoice_upload(self, files: list[rx.UploadFile]):
        if not files or not self.active_stop:
            self.upload_status = "Сначала сделайте фото накладной"
            return

        file = files[0]
        data = await file.read()
        safe_stop = "".join(ch if ch.isalnum() else "_" for ch in self.active_stop)
        filename = f"{datetime.now():%Y%m%d_%H%M%S}_{safe_stop}.jpg"

        vehicle_upload_dir = rx.get_upload_dir() / "invoices" / self.vehicle_key
        vehicle_upload_dir.mkdir(parents=True, exist_ok=True)
        (vehicle_upload_dir / filename).write_bytes(data)

        photo_rel_path = f"invoices/{self.vehicle_key}/{filename}"
        updated = driver_data.mark_stop_done(
            self.vehicle_key, self._stores_file(), self.active_stop, photo_rel_path,
        )
        self.stops = updated["stops"]
        self.active_stop = ""
        self.upload_status = "Накладная сохранена"


def driver_vehicle_button(key, label, color):
    return rx.button(
        fa_icon(tag="truck", size=22, color="white"),
        rx.text(label, font_size="17px", font_weight="800", color="white"),
        on_click=DriverState.select_vehicle(key, label),
        width="100%",
        height="76px",
        border_radius="14px",
        background=color,
        _hover={"opacity": 0.9},
        cursor="pointer",
    )


def driver_select_screen():
    return rx.vstack(
        rx.heading("Выберите машину", color=text(), size="6"),
        segmented_control(["Город", "Область"], DriverState.source, DriverState.set_source),
        rx.vstack(
            *[driver_vehicle_button(key, label, color) for key, label, color in DRIVER_VEHICLES],
            spacing="3",
            width="100%",
        ),
        spacing="5",
        width="100%",
        max_width="420px",
        padding="24px",
    )


def driver_upload_box():
    return rx.vstack(
        rx.upload(
            rx.vstack(
                fa_icon(tag="camera", size=22, color=ACCENT),
                rx.text(
                    "Нажмите, чтобы сфотографировать накладную",
                    color=muted(), font_size="13px", text_align="center",
                ),
                align="center",
                spacing="2",
            ),
            id=INVOICE_UPLOAD_ID,
            accept={"image/*": [".jpg", ".jpeg", ".png"]},
            max_files=1,
            border=f"1px dashed {border()}",
            border_radius="10px",
            background=surface_alt(),
            padding="18px",
            width="100%",
            cursor="pointer",
        ),
        rx.hstack(
            rx.button(
                "Сохранить",
                on_click=DriverState.handle_invoice_upload(rx.upload_files(upload_id=INVOICE_UPLOAD_ID)),
                height="42px",
                width="100%",
                border_radius="9px",
                background=ACCENT,
                color="white",
                font_weight="700",
                cursor="pointer",
            ),
            rx.button(
                "Отмена",
                on_click=DriverState.cancel_upload,
                height="42px",
                width="120px",
                border_radius="9px",
                background=surface_alt(),
                color=text(),
                cursor="pointer",
            ),
            width="100%",
            spacing="2",
        ),
        rx.cond(
            DriverState.upload_status != "",
            rx.text(DriverState.upload_status, color=muted(), font_size="12px"),
            rx.box(),
        ),
        spacing="3",
        width="100%",
        padding="12px",
        border=f"1px solid {border()}",
        border_radius="10px",
        background=surface(),
    )


def driver_stop_card(stop):
    return rx.vstack(
        rx.hstack(
            rx.cond(
                stop["status"] == "done",
                fa_icon(tag="circle_check", size=20, color=ACCENT),
                fa_icon(tag="circle", size=20, color=muted()),
            ),
            rx.text(stop["name"], color=text(), font_size="16px", font_weight="700"),
            rx.spacer(),
            rx.cond(
                stop["status"] == "done",
                rx.text(stop["done_at"], color=muted(), font_size="12px"),
                rx.box(),
            ),
            width="100%",
            align="center",
            spacing="3",
        ),
        rx.cond(
            stop["status"] == "done",
            rx.image(
                src=f"/_upload/{stop['photo']}",
                width="100%", max_height="160px",
                object_fit="cover", border_radius="8px",
            ),
            rx.cond(
                DriverState.active_stop == stop["name"],
                driver_upload_box(),
                rx.button(
                    "Закрыть магазин",
                    on_click=DriverState.open_upload(stop["name"]),
                    width="100%",
                    height="46px",
                    border_radius="9px",
                    background=ACCENT,
                    color="white",
                    font_weight="700",
                    cursor="pointer",
                ),
            ),
        ),
        align="start",
        spacing="3",
        padding="16px",
        border=f"1px solid {border()}",
        border_radius="12px",
        background=surface(),
        width="100%",
    )


def driver_stops_screen():
    return rx.vstack(
        rx.hstack(
            rx.vstack(
                rx.heading(DriverState.vehicle_label, color=text(), size="6"),
                rx.text("Список магазинов на сегодня", color=muted(), font_size="13px"),
                align="start",
                spacing="1",
            ),
            rx.spacer(),
            secondary_button("Сменить машину", on_click=DriverState.change_vehicle, width="170px"),
            width="100%",
            align="center",
        ),
        rx.box(
            id="driver-vehicle-meta",
            custom_attrs={"data-vehicle": DriverState.vehicle_key},
            display="none",
        ),
        rx.script(GPS_WATCH_JS),
        rx.vstack(
            rx.foreach(DriverState.stops, driver_stop_card),
            spacing="3",
            width="100%",
        ),
        spacing="4",
        width="100%",
        max_width="480px",
        padding="20px",
    )


def driver_page():
    return rx.center(
        rx.cond(
            DriverState.vehicle_key == "",
            driver_select_screen(),
            driver_stops_screen(),
        ),
        width="100%",
        min_height="100vh",
        background=page_bg(),
    )


app = rx.App(
    api_transformer=custom_api,
    stylesheets=[
        "https://fonts.googleapis.com/css2?family=Roboto:wght@400;500;600;700;800&display=swap",
    ],
    style={
        "font_family": "'Roboto', sans-serif",
        "--default-font-family": "'Roboto', sans-serif",
    },
)
app.add_page(dashboard, route="/", title="Обработка заказов", on_load=State.load_history)
app.add_page(driver_page, route="/driver", title="Водитель")
