from functools import partial
from orders_dashboard.constants import (
    ACCENT,
    AI_PROVIDER_LABELS,
    AI_PROVIDER_OPTIONS,
    DASHBOARD_API_ORIGIN_JS,
    DASHBOARD_LOGIN_JS,
    DISPATCH_STAGES,
    HELP_CHAT_MODEL_BY_LABEL,
    HELP_CHAT_MODEL_HAIKU,
    HELP_CHAT_MODEL_OPTIONS,
    HELP_CHAT_MODEL_SONNET,
    INVOICE_OCR_UPLOAD_ID,
    MAIL_APP_PASSWORD_URL,
    NAV_GROUPS,
    PAGE_GROUPS,
    PAGE_LABELS,
    RETURN_STATUS_LABELS,
    SETTINGS_LABELS,
    SUPPORTED_EXCEL_LABEL,
    UPLOAD_ID,
    VOLUME_CHART_DAYS,
    VOLUME_ROUTE_LABELS,
    WEIGHT_FILTER_ALL,
    WEIGHT_FILTER_UNBOUND,
    WEIGHT_NO_BINDING,
    WEIGHT_ROUTES,
    WEIGHT_ROUTE_FILTER_OPTIONS,
    WEIGHT_ROUTE_OPTIONS,
    WEIGHT_STAGE_FILTER_OPTIONS,
    WEIGHT_STAGE_OPTIONS,
)
from orders_dashboard.components import (
    RouteDropTarget,
    format_decimal,
    _delivery_difference_color,
    _dispatch_assignment,
    _dispatch_stage_badge,
    _dispatch_store,
    _dispatch_trip_card,
    _pill,
    _return_view,
    _today_action,
    backup_item_row,
    border,
    button_base,
    delivery_item_card,
    delivery_line_row,
    delivery_summary_row,
    design_button,
    design_heading,
    design_icon,
    design_mail_panel,
    design_page,
    design_panel_heading,
    design_theme_switch,
    driver_avatar,
    event_badge,
    fleet_text_field,
    help_chat_message_bubble,
    icon_button,
    invoice_ocr_journal_row,
    loading_rail_item,
    login_page,
    mail_verdict_badge,
    metric_card,
    muted,
    muted_text,
    navigation_icon,
    page_bg,
    page_shell,
    panel_shell,
    panel_title,
    preview_metric,
    primary_button,
    rating_row,
    real_stop_row,
    real_vehicle_card,
    real_vehicle_map,
    result_metric,
    return_line_row,
    route_result,
    secondary_button,
    segment_button,
    segmented_control,
    settings_toggle_row,
    sidebar_logo,
    stat_card,
    status_pill,
    surface,
    surface_alt,
    table_container,
    text,
    theme_selector,
    topbar,
    tracking_legend_dot,
    tracking_progress_bar,
    upload_area,
    vehicle_card,
    version_release_card,
    weight_field,
    weight_select_field,
    weight_stat,
)
from orders_dashboard.icons import (
    TABLER_ICON_MAP,
    TablerIcon,
    fa_icon,
)
from orders_dashboard.pages.routes import (
    _dispatch_overview as _view__dispatch_overview,
    _dispatch_route_button as _view__dispatch_route_button,
    _routes_editor as _view__routes_editor,
    _template_dialogs as _view__template_dialogs,
    _template_route_tile as _view__template_route_tile,
    _template_store_tile as _view__template_store_tile,
    event_log_panel as _view_event_log_panel,
    rating_panel as _view_rating_panel,
    real_data_section as _view_real_data_section,
    routes_backup_bar as _view_routes_backup_bar,
    routes_page as _view_routes_page,
    simulation_section as _view_simulation_section,
    start_pause_button as _view_start_pause_button,
    tracking_controls as _view_tracking_controls,
    tracking_legend as _view_tracking_legend,
    tracking_map_panel as _view_tracking_map_panel,
    tracking_page as _view_tracking_page,
    tracking_view_toggle as _view_tracking_view_toggle,
)
from orders_dashboard.pages.workspace import (
    app_header as _view_app_header,
    app_tabs as _view_app_tabs,
    dashboard_tracking_preview as _view_dashboard_tracking_preview,
    help_chat_widget as _view_help_chat_widget,
    help_page as _view_help_page,
    overview_page as _view_overview_page,
    page_primary_action as _view_page_primary_action,
    page_tab as _view_page_tab,
    rail_item as _view_rail_item,
    sidebar as _view_sidebar,
    volume_chart_panel as _view_volume_chart_panel,
)
from orders_dashboard.pages.settings import (
    backup_page as _view_backup_page,
    fleet_driver_card as _view_fleet_driver_card,
    fleet_drivers_tab as _view_fleet_drivers_tab,
    fleet_page as _view_fleet_page,
    fleet_vehicle_card as _view_fleet_vehicle_card,
    fleet_vehicles_tab as _view_fleet_vehicles_tab,
    settings_page as _view_settings_page,
    version_page as _view_version_page,
)
from orders_dashboard.pages.reports import (
    delivery_page as _view_delivery_page,
    invoice_ocr_line as _view_invoice_ocr_line,
    invoice_ocr_page as _view_invoice_ocr_page,
    order_details_drawer as _view_order_details_drawer,
    order_invoice_row as _view_order_invoice_row,
    order_source_file_row as _view_order_source_file_row,
    return_item_card as _view_return_item_card,
    returns_page as _view_returns_page,
    route_assignment_dialog as _view_route_assignment_dialog,
    route_assignment_row as _view_route_assignment_row,
    weight_draft_row as _view_weight_draft_row,
    weight_name_autocomplete_option as _view_weight_name_autocomplete_option,
    weight_name_suggestion_chip as _view_weight_name_suggestion_chip,
    weight_page as _view_weight_page,
    weight_row as _view_weight_row,
)
from orders_dashboard.pages.orders import (
    history_page as _view_history_page,
    history_panel as _view_history_panel,
    history_row as _view_history_row,
    order_panel as _view_order_panel,
    order_preview_panel as _view_order_preview_panel,
    orders_page as _view_orders_page,
    processed_file_row as _view_processed_file_row,
    processing_summary as _view_processing_summary,
    route_driver_row as _view_route_driver_row,
    route_drivers_panel as _view_route_drivers_panel,
)
from orders_dashboard.pages.mail import (
    mail_item_row as _view_mail_item_row,
    mail_page as _view_mail_page,
    mail_setup_hint as _view_mail_setup_hint,
)

from pathlib import Path
from typing import TypedDict
from datetime import datetime, timedelta
from decimal import Decimal, InvalidOperation
from http.cookies import CookieError, SimpleCookie
from urllib.parse import quote
import asyncio
import json
import os
import traceback
import uuid

import reflex as rx
from reflex.components.radix.themes.layout.box import Box
from reflex.config import get_config
from reflex.state import StateUpdate
from reflex_base.event import Event
from starlette.applications import Starlette
from starlette.requests import Request
from starlette.responses import FileResponse, JSONResponse
from starlette.routing import Route

from modules import (
    dashboard_sessions,
    driver_data,
    driver_mileage,
    driver_orders,
    driver_sessions,
    goods_returns,
    order_records,
    vehicle_trips,
    loader_sessions,
    gdemoi,
    paths,
)
from modules.driver_mileage import DriverMileageConflict, DriverMileageError
from modules.driver_orders import DriverOrderConflict, DriverOrderError, DriverOrderNotFound
from modules.auth import AuthConfigurationError, verify_credentials
from modules.backup import (
    BackupError,
    create_backup,
    list_backups,
    load_backup_directory,
    restore_backup,
    save_backup_directory,
)
from modules.config import (
    DEFAULT_ROUTE_COUNT,
    MAX_ROUTES,
    build_groups,
    load_route_count,
    load_settings,
    load_stores,
    save_route_count,
    save_settings,
    save_stores,
)
from modules.excel_io import EXCEL_MIME_TYPES, is_excel_file
from modules.history import (
    load_processed_files,
    load_volume_history,
    record_processing,
    was_processed,
)
from modules.order_positions import order_position_names
from modules.order_records import (
    OrderRecordConflict,
    OrderRecordError,
    OrderRecordNotFound,
    create_processed_order_record,
    latest_record_ids_by_source_filename,
    list_order_record_summaries,
    list_route_trip_summaries,
    load_order_record,
    logistics_summary,
    loading_batch_destinations,
    loading_batches,
    route_loading_ready,
    save_store_shipment,
)
from modules.processed_files import (
    ProcessedFileError,
    consume_download_ticket,
    create_download_ticket,
    list_processed_files,
    resolve_processed_file,
)
from modules.weight_log import (
    STAGE_LOADING,
    STAGE_STORE_SHIPMENT,
    STAGE_UNLOADING,
    STAGES,
    add_weight_row,
    delete_weight_row,
    known_names_for_order,
    last_avg_weight_for,
    load_weight_rows,
    update_weight_row,
)
from modules.mail_watcher import (
    INVOICE_CATEGORY_UNCATEGORIZED,
    KIND_INVOICES,
    KIND_MESSAGE,
    KIND_ORDERS,
    MailDownloadError,
    MailErrorEntry,
    append_mail_error,
    check_mail,
    check_mail_connection,
    check_mail_with_retry,
    clear_mail_error_log,
    is_configured,
    invoice_category,
    link_invoice,
    load_mail_config,
    load_mail_error_log,
    load_mail_items,
    resolve_linked_invoice_for_download,
    resolve_order_for_download,
    save_mail_credentials as save_mail_credentials_config,
    sources as mail_sources_config,
    split_invoice_candidates,
    unlink_invoice,
)
from modules.pipeline import detect_mode, process_order as run_pipeline
from modules.fleet import (
    FleetError,
    active_drivers,
    active_vehicles,
    add_driver,
    add_vehicle,
    delete_driver,
    delete_vehicle,
    driver_by_id,
    driver_by_login,
    employee_role,
    loader_by_id,
    loader_by_login,
    load_fleet,
    record_order_route_assignments,
    set_driver_pin,
    update_driver,
    update_vehicle,
    verify_driver_pin,
    verify_loader_pin,
)
from modules.order_preview import PreviewError, build_order_preview
from modules.styles import conflict_fill, fills_for
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
from modules.route_drivers import (
    ROUTE_AREAS,
    load_route_drivers,
    route_index_from_name,
    save_route_drivers,
)
from modules.ai_settings import (
    PROVIDER_CLAUDE_CLI,
    PROVIDER_CLAUDE_KEY,
    PROVIDER_OPENAI_KEY,
    is_yandex_vision_configured,
    load_ai_settings,
    save_ai_settings,
)
from modules.invoice_journal import (
    InvoiceJournalError,
    append_invoice_entry,
    discard_staged_invoice,
    load_invoice_entries,
    stage_invoice_photos,
)
from modules.invoice_ocr import (
    InvoiceOcrError,
    MAX_PHOTOS,
    OCR_TIMEOUT_SECONDS,
    parse_invoice_lines,
    parse_invoice_table,
    recognize_invoice_page,
    validate_and_prepare_photo,
)
from modules.help_chat import HelpChatError, send_chat_message
from orders_dashboard import theme as ui
from orders_dashboard.loading_page import LoadingAuthMiddleware, LoadingState, loading_page
from orders_dashboard.vehicle_trips_page import TripAuthMiddleware, TripState, vehicle_trips_page


from orders_dashboard.api import custom_api
from orders_dashboard.api.common import (
    _admin_session_for_router,
    _admin_token,
    _assignment_for_session,
    _dashboard_download_authorized,
    _excel_media_type,
    _json_payload,
    _loader_available_vehicles,
    _loader_session,
    _mileage_required_response,
    _mileage_status,
    _public_driver_assignment,
    _router_query_param,
    _session,
    _set_driver_cookie,
    _set_loader_cookie,
)
from orders_dashboard.api.admin import (
    admin_login,
    admin_logout,
    download_linked_invoice_file,
    download_order_source_file,
    download_processed_file,
)
from orders_dashboard.api.driver import (
    _driver_available_vehicles,
    _owned_trip,
    _return_assignment,
    _trip_actor,
    driver_complete_store,
    driver_login,
    driver_logout,
    driver_me,
    driver_mileage_submit,
    driver_order,
    driver_return_detail,
    driver_returns,
    driver_select_vehicle,
    driver_sync,
    driver_trip_complete,
    driver_trip_detail,
    driver_trip_operate,
    driver_trip_return,
    gps_ping,
)
from orders_dashboard.api.loader import (
    loader_login,
    loader_logout,
    loader_me,
    loader_orders,
    loader_select_vehicle,
    loader_vehicles,
)


ACCENT_HOVER = ui.PURPLE_DARK
SIDEBAR_BG = ui.PANEL
SIDEBAR_BORDER = ui.LINE
SIDEBAR_TEXT = ui.INK
SIDEBAR_MUTED = ui.INK_2
SIDEBAR_HOVER = ui.STATUS_GRAY_BG
SIDEBAR_SURFACE_ALT = ui.PAGE
ROUTE_BACKUPS_FILE = paths.ROUTE_BACKUPS_FILE
MAX_ROUTE_BACKUPS = 20
MAIL_PAGE_SIZE = 50
VOLUME_ROUTE_KEYS = [f"route_{i}" for i in range(1, MAX_ROUTES + 1)]
WEIGHT_STORE_PLACEHOLDER = "— выберите магазин —"
# Чат-помощник сейчас работает только через Claude — ChatGPT в списке
# выбора не показываем, хотя modules/ai_settings.py всё ещё умеет его
# хранить (задел на будущее).
AI_PROVIDER_BY_LABEL = {label: value for value, label in AI_PROVIDER_LABELS.items()}
VERSION_HISTORY = load_changelog()


GROUP_TABS = {
    "Сводка": [{"label": "Сводка дня", "page": "Dashboard", "icon": "layout_dashboard"}],
    "Заказы": [
        {"label": "Заказы", "page": "Заказы", "icon": "package"},
        {"label": "Почта", "page": "Почта", "icon": "mail"},
        {"label": "История", "page": "История", "icon": "history"},
    ],
    "Рейсы": [{"label": "Рейсы", "page": "Маршруты", "icon": "list"}],
    "Справочники": [], "Дополнительно": [], "Возвраты": [], "Помощь": [],
    "Накладные": [
        {"label": "OCR накладных", "page": "OCR накладных", "icon": "camera"},
    ],
    "Вес": [{"label": "Вес", "page": "Вес", "icon": "scale"}],
    "Настройки": [
        {"label": "Настройки", "page": "Настройки", "icon": "settings"},
        {"label": "Резервные копии", "page": "Резервные копии", "icon": "save"},
        {"label": "Версия", "page": "Версия", "icon": "info"},
    ],
}


class TemplateRouteView(TypedDict):
    index: int
    label: str
    area: str
    count: int
    matches: int


class TemplateStoreView(TypedDict):
    name: str
    selected: bool


class DispatchStoreView(TypedDict):
    id: str
    name: str
    completed: bool
    status: str
    shipped_net_kg: str


class DispatchAssignmentView(TypedDict):
    assignment_id: str
    driver_name: str
    vehicle_name: str
    vehicle_plate: str
    active: bool


class DispatchTripView(TypedDict):
    order_record_id: str
    order_number: str
    client_name: str
    processed_at: str
    processed_display: str
    mode: str
    route_key: str
    route_label: str
    stage: str
    loading_ready: bool
    limited_data: bool
    loaded_net_kg: str
    shipped_net_kg: str
    completed_stores: int
    store_count: int
    stores: list[DispatchStoreView]
    assignments: list[DispatchAssignmentView]
    has_active_assignment: bool
    return_label: str
    return_net_kg: str
    loading_href: str
    search_text: str


class DispatchRouteView(TypedDict):
    route_key: str
    label: str
    trip_count: int
    completed_stores: int
    store_count: int


def _dispatch_trips(processed_date: str, mode: str) -> list[DispatchTripView]:
    trips = list_route_trip_summaries(processed_date, mode)
    pairs = {(trip["order_record_id"], trip["route_key"]) for trip in trips}
    assignments = driver_orders.route_assignment_summaries(pairs) if pairs else []
    returns = {(doc["order_record_id"], doc["route_key"]): doc for doc in goods_returns.list_returns()} if pairs else {}
    result = []
    for trip in trips:
        pair = (trip["order_record_id"], trip["route_key"])
        linked = [item for item in assignments if (item["order_record_id"], item["route_key"]) == pair]
        doc = returns.get(pair)
        result.append({
            **trip, "processed_display": datetime.fromisoformat(trip["processed_at"]).strftime("%d.%m.%Y %H:%M"),
            "assignments": linked, "has_active_assignment": any(item["active"] and item["driver_id"] for item in linked),
            "return_label": {"submitted": "Возврат на проверке", "accepted": "Возврат принят", "rejected": "Возврат отклонён"}.get(doc["status"], "") if doc else "",
            "return_net_kg": doc["total_net_kg"] if doc else "",
            "loading_href": f"/loading?order={quote(trip['order_record_id'], safe='')}&route={quote(trip['route_key'], safe='')}",
            "search_text": " ".join([
                trip["order_number"], trip["client_name"], trip["route_label"],
                *(store["name"] for store in trip["stores"]),
                *(" ".join((item["driver_name"], item["vehicle_name"], item["vehicle_plate"])) for item in linked),
            ]).casefold(),
        })
    return result


def _dispatch_routes(trips: list[dict], count: int, show_empty: bool) -> list[DispatchRouteView]:
    routes = {f"route_{index + 1}": f"Маршрут №{index + 1}" for index in range(count)} if show_empty else {}
    routes.update({trip["route_key"]: trip["route_label"] for trip in trips})
    result = []
    for key, label in sorted(routes.items(), key=lambda pair: (route_index_from_name(pair[1]) if route_index_from_name(pair[1]) is not None else MAX_ROUTES, pair[0])):
        selected = [trip for trip in trips if trip["route_key"] == key]
        result.append({
            "route_key": key, "label": label, "trip_count": len(selected),
            "completed_stores": sum(trip["completed_stores"] for trip in selected),
            "store_count": sum(trip["store_count"] for trip in selected),
        })
    return result


class DeliveryLineView(TypedDict):
    name: str
    unit: str
    planned: int | float
    delivered: int | float
    difference: int | float


class DeliverySummaryView(DeliveryLineView):
    pass


class DeliveryItemView(TypedDict):
    assignment_id: str
    publication_id: str
    order_id: str
    route_label: str
    driver_name: str
    vehicle_name: str
    vehicle_plate: str
    store_name: str
    completed_at: str
    lines: list[DeliveryLineView]


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

        bucket = daily.setdefault(date, [0.0] * len(VOLUME_ROUTE_KEYS))
        for index, key in enumerate(VOLUME_ROUTE_KEYS):
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


def format_history_timestamp(processed_at: str, now: datetime | None = None) -> tuple[str, str]:
    raw_timestamp = str(processed_at or "").strip()
    try:
        timestamp = datetime.fromisoformat(raw_timestamp)
    except ValueError:
        return raw_timestamp, ""

    relation = ""
    current_date = (now or datetime.now()).date()
    if timestamp.date() == current_date:
        relation = "Сегодня"
    elif timestamp.date() == current_date - timedelta(days=1):
        relation = "Вчера"

    display = timestamp.strftime("%d.%m.%y")
    if "T" in raw_timestamp or " " in raw_timestamp:
        display += timestamp.strftime(" %H:%M")
    return display, relation


def _invoice_decimal(value: str) -> Decimal | None:
    try:
        return Decimal(value.strip().replace(",", "."))
    except (InvalidOperation, AttributeError):
        return None


def format_bytes(value):
    size = float(value or 0)
    for unit in ("Б", "КБ", "МБ", "ГБ"):
        if size < 1024 or unit == "ГБ":
            return f"{size:.1f} {unit}" if unit != "Б" else f"{int(size)} {unit}"
        size /= 1024

    return "0 Б"


def format_weight_row(entry: dict, driver_by_route: dict | None = None) -> dict:
    """Запись modules.weight_log, подготовленная для таблицы: числа — строкой,
    а отсутствующий точный вес — пустой строкой (не None — списку записей в
    State нужен один и тот же тип значения в каждой строке).

    driver_by_route — {"Маршрут №1": "Имя водителя", ...}, чтобы подписать,
    кто отвозил заказ, прямо в строке веса."""

    exact_weight = entry["exact_weight"]
    net_weight = entry.get("net_weight")
    driver_by_route = driver_by_route or {}

    return {
        "id": entry["id"],
        "date": entry["date"],
        "name": entry["name"],
        "box_count": entry["box_count"],
        "avg_weight": f"{float(entry['avg_weight']):g}",
        "exact_weight": f"{float(exact_weight):g}" if exact_weight is not None else "",
        "net_weight": f"{float(net_weight):g}" if net_weight is not None else "",
        "total": f"{float(entry['total']):g}",
        "order_file": entry["order_file"],
        "route": entry["route"],
        "driver": driver_by_route.get(entry["route"], ""),
        "stage": entry.get("stage", ""),
        "store": entry.get("store", ""),
    }


def _empty_weight_draft_row() -> dict:
    """Пустая строка черновика массового ввода веса.

    saved_id пуст для ещё не сохранённой строки; если строку загрузили для
    правки уже сохранённой записи, там будет её id из weight_log.
    """

    return {
        "id": uuid.uuid4().hex,
        "saved_id": "",
        "name": "",
        "box_count": "",
        "avg_weight": "",
        "exact_weight": "",
        "net_weight": "",
        "store": WEIGHT_STORE_PLACEHOLDER,
    }


def format_invoice_journal_entry(entry: dict) -> dict:
    lines = entry.get("lines", [])
    first_line = lines[0] if lines else {}
    return {
        "id": entry["id"],
        "saved_at": entry.get("saved_at", "").replace("T", " "),
        "order_file": entry.get("order_file", ""),
        "route": entry.get("route", ""),
        "store_number": entry.get("store_number", first_line.get("store_number", "")),
        "line_count": len(lines),
        "total": entry.get("total", "0"),
    }


class State(rx.State):
    selected_file: str = "Файл не выбран"
    uploaded_file_path: str = ""
    order_client_name: str = ""
    order_mail_metadata: dict | None = None
    order_record_warning: str = ""
    mode: str = "Область"
    mode_auto_note: str = ""
    mode_detection_warning: str = ""
    duplicate_note: str = ""
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
    route_totals: list[str] = ["0"] * MAX_ROUTES
    conflict_count: int = 0
    unknown_count: int = 0
    error_text: str = ""
    history_1_file: str = "Нет обработок"
    history_1_time: str = ""
    history_1_date_relation: str = ""
    history_2_file: str = "Нет обработок"
    history_2_time: str = ""
    history_2_date_relation: str = ""
    history_3_file: str = "Нет обработок"
    history_3_time: str = ""
    history_3_date_relation: str = ""

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
    search_query: str = ""
    nav_groups: list[dict] = NAV_GROUPS
    mobile_menu_open: bool = False
    sidebar_collapsed: bool = False
    today_mode: str = "Область"
    today_waiting: int = 0
    today_drafts: int = 0
    today_ready: int = 0
    today_shipping: int = 0
    today_completed: int = 0
    today_returns: int = 0
    pending_trip_unloads: int = 0
    today_error: str = ""

    def toggle_sidebar(self):
        self.sidebar_collapsed = not self.sidebar_collapsed

    def toggle_mobile_menu(self):
        self.mobile_menu_open = not self.mobile_menu_open

    def close_mobile_menu(self):
        self.mobile_menu_open = False

    def navigate(self, target: str):
        if target == "Шаблоны маршрутов":
            self.mobile_menu_open = False
            self.current_page = "Маршруты"
            self.open_routes_editor()
            return
        if target == "Маршруты" and self.routes_editor_open:
            self.mobile_menu_open = False
            return self.close_routes_editor()
        return self.set_page(target)

    def load_today_overview(self):
        self.today_error = ""
        try:
            trips = list_route_trip_summaries(datetime.now().astimezone().date().isoformat(), self.today_mode)
            self.today_waiting = sum(t["stage"] == "Ожидает загрузки" for t in trips)
            self.today_drafts = sum(t["stage"] in {"Загрузка начата", "Ящики учтены, ожидается взвешивание"} for t in trips)
            self.today_ready = sum(t["stage"] in {"Готов к отгрузке", "Загружен частично"} for t in trips)
            self.today_shipping = sum(t["stage"] == "Отгрузка идёт" for t in trips)
            self.today_completed = sum(t["stage"] == "Отгрузка завершена" for t in trips)
            self.today_returns = sum(doc.get("status") == "submitted" for doc in goods_returns.list_returns())
            self.pending_trip_unloads = sum(trip["status"] == "released_pending" for trip in vehicle_trips.list_trips())
        except (OrderRecordError, goods_returns.GoodsReturnError, OSError, ValueError) as error:
            self.today_error = f"Не удалось обновить обзор: {error}"

    def set_today_mode(self, value: str):
        if value in {"Город", "Область"}:
            self.today_mode = value
            self.load_today_overview()

    def open_today_stage(self, stage: str):
        self.dispatch_date = datetime.now().astimezone().date().isoformat()
        self.dispatch_mode = self.today_mode
        self.dispatch_stage = stage if stage in DISPATCH_STAGES else "Все"
        return self.set_page("Маршруты")

    is_authenticated: bool = False

    def logout(self):
        self.mail_auto = False
        self.tracking_running = False
        self.real_watching = False
        self.reset()
        return rx.call_script(
            "fetch(" + DASHBOARD_API_ORIGIN_JS + " + '/api/dashboard/logout', {method: 'POST', "
            "headers: {'X-Dashboard-Request': '1'}, credentials: 'include'})"
            ".finally(() => window.location.replace('/login'));"
        )

    def load_dashboard(self):
        self.is_authenticated = _admin_session_for_router(self.router)
        if not self.is_authenticated:
            return rx.redirect("/login", replace=True)
        self.load_history()
        self.load_today_overview()
        if _router_query_param(self.router, "page") == "history":
            self.current_page = "История"

    def redirect_authenticated_user(self):
        self.is_authenticated = _admin_session_for_router(self.router)
        if self.is_authenticated:
            return rx.redirect("/", replace=True)

    routes_source: str = "Область"
    routes_editor_open: bool = False
    route_editor_baseline: list[list[str]] = []
    route_editor_pending_action: str = ""
    route_editor_pending_value: str = ""
    route_editor_error: str = ""
    dispatch_date: str = ""
    dispatch_mode: str = "Область"
    dispatch_stage: str = "Все"
    dispatch_selected_route: str = ""
    dispatch_mobile_detail: bool = False
    dispatch_trips: list[DispatchTripView] = []
    dispatch_route_count: int = DEFAULT_ROUTE_COUNT
    dispatch_message: str = ""
    # Списки по маршрутам (индексы 0..MAX_ROUTES-1 соответствуют ROUTE_KEYS);
    # сколько из них реально показываются — active_route_count.
    route_stores: list[list[str]] = [[] for _ in range(MAX_ROUTES)]
    active_route_count: int = DEFAULT_ROUTE_COUNT
    selected_route_index: int = 0
    new_store_input: str = ""
    routes_status: str = ""
    route_backup_labels: list[str] = []
    selected_route_backup: str = ""
    template_selected_stores: list[str] = []
    template_move_stores: list[str] = []
    template_move_source: int = -1
    template_move_target: str = ""
    template_move_error: str = ""
    template_discard_open: bool = False

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
    mail_result_count: int = 0
    mail_page: int = 1
    mail_page_count: int = 1
    mail_sources: list[str] = ["Все"]
    mail_source: str = "Все"
    mail_categories: list[str] = ["Все"]
    mail_category: str = "Все"
    mail_kind_filter: str = "Все сообщения"
    mail_auto: bool = False
    mail_interval: int = 10

    history_items: list[dict] = []
    processed_file_items: list[dict] = []
    processed_file_status: str = ""
    order_details_open: bool = False
    selected_order: str = ""
    selected_order_processed_path: str = ""
    selected_order_processed_name: str = ""
    selected_order_time: str = ""
    selected_order_time_label: str = "Обработан"
    selected_order_date_relation: str = ""
    order_detail_tab: str = "Накладные"
    order_invoices: list[dict] = []
    available_invoices: list[dict] = []
    other_invoices: list[dict] = []
    available_invoices_title: str = "Непривязанные накладные"
    available_invoices_empty: str = "Новых непривязанных накладных нет"
    invoice_date_hint: str = ""
    invoice_search: str = ""
    order_detail_status: str = ""

    tracking_view: str = "Реальные данные"
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

    route_driver_names: list[str] = ["----", "Азер", "Фарид", "Раван", "----", "----", "----", "----"]
    route_drivers_status: str = ""

    fleet_tab: str = "Водители"
    fleet_drivers: list[dict] = []
    fleet_vehicles: list[dict] = []
    fleet_driver_options: list[str] = [""]
    fleet_vehicle_options: list[str] = [""]
    fleet_status: str = ""
    fleet_driver_id: str = ""
    fleet_driver_login: str = ""
    fleet_driver_name: str = ""
    fleet_driver_phone: str = ""
    fleet_driver_rating: str = "5"
    fleet_driver_hired_on: str = ""
    fleet_driver_notes: str = ""
    fleet_driver_default_vehicle: str = ""
    fleet_driver_pin: str = ""
    fleet_driver_role: str = "driver"
    fleet_driver_active: bool = True
    delivery_completed_stores: int = 0
    delivery_line_count: int = 0
    delivery_summary: list[DeliverySummaryView] = []
    delivery_items: list[DeliveryItemView] = []
    returns_items: list[dict] = []
    returns_status_filter: str = "Все"
    returns_route_filter: str = "Все"
    returns_driver_filter: str = "Все"
    returns_date_from: str = ""
    returns_date_to: str = ""
    returns_message: str = ""
    returns_decision_id: str = ""
    returns_decision_revision: int = 0
    returns_decision_kind: str = ""
    returns_decision_comment: str = ""
    fleet_vehicle_id: str = ""
    fleet_vehicle_name: str = ""
    fleet_vehicle_plate: str = ""
    fleet_vehicle_odometer: str = "0"
    fleet_vehicle_description: str = ""
    fleet_vehicle_notes: str = ""
    fleet_vehicle_active: bool = True
    fleet_vehicle_tracker_id: str = ""
    route_assignment_open: bool = False
    route_assignments: list[dict] = []
    fleet_delete_pending_id: str = ""
    fleet_delete_pending_kind: str = ""

    gdemoi_api_key_input: str = ""
    gdemoi_configured: bool = False
    gdemoi_settings_status: str = ""
    gdemoi_poll_status: str = ""

    weight_rows: list[dict] = []
    weight_order: str = WEIGHT_NO_BINDING
    weight_route: str = WEIGHT_NO_BINDING
    weight_order_options: list[str] = [WEIGHT_NO_BINDING]
    weight_order_filter_options: list[str] = [WEIGHT_FILTER_ALL, WEIGHT_FILTER_UNBOUND]
    weight_filter_order: str = WEIGHT_FILTER_ALL
    weight_filter_route: str = WEIGHT_FILTER_ALL
    weight_filter_stage: str = WEIGHT_FILTER_ALL
    weight_delete_confirm_id: str = ""
    weight_status: str = ""
    weight_stage: str = STAGE_LOADING
    weight_draft_rows: list[dict] = []
    weight_name_suggestions: list[str] = []
    weight_suggestions_expanded: bool = False
    weight_autocomplete_row: str = ""
    weight_autocomplete_matches: list[str] = []

    invoice_ocr_order: str = ""
    invoice_ocr_order_options: list[str] = []
    invoice_ocr_route: str = ""
    invoice_ocr_store_number: str = ""
    invoice_ocr_busy: bool = False
    invoice_ocr_status: str = ""
    invoice_ocr_draft_id: str = ""
    invoice_ocr_photo_refs: list[str] = []
    invoice_ocr_photo_names: list[str] = []
    invoice_ocr_raw_text: str = ""
    invoice_ocr_rows: list[dict] = []
    invoice_ocr_entries: list[dict] = []

    yandex_vision_api_key_input: str = ""
    yandex_vision_folder_id_input: str = ""
    yandex_vision_configured: bool = False
    yandex_vision_settings_status: str = ""

    ai_provider_label: str = AI_PROVIDER_LABELS[PROVIDER_CLAUDE_KEY]
    ai_anthropic_key_input: str = ""
    ai_configured: bool = False
    ai_settings_status: str = ""

    help_chat_open: bool = False
    help_chat_model_label: str = "Sonnet"
    help_chat_messages: list[dict] = []
    help_chat_input: str = ""
    help_chat_busy: bool = False
    help_chat_status: str = ""

    @rx.var
    def current_group(self) -> str:
        if self.current_page == "Маршруты" and self.routes_editor_open:
            return "Справочники"
        return PAGE_GROUPS.get(self.current_page, "Сводка")

    @rx.var
    def current_page_label(self) -> str:
        if self.current_page == "Маршруты" and self.routes_editor_open:
            return "Шаблоны маршрутов"
        return PAGE_LABELS.get(self.current_page, self.current_page)

    @rx.var
    def current_tabs(self) -> list[dict]:
        return GROUP_TABS.get(self.current_group, [])

    def set_search_query(self, value: str):
        self.search_query = value
        if self.current_page == "Маршруты" and not self.routes_editor_open:
            self._select_visible_dispatch_route()

    @rx.var
    def weight_visible_rows(self) -> list[dict]:
        rows = self.weight_rows

        if self.weight_filter_order == WEIGHT_FILTER_UNBOUND:
            rows = [row for row in rows if not row["order_file"]]
        elif self.weight_filter_order != WEIGHT_FILTER_ALL:
            rows = [row for row in rows if row["order_file"] == self.weight_filter_order]

        if self.weight_filter_route == WEIGHT_FILTER_UNBOUND:
            rows = [row for row in rows if not row["route"]]
        elif self.weight_filter_route != WEIGHT_FILTER_ALL:
            rows = [row for row in rows if row["route"] == self.weight_filter_route]

        if self.weight_filter_stage != WEIGHT_FILTER_ALL:
            rows = [row for row in rows if row["stage"] == self.weight_filter_stage]

        return rows

    @rx.var
    def weight_draft_store_options(self) -> list[str]:
        """Магазины выбранного маршрута — варианты для поля «Магазин» на этапе отгрузки."""

        stores = (
            self.route_stores[WEIGHT_ROUTES.index(self.weight_route)]
            if self.weight_route in WEIGHT_ROUTES
            else []
        )
        return [WEIGHT_STORE_PLACEHOLDER] + stores

    @rx.var
    def weight_total(self) -> str:
        total = sum(float(row["total"]) for row in self.weight_visible_rows)
        return f"{total:g}"

    @rx.var
    def weight_reconciliation_rows(self) -> list[dict]:
        """Строки для сверки склада — с учётом фильтров по заказу и маршруту, но без фильтра по этапу.

        Нужны сразу все три этапа одновременно, иначе сверку не построить.
        """

        rows = self.weight_rows

        if self.weight_filter_order == WEIGHT_FILTER_UNBOUND:
            rows = [row for row in rows if not row["order_file"]]
        elif self.weight_filter_order != WEIGHT_FILTER_ALL:
            rows = [row for row in rows if row["order_file"] == self.weight_filter_order]

        if self.weight_filter_route == WEIGHT_FILTER_UNBOUND:
            rows = [row for row in rows if not row["route"]]
        elif self.weight_filter_route != WEIGHT_FILTER_ALL:
            rows = [row for row in rows if row["route"] == self.weight_filter_route]

        return rows

    @rx.var
    def weight_reconciliation(self) -> dict[str, str]:
        """Сверка склада за выбранные заказ/маршрут: загрузка = отгрузка по магазинам + выгрузка + разница.

        Разница — то, что не сошлось (пересорт, недовес, потери), в идеале должна быть 0.
        """

        totals = {stage: 0.0 for stage in STAGES}
        for row in self.weight_reconciliation_rows:
            stage = row["stage"]
            if stage in totals:
                totals[stage] += float(row["total"])

        loaded = totals[STAGE_LOADING]
        shipped = totals[STAGE_STORE_SHIPMENT]
        unloaded = totals[STAGE_UNLOADING]
        difference = loaded - shipped - unloaded

        return {
            "loaded": f"{loaded:g}",
            "shipped": f"{shipped:g}",
            "unloaded": f"{unloaded:g}",
            "difference": f"{difference:g}",
            "has_difference": "1" if round(difference, 3) != 0 else "",
        }

    @rx.var
    def invoice_ocr_total(self) -> str:
        total = Decimal()
        for row in self.invoice_ocr_rows:
            try:
                total += Decimal(str(row.get("line_total", "")).replace(",", "."))
            except (InvalidOperation, ValueError):
                continue
        return format_decimal(total)

    def set_page(self, page: str):
        self.mobile_menu_open = False
        if getattr(self, "routes_editor_open", False) and page != "Маршруты" and self.route_editor_baseline != self.route_stores:
            self.route_editor_pending_action = "page"
            self.route_editor_pending_value = page
            return
        if page != "Маршруты":
            self.routes_editor_open = False
        self.current_page = page

        if page == "Dashboard":
            self.load_history()
            self.load_today_overview()
        elif page == "История":
            self.load_history()
        elif page == "Заказы":
            self.load_route_drivers_form()
        elif page == "Маршруты":
            if not self.routes_editor_open:
                self.load_dispatch()
        elif page == "Настройки":
            self.load_settings_form()
            self.load_ai_settings_form()
            self.load_gdemoi_settings_form()
        elif page == "Резервные копии":
            self.load_backups()
        elif page == "Трекинг":
            self.refresh_real_data()
            if not self.vehicles:
                self.init_tracking()
        elif page == "Водители и транспорт":
            self.load_fleet()
        elif page == "Сданный товар":
            self.load_delivery_report()
        elif page == "Возвраты":
            self.load_returns_report()
        elif page == "Вес":
            self.load_weight()
        elif page == "OCR накладных":
            self.load_invoice_ocr()
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

    def _set_mail_categories(self, source_configs=None):
        source_configs = source_configs or mail_sources_config(load_mail_config())
        categories = next(
            (
                source.get("categories") or []
                for source in source_configs
                if source.get("name") == self.mail_source
            ),
            [],
        )
        self.mail_categories = ["Все"] + [
            category["name"] if isinstance(category, dict) else str(category)
            for category in categories
        ]
        if categories:
            self.mail_categories.append(INVOICE_CATEGORY_UNCATEGORIZED)
        if self.mail_category not in self.mail_categories:
            self.mail_category = "Все"

    def refresh_mail_config(self):
        config = load_mail_config()
        self.mail_configured = is_configured(config)
        self.mail_email = str(config.get("email", ""))
        self.mail_app_password = ""
        self.mail_interval = max(int(config.get("check_interval_minutes", 10)), 1)
        source_configs = mail_sources_config(config)
        self.mail_sources = ["Все"] + list(dict.fromkeys(
            [item["name"] for item in source_configs] + ["Другие"]
        ))

        if self.mail_source not in self.mail_sources:
            self.mail_source = "Все"
        self._set_mail_categories(source_configs)

        self._reload_mail_items(source_configs)
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
    def _mail_item_for_view(item: dict, categories=None) -> dict:
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
            "has_attachment": bool(item.get("file")),
            "reason": verdict.get("reason", ""),
            "mode": verdict.get("mode", ""),
            "matches": verdict.get("matches", 0),
            "order_file": item.get("order_file", ""),
            "date_relation": item.get("date_relation", ""),
            "category": invoice_category(
                item.get("file", ""),
                categories,
                item.get("subject", ""),
                kind,
            ),
        }

    def _filter_mail_items(self, source_configs=None):
        if source_configs is None:
            source_configs = mail_sources_config(load_mail_config())
        category_rules = {
            source["name"]: source.get("categories") or []
            for source in source_configs
        }
        items = [
            (item, self._mail_item_for_view(item, category_rules.get(item.get("source_name"), [])))
            for item in load_mail_items()
        ]
        if self.mail_source != "Все":
            items = [(original, view) for original, view in items if view["source"] == self.mail_source]
        if self.mail_category != "Все":
            if self.mail_category == INVOICE_CATEGORY_UNCATEGORIZED:
                items = [(original, view) for original, view in items
                         if (view["is_invoice"] and not view["category"]) or view["kind"] == KIND_MESSAGE]
            else:
                items = [(original, view) for original, view in items
                         if view["is_invoice"] and view["category"] == self.mail_category]
        if self.mail_kind_filter == "Только заказы":
            items = [(original, view) for original, view in items if view["is_order"]]
        elif self.mail_kind_filter == "Только непривязанные накладные":
            items = [(original, view) for original, view in items if view["is_invoice"] and not view["order_file"]]

        def received_at(pair):
            try:
                return datetime.fromisoformat(str(pair[0].get("received_at", ""))).timestamp()
            except (OSError, TypeError, ValueError, OverflowError):
                return 0

        items.sort(key=received_at, reverse=True)
        self.mail_result_count = len(items)
        self.mail_page_count = max(1, (len(items) + MAIL_PAGE_SIZE - 1) // MAIL_PAGE_SIZE)
        self.mail_page = max(1, min(self.mail_page, self.mail_page_count))
        start = (self.mail_page - 1) * MAIL_PAGE_SIZE
        self.mail_items = [view for _, view in items[start:start + MAIL_PAGE_SIZE]]

    def _reload_mail_items(self, source_configs=None):
        self._filter_mail_items(source_configs)

    def set_mail_source(self, source: str):
        if source not in self.mail_sources:
            return
        self.mail_source = source
        if source == "Все":
            self.mail_kind_filter = "Все сообщения"
            self.mail_category = "Все"
        self.mail_page = 1
        self._set_mail_categories()
        self._filter_mail_items()

    def set_mail_category(self, value: str):
        if value not in self.mail_categories:
            return
        self.mail_category = value
        self.mail_page = 1
        self._filter_mail_items()

    def set_mail_kind_filter(self, value: str):
        if value not in {"Все сообщения", "Только заказы", "Только непривязанные накладные"}:
            return
        self.mail_kind_filter = value
        self.mail_page = 1
        self._filter_mail_items()

    def set_mail_page(self, page: int):
        if type(page) is not int or not 1 <= page <= self.mail_page_count:
            return
        self.mail_page = page
        self._filter_mail_items()

    def _apply_mail_result(self, result: dict):
        """Раскладывает ответ check_mail по состоянию. Только внутри `async with self`."""

        self.mail_error_log = load_mail_error_log()

        self._reload_mail_items()
        found = result["items"]
        if not result["ok"]:
            self.mail_error = result["error"]
            self.mail_status = f"Проверка не завершена · сохранено записей: {len(found)}" if found else "Проверка не удалась"
        else:
            self.mail_error = ""
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

        if not result["ok"]:
            return

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

    def _client_connected(self) -> bool:
        """Жив ли ещё веб-сокет этой вкладки.

        Фоновые циклы (эта проверка, симуляция трекинга, слежение за
        реальными данными) иначе тикают вечно после закрытия вкладки —
        флаг вроде tracking_running/real_watching/mail_auto остаётся
        True навсегда, потому что сбросить его после закрытия некому, а
        каждый тик Reflex всё равно пытается отправить дельту уже
        отключённому клиенту и пишет в лог предупреждение
        "Attempting to send delta to disconnected client". Останавливает
        цикл на первом же тике после отключения.
        """

        namespace = app.event_namespace
        if namespace is None:
            return True

        return self.router.session.client_token in namespace.token_to_sid

    @rx.event(background=True)
    async def watch_mail(self):
        """Периодическая проверка, пока дашборд открыт и переключатель включён."""

        while True:
            async with self:
                if not self.mail_auto or not self._client_connected():
                    return
                interval = self.mail_interval

            await asyncio.sleep(max(interval, 1) * 60)

            async with self:
                if not self.mail_auto or not self._client_connected():
                    return

            await self._run_mail_check(with_retry=True)

    def take_mail_order(self, path: str, filename: str, received: str):
        """Берёт найденный файл в обработку на странице «Заказы»."""

        mail_item = next(
            (
                item
                for item in load_mail_items()
                if item.get("kind") == KIND_ORDERS and item.get("path") == path
            ),
            {},
        )
        self.selected_file = filename
        self.uploaded_file_path = path
        self.order_mail_metadata = {
            key: str(mail_item.get(key, ""))
            for key in (
                "message_id",
                "sender",
                "subject",
                "received_at",
                "received_display",
                "source_name",
                "source_email",
                "source_person",
            )
        }
        self.order_record_warning = ""
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

    def download_order_source_file(self):
        try:
            path = resolve_order_for_download(self.selected_order)
        except MailDownloadError:
            self.order_detail_status = "Исходный файл заказа больше недоступен"
            return
        return rx.download(
            url=f"/api/order-files/orders/{quote(path.name, safe='')}",
            filename=path.name,
        )

    def download_order_processed_file(self):
        try:
            path = resolve_processed_file(self.selected_order_processed_path)
            ticket = create_download_ticket(self.selected_order_processed_path)
        except ProcessedFileError:
            self.order_detail_status = "Обработанный файл больше недоступен. Обновите историю файлов."
            return
        self.order_detail_status = ""
        return rx.download(url=f"/api/processed-files/download/{ticket}", filename=path.name)

    def download_linked_invoice_file(self, filename: str):
        try:
            path = resolve_linked_invoice_for_download(self.selected_order, filename)
        except MailDownloadError:
            self.order_detail_status = "Накладная больше недоступна"
            return
        return rx.download(
            url=(
                f"/api/order-files/invoices/{quote(self.selected_order, safe='')}"
                f"/{quote(path.name, safe='')}"
            ),
            filename=path.name,
        )

    def _show_order_details(
        self,
        filename: str,
        displayed_at: str,
        time_label: str,
        date_relation: str = "",
    ):
        self.selected_order = filename
        self.selected_order_processed_path = ""
        self.selected_order_processed_name = ""
        if time_label == "Обработан":
            try:
                record_id = latest_record_ids_by_source_filename().get(filename, "")
                if record_id:
                    relative_path = str(load_order_record(record_id).get("output_relative_path", ""))
                    result = resolve_processed_file(relative_path)
                    self.selected_order_processed_path = relative_path
                    self.selected_order_processed_name = result.name
            except (OrderRecordError, ProcessedFileError, OSError):
                pass
        self.selected_order_time = displayed_at
        self.selected_order_time_label = time_label
        self.selected_order_date_relation = date_relation
        self.order_detail_tab = "Накладные"
        self.order_detail_status = ""
        self.invoice_search = ""
        self.order_details_open = True
        self._refresh_order_invoices()

    def open_order_details(self, filename: str, processed_at: str, date_relation: str = ""):
        if filename == "Нет обработок":
            return

        self._show_order_details(filename, processed_at, "Обработан", date_relation)

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

    def load_dispatch(self):
        if not self.dispatch_date:
            self.dispatch_date = datetime.now().astimezone().date().isoformat()
        self.dispatch_message = ""
        try:
            self.dispatch_route_count = load_route_count()
            self.dispatch_trips = _dispatch_trips(self.dispatch_date, self.dispatch_mode)
        except (OrderRecordError, DriverOrderError, goods_returns.GoodsReturnError, OSError, ValueError) as error:
            self.dispatch_trips = []
            self.dispatch_message = f"Не удалось загрузить рейсы: {error}"
        self._select_visible_dispatch_route()

    @rx.var
    def dispatch_filtered_trips(self) -> list[DispatchTripView]:
        query = self.search_query.strip().casefold()
        return [trip for trip in self.dispatch_trips
                if (self.dispatch_stage == "Все" or trip["stage"] == self.dispatch_stage
                    or (self.dispatch_stage == "Готов к отгрузке" and trip["stage"] == "Загружен частично")
                    or (self.dispatch_stage == "Загрузка начата" and trip["stage"] == "Ящики учтены, ожидается взвешивание"))
                and (not query or query in trip["search_text"])]

    @rx.var
    def dispatch_routes(self) -> list[DispatchRouteView]:
        return _dispatch_routes(self.dispatch_filtered_trips, self.dispatch_route_count,
                                self.dispatch_stage == "Все" and not self.search_query.strip())

    @rx.var
    def dispatch_selected_trips(self) -> list[DispatchTripView]:
        return [trip for trip in self.dispatch_filtered_trips if trip["route_key"] == self.dispatch_selected_route]

    @rx.var
    def dispatch_selected_label(self) -> str:
        return next((route["label"] for route in self.dispatch_routes if route["route_key"] == self.dispatch_selected_route), "Маршрут не выбран")

    def _select_visible_dispatch_route(self):
        routes = self.dispatch_routes
        keys = {route["route_key"] for route in routes}
        if self.dispatch_selected_route not in keys:
            self.dispatch_selected_route = routes[0]["route_key"] if routes else ""
            self.dispatch_mobile_detail = False

    def set_dispatch_date(self, value: str):
        try:
            datetime.strptime(value, "%Y-%m-%d")
        except ValueError:
            return
        self.dispatch_date = value
        self.load_dispatch()

    def set_dispatch_mode(self, value: str):
        if value not in {"Город", "Область"}:
            return
        self.dispatch_mode = value
        self.load_dispatch()

    def set_dispatch_stage(self, value: str):
        if value not in DISPATCH_STAGES:
            return
        self.dispatch_stage = value
        self._select_visible_dispatch_route()

    def reset_dispatch_filters(self):
        self.dispatch_stage = "Все"
        self.search_query = ""
        self._select_visible_dispatch_route()

    def select_dispatch_route(self, route_key: str):
        if route_key not in {route["route_key"] for route in self.dispatch_routes}:
            return
        self.dispatch_selected_route = route_key
        self.dispatch_mobile_detail = True

    def back_to_dispatch_routes(self):
        self.dispatch_mobile_detail = False

    def open_routes_editor(self):
        if self.routes_editor_open:
            return
        self.routes_source = self.dispatch_mode
        self.load_routes()
        self.routes_editor_open = True
        self.route_editor_pending_action = ""
        self.route_editor_error = ""

    def close_routes_editor(self):
        if self.route_editor_baseline != self.route_stores:
            self.route_editor_pending_action = "overview"
            self.route_editor_pending_value = ""
            return
        self.routes_editor_open = False
        self.search_query = ""
        self.load_dispatch()

    def cancel_route_editor_transition(self):
        self.route_editor_pending_action = ""
        self.route_editor_pending_value = ""
        self.route_editor_error = ""

    def finish_route_editor_transition(self, save: bool):
        if not self.route_editor_pending_action:
            return
        if save:
            try:
                self.save_routes()
            except (OSError, ValueError) as error:
                self.route_editor_error = f"Не удалось сохранить маршруты: {error}"
                return
        else:
            self.route_stores = [list(names) for names in self.route_editor_baseline]
        action, value = self.route_editor_pending_action, self.route_editor_pending_value
        self.cancel_route_editor_transition()
        if action == "source":
            self.routes_source = value
            self.load_routes()
        elif action == "page":
            self.routes_editor_open = False
            return self.set_page(value)
        else:
            self.routes_editor_open = False
            self.search_query = ""
            self.load_dispatch()

    def load_routes(self):
        self.reset_template_selection()
        data = load_stores(self.stores_file)
        self.route_stores = [list(data.get(key, [])) for key in ROUTE_KEYS]
        self.route_editor_baseline = [list(names) for names in self.route_stores]
        self.active_route_count = load_route_count()
        drivers = load_route_drivers()
        self.route_driver_names = [drivers.get(key, "----") for key in ROUTE_KEYS]
        self.search_query = ""
        if self.selected_route_index >= self.active_route_count:
            self.selected_route_index = 0
        self.routes_status = ""
        self.refresh_route_backups()

    def reset_template_selection(self):
        self.template_selected_stores = []
        self.template_move_stores = []
        self.template_move_source = -1
        self.template_move_target = ""
        self.template_move_error = ""
        self.template_discard_open = False

    @rx.var
    def template_dirty(self) -> bool:
        return self.route_stores != self.route_editor_baseline

    @rx.var
    def template_routes(self) -> list[TemplateRouteView]:
        query = self.search_query.strip().lower()
        return [
            {
                "index": index,
                "label": f"Маршрут №{index + 1}",
                "area": ROUTE_AREAS[index] if index < len(ROUTE_AREAS) else "",
                "count": len(self.route_stores[index]),
                "matches": len(self.template_filtered_names(index, query)),
            }
            for index in range(self.active_route_count)
        ]

    def template_filtered_names(self, index: int, query: str) -> list[str]:
        title = f"Маршрут №{index + 1} " + (ROUTE_AREAS[index] if index < len(ROUTE_AREAS) else "")
        return [name for name in self.route_stores[index] if not query or query in title.lower() or query in name.lower()]

    @rx.var
    def template_stores(self) -> list[TemplateStoreView]:
        return [
            {"name": name, "selected": name in self.template_selected_stores}
            for name in self.template_filtered_names(self.selected_route_index, self.search_query.strip().lower())
        ]

    @rx.var
    def template_store_count(self) -> int:
        return len(self.route_stores[self.selected_route_index])

    @rx.var
    def template_move_options(self) -> list[str]:
        return [f"Маршрут №{index + 1}" for index in range(self.active_route_count) if index != self.template_move_source]

    def select_template_route(self, index: int):
        if 0 <= index < self.active_route_count and index != self.selected_route_index:
            self.reset_template_selection()
            self.selected_route_index = index
            self.new_store_input = ""

    def toggle_template_store(self, name: str):
        if name not in self.route_stores[self.selected_route_index]:
            return
        selected = list(self.template_selected_stores)
        if name in selected:
            selected.remove(name)
        else:
            selected.append(name)
        self.template_selected_stores = selected

    def select_template_matches(self):
        names = self.template_filtered_names(self.selected_route_index, self.search_query.strip().lower())
        self.template_selected_stores = list(dict.fromkeys([*self.template_selected_stores, *names]))

    def clear_template_selection(self):
        self.template_selected_stores = []

    def open_template_move(self, name: str):
        names = [name] if name else list(self.template_selected_stores)
        if not names or any(item not in self.route_stores[self.selected_route_index] for item in names):
            return
        self.template_move_source = self.selected_route_index
        self.template_move_stores = names
        self.template_move_target = ""
        self.template_move_error = ""

    def set_template_move_open(self, opened: bool):
        if not opened:
            self.close_template_move()

    def close_template_move(self):
        self.template_move_source = -1
        self.template_move_stores = []
        self.template_move_target = ""
        self.template_move_error = ""

    def set_template_move_target(self, value: str):
        self.template_move_target = value
        self.template_move_error = ""

    def move_template_stores(self, source: int, target: int, names: list[str]) -> bool:
        if not (0 <= source < self.active_route_count and 0 <= target < self.active_route_count) or source == target:
            self.template_move_error = "Выберите другой действующий маршрут."
            return False
        if not names or any(name not in self.route_stores[source] for name in names):
            self.template_move_error = "Состав исходного маршрута изменился. Выберите магазины заново."
            return False
        conflicts = [name for name in names if name in self.route_stores[target]]
        if conflicts:
            self.template_move_error = "В целевом маршруте уже есть: " + ", ".join(conflicts)
            return False
        routes = [list(items) for items in self.route_stores]
        moving = [name for name in routes[source] if name in names]
        routes[source] = [name for name in routes[source] if name not in names]
        routes[target].extend(moving)
        self.route_stores = routes
        self.template_selected_stores = [name for name in self.template_selected_stores if name not in moving]
        self.routes_status = f"Перемещено магазинов: {len(moving)} → Маршрут №{target + 1}. Сохраните изменения."
        self.template_move_error = ""
        return True

    def confirm_template_move(self):
        target = route_index_from_name(self.template_move_target)
        if target is None:
            self.template_move_error = "Выберите целевой маршрут."
            return
        if self.move_template_stores(self.template_move_source, target, self.template_move_stores):
            self.close_template_move()

    def drop_template_store(self, target: int, payload: str):
        try:
            data = json.loads(payload)
            source, name = data["source"], data["name"]
            if type(source) is not int or not isinstance(name, str):
                return
        except (ValueError, TypeError, KeyError):
            return
        if not self.move_template_stores(source, target, [name]):
            self.routes_status = self.template_move_error

    def request_template_discard(self):
        self.template_discard_open = True

    def cancel_template_discard(self):
        self.template_discard_open = False

    def discard_template_changes(self):
        self.route_stores = [list(names) for names in self.route_editor_baseline]
        self.reset_template_selection()
        self.routes_status = "Несохранённые изменения отменены."

    @rx.var
    def route_name_options(self) -> list[str]:
        return [f"Маршрут №{index + 1}" for index in range(self.active_route_count)]

    @rx.var
    def selected_route_label(self) -> str:
        return f"Маршрут №{self.selected_route_index + 1}"

    def remove_route_store(self, index: int, name: str):
        if 0 <= index < self.active_route_count:
            self.selected_route_index = index
            self.remove_store(name)

    def select_route(self, value: str):
        index = route_index_from_name(value)
        if index is not None and index < self.active_route_count:
            self.selected_route_index = index

    def add_route(self):
        if self.active_route_count >= MAX_ROUTES:
            self.routes_status = f"Достигнут предел — не больше {MAX_ROUTES} маршрутов"
            return

        self.reset_template_selection()
        self.new_store_input = ""
        self.active_route_count += 1
        save_route_count(self.active_route_count)
        self.selected_route_index = self.active_route_count - 1
        self.routes_status = (
            f"Добавлен «Маршрут №{self.active_route_count}» — впишите магазины и сохраните"
        )

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
            self.reset_template_selection()
            self.routes_status = (
                f"Загружена копия «{self.selected_route_backup}». "
                "Нажмите «Сохранить маршруты», чтобы применить её."
            )
            return

        self.routes_status = "Копия не найдена — обновите список"
        self.refresh_route_backups()

    def set_routes_source(self, value: str):
        if value not in {"Город", "Область"} or value == self.routes_source:
            return
        if getattr(self, "routes_editor_open", False) and self.route_editor_baseline != self.route_stores:
            self.route_editor_pending_action = "source"
            self.route_editor_pending_value = value
            return
        self.routes_source = value
        self.load_routes()

    def set_new_store(self, value: str):
        self.new_store_input = value

    def add_store(self):
        index = self.selected_route_index
        value = self.new_store_input.strip()

        if value and value not in self.route_stores[index]:
            routes = [list(names) for names in self.route_stores]
            routes[index].append(value)
            self.route_stores = routes

        self.new_store_input = ""

    def remove_store(self, name: str):
        routes = [list(names) for names in self.route_stores]
        index = self.selected_route_index
        routes[index] = [item for item in routes[index] if item != name]
        self.route_stores = routes
        self.template_selected_stores = [item for item in getattr(self, "template_selected_stores", []) if item != name]
        if name in getattr(self, "template_move_stores", []):
            self.close_template_move()

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
        self.route_editor_baseline = [list(names) for names in self.route_stores]

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
        self.vehicles = init_vehicles(stores_file, self.active_route_count)
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
                if not self.tracking_running or not self._client_connected():
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

        for index, key in enumerate(ROUTE_KEYS[: self.active_route_count]):
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
                if (
                    not self.real_watching
                    or self.tracking_view != "Реальные данные"
                    or not self._client_connected()
                ):
                    self.real_watching = False
                    return

            try:
                await asyncio.to_thread(gdemoi.poll_and_record)
                gdemoi_error = ""
            except gdemoi.GdemoiError as error:
                gdemoi_error = str(error)

            async with self:
                if (
                    not self.real_watching
                    or self.tracking_view != "Реальные данные"
                    or not self._client_connected()
                ):
                    self.real_watching = False
                    return

                self.gdemoi_poll_status = gdemoi_error
                self.refresh_real_data()

    def download_processed_file(self, relative_path: str):
        try:
            filename = resolve_processed_file(relative_path).name
            ticket = create_download_ticket(relative_path)
        except ProcessedFileError:
            self.processed_file_status = "Файл больше недоступен. Обновите страницу."
            return
        self.processed_file_status = ""
        return rx.download(
            url=f"/api/processed-files/download/{ticket}",
            filename=filename,
        )

    def load_history(self):
        self.processed_file_items = list_processed_files()
        self.processed_file_status = ""
        data = load_processed_files()
        all_items = sorted(data.items(), key=lambda item: item[1], reverse=True)
        try:
            loading_record_ids = latest_record_ids_by_source_filename()
            loading_statuses = {
                item["id"]: item["status"] for item in list_order_record_summaries()
            }
        except OrderRecordError:
            loading_record_ids = {}
            loading_statuses = {}
        now = datetime.now()
        history_items = []
        for filename, processed_at in all_items:
            displayed_at, date_relation = format_history_timestamp(processed_at, now)
            loading_order_id = loading_record_ids.get(filename, "")
            loading_status = loading_statuses.get(loading_order_id, "")
            history_items.append(
                {
                    "file": filename,
                    "time": displayed_at,
                    "date_relation": date_relation,
                    "loading_href": f"/loading?order={loading_order_id}&from=history" if loading_order_id else "",
                    "loading_label": "Посмотреть загрузку" if loading_status == "loaded" else "Загрузить",
                }
            )
        self.history_items = history_items
        items = history_items[:3]
        placeholders = [{"file": "Нет обработок", "time": "", "date_relation": ""}] * 3
        items = items + placeholders[len(items):]

        self.history_1_file = items[0]["file"]
        self.history_1_time = items[0]["time"]
        self.history_1_date_relation = items[0]["date_relation"]
        self.history_2_file = items[1]["file"]
        self.history_2_time = items[1]["time"]
        self.history_2_date_relation = items[1]["date_relation"]
        self.history_3_file = items[2]["file"]
        self.history_3_time = items[2]["time"]
        self.history_3_date_relation = items[2]["date_relation"]

        self.orders_total_count = len(data)
        today = now.strftime("%Y-%m-%d")
        self.orders_today_count = sum(1 for ts in data.values() if ts.startswith(today))

        self.active_route_count = load_route_count()
        self.refresh_stores_total()
        self.volume_chart_data = build_volume_chart_data()
        self.load_ai_settings_form()

    def load_route_drivers_form(self):
        drivers = load_route_drivers()
        self.route_driver_names = [drivers[key] for key in ROUTE_KEYS]
        self.route_drivers_status = ""

    def set_route_driver_name(self, index: int, value: str):
        names = list(self.route_driver_names)
        names[index] = value
        self.route_driver_names = names

    def save_route_drivers_form(self):
        save_route_drivers(dict(zip(ROUTE_KEYS, self.route_driver_names)))
        self.route_drivers_status = "Сохранено"

    def _route_driver_lookup(self) -> dict:
        return {f"Маршрут №{index + 1}": name for index, name in enumerate(self.route_driver_names)}

    def load_weight(self):
        self.weight_status = ""
        self.weight_delete_confirm_id = ""
        self.weight_suggestions_expanded = False
        self.weight_autocomplete_row = ""
        self.weight_autocomplete_matches = []
        self.load_route_drivers_form()
        self.load_routes()
        driver_lookup = self._route_driver_lookup()
        self.weight_rows = [format_weight_row(row, driver_lookup) for row in load_weight_rows()]

        files = sorted(load_processed_files().items(), key=lambda item: item[1], reverse=True)
        filenames = [filename for filename, _ in files]
        self.weight_order_options = [WEIGHT_NO_BINDING] + filenames
        self.weight_order_filter_options = [WEIGHT_FILTER_ALL, WEIGHT_FILTER_UNBOUND] + filenames

        if not self.weight_draft_rows:
            self.weight_draft_rows = [_empty_weight_draft_row()]
        self._refresh_weight_name_suggestions()

    def _refresh_weight_name_suggestions(self):
        order_file = "" if self.weight_order == WEIGHT_NO_BINDING else self.weight_order

        if order_file:
            names = list(order_position_names(order_file))
            seen = {name.casefold() for name in names}
            for name in known_names_for_order(order_file):
                if name.casefold() not in seen:
                    seen.add(name.casefold())
                    names.append(name)
            self.weight_name_suggestions = names
        else:
            self.weight_name_suggestions = []

        self.weight_autocomplete_row = ""
        self.weight_autocomplete_matches = []

    def toggle_weight_suggestions(self):
        self.weight_suggestions_expanded = not self.weight_suggestions_expanded

    def set_weight_order(self, value: str):
        self.weight_order = value
        self._refresh_weight_name_suggestions()

    def set_weight_route(self, value: str):
        self.weight_route = value

    def set_weight_stage(self, value: str):
        self.weight_stage = value

    def set_weight_filter_order(self, value: str):
        self.weight_filter_order = value

    def set_weight_filter_route(self, value: str):
        self.weight_filter_route = value

    def set_weight_filter_stage(self, value: str):
        self.weight_filter_stage = value

    def set_weight_draft_field(self, row_id: str, field: str, value: str):
        if field not in {"name", "box_count", "avg_weight", "exact_weight", "net_weight", "store"}:
            return

        rows = []
        for row in self.weight_draft_rows:
            if row["id"] == row_id:
                row = dict(row)
                row[field] = value
            rows.append(row)
        self.weight_draft_rows = rows

        if field == "name":
            self._refresh_weight_name_autocomplete(row_id, value)

    def _refresh_weight_name_autocomplete(self, row_id: str, typed: str):
        typed = typed.strip().lower()
        if not typed:
            self.weight_autocomplete_row = ""
            self.weight_autocomplete_matches = []
            return

        self.weight_autocomplete_row = row_id
        self.weight_autocomplete_matches = [
            name for name in self.weight_name_suggestions if name.lower().startswith(typed)
        ][:6]

    def handle_weight_name_key(self, row_id: str, key: str):
        if key == "Escape":
            self.weight_autocomplete_row = ""
            self.weight_autocomplete_matches = []
            return

        if key != "Tab":
            return

        if self.weight_autocomplete_row != row_id or not self.weight_autocomplete_matches:
            return

        self.accept_weight_name_suggestion(row_id, self.weight_autocomplete_matches[0])

    def accept_weight_name_suggestion(self, row_id: str, name: str):
        self.set_weight_draft_field(row_id, "name", name)
        self.weight_autocomplete_row = ""
        self.weight_autocomplete_matches = []
        self.suggest_weight_draft_avg(row_id)

    def suggest_weight_draft_avg(self, row_id: str):
        """Подставляет средний вес ящика из последней записи с таким же названием.

        Срабатывает по уходу фокуса с поля «Наименование» строки черновика и
        не трогает поле, если оно уже заполнено.
        """

        rows = []
        changed = False
        for row in self.weight_draft_rows:
            if row["id"] == row_id and not row["avg_weight"].strip():
                suggestion = last_avg_weight_for(row["name"])
                if suggestion is not None:
                    row = dict(row)
                    row["avg_weight"] = f"{suggestion:g}"
                    changed = True
            rows.append(row)

        if changed:
            self.weight_draft_rows = rows

    def add_weight_draft_row(self):
        self.weight_draft_rows = self.weight_draft_rows + [_empty_weight_draft_row()]
        self.weight_status = ""

    def add_weight_draft_row_with_name(self, name: str):
        """Клик по подсказке наименования — быстро завести строку с этим именем.

        Занимает последнюю пустую строку черновика, если она есть, иначе
        добавляет новую — так по подсказкам можно быстро набрать список
        позиций, а потом просто проставить количества."""

        suggestion = last_avg_weight_for(name)
        avg_weight = f"{suggestion:g}" if suggestion is not None else ""

        rows = list(self.weight_draft_rows)
        if rows and not rows[-1]["name"].strip() and not rows[-1]["saved_id"]:
            rows[-1] = {**rows[-1], "name": name, "avg_weight": avg_weight}
        else:
            rows.append({**_empty_weight_draft_row(), "name": name, "avg_weight": avg_weight})
        self.weight_draft_rows = rows
        self.weight_status = ""

    def remove_weight_draft_row(self, row_id: str):
        remaining = [row for row in self.weight_draft_rows if row["id"] != row_id]
        self.weight_draft_rows = remaining or [_empty_weight_draft_row()]
        self.weight_status = ""
        if self.weight_autocomplete_row == row_id:
            self.weight_autocomplete_row = ""
            self.weight_autocomplete_matches = []

    def start_edit_weight_row(self, row_id: str):
        """Подгружает уже сохранённую запись в черновик массового ввода для правки."""

        row = next((row for row in self.weight_rows if row["id"] == row_id), None)
        if row is None:
            return

        if any(draft["saved_id"] == row_id for draft in self.weight_draft_rows):
            return

        loaded = {
            "id": uuid.uuid4().hex,
            "saved_id": row_id,
            "name": row["name"],
            "box_count": str(row["box_count"]),
            "avg_weight": row["avg_weight"],
            "exact_weight": row["exact_weight"],
            "net_weight": row["net_weight"],
            "store": row["store"] or WEIGHT_STORE_PLACEHOLDER,
        }

        only_row = self.weight_draft_rows[0] if len(self.weight_draft_rows) == 1 else None
        is_blank = only_row is not None and not only_row["name"].strip() and not only_row["saved_id"]

        self.weight_order = row["order_file"] or WEIGHT_NO_BINDING
        self.weight_route = row["route"] or WEIGHT_NO_BINDING
        if row["stage"]:
            self.weight_stage = row["stage"]
        self._refresh_weight_name_suggestions()
        self.weight_delete_confirm_id = ""
        self.weight_status = ""

        self.weight_draft_rows = [loaded] if is_blank else self.weight_draft_rows + [loaded]

    def submit_weight_draft_rows(self):
        order_file = "" if self.weight_order == WEIGHT_NO_BINDING else self.weight_order
        route = "" if self.weight_route == WEIGHT_NO_BINDING else self.weight_route
        stage = self.weight_stage

        parsed = []
        for index, row in enumerate(self.weight_draft_rows, start=1):
            name = row["name"].strip()
            if not name and not row["box_count"].strip() and not row["avg_weight"].strip():
                continue

            if not name:
                self.weight_status = f"Строка {index}: укажите наименование"
                return

            try:
                box_count = int(row["box_count"])
                assert box_count > 0
            except (ValueError, AssertionError):
                self.weight_status = f"Строка {index}: количество ящиков должно быть целым числом больше нуля"
                return

            try:
                avg_weight = float(row["avg_weight"].replace(",", "."))
                assert avg_weight >= 0
            except (ValueError, AssertionError):
                self.weight_status = f"Строка {index}: средний вес ящика должен быть числом"
                return

            exact_weight = None
            if row["exact_weight"].strip():
                try:
                    exact_weight = float(row["exact_weight"].replace(",", "."))
                    assert exact_weight >= 0
                except (ValueError, AssertionError):
                    self.weight_status = f"Строка {index}: грязный вес должен быть числом"
                    return

            net_weight = None
            if row["net_weight"].strip():
                try:
                    net_weight = float(row["net_weight"].replace(",", "."))
                    assert net_weight >= 0
                except (ValueError, AssertionError):
                    self.weight_status = f"Строка {index}: чистый вес должен быть числом"
                    return

            store = row["store"].strip() if stage == STAGE_STORE_SHIPMENT else ""
            if store == WEIGHT_STORE_PLACEHOLDER:
                store = ""
            if stage == STAGE_STORE_SHIPMENT and not store:
                self.weight_status = f"Строка {index}: укажите магазин"
                return

            parsed.append((row["saved_id"], name, box_count, avg_weight, exact_weight, store, net_weight))

        if not parsed:
            self.weight_status = "Добавьте хотя бы одну позицию"
            return

        driver_lookup = self._route_driver_lookup()

        for saved_id, name, box_count, avg_weight, exact_weight, store, net_weight in parsed:
            if saved_id:
                entry = update_weight_row(
                    saved_id, name, box_count, avg_weight, exact_weight, order_file, route, stage, store,
                    net_weight=net_weight,
                )
                if entry is None:
                    continue
                formatted = format_weight_row(entry, driver_lookup)
                self.weight_rows = [
                    formatted if r["id"] == entry["id"] else r for r in self.weight_rows
                ]
            else:
                entry = add_weight_row(
                    name, box_count, avg_weight, exact_weight, order_file, route, stage, store,
                    net_weight=net_weight,
                )
                self.weight_rows = self.weight_rows + [format_weight_row(entry, driver_lookup)]

        self.weight_draft_rows = [_empty_weight_draft_row()]
        self.weight_status = f"Сохранено позиций: {len(parsed)}"
        self._refresh_weight_name_suggestions()

    def ask_delete_weight_row(self, row_id: str):
        self.weight_delete_confirm_id = row_id

    def cancel_delete_weight_row(self):
        self.weight_delete_confirm_id = ""

    def confirm_delete_weight_row(self):
        row_id = self.weight_delete_confirm_id
        delete_weight_row(row_id)
        self.weight_rows = [row for row in self.weight_rows if row["id"] != row_id]
        remaining = [row for row in self.weight_draft_rows if row["saved_id"] != row_id]
        self.weight_draft_rows = remaining or [_empty_weight_draft_row()]
        self.weight_delete_confirm_id = ""

    def load_invoice_ocr(self):
        files = sorted(load_processed_files().items(), key=lambda item: item[1], reverse=True)
        self.invoice_ocr_order_options = [filename for filename, _ in files]
        if self.invoice_ocr_order not in self.invoice_ocr_order_options:
            self.invoice_ocr_order = ""
        try:
            self.invoice_ocr_entries = [
                format_invoice_journal_entry(entry) for entry in load_invoice_entries()
            ]
        except InvoiceJournalError as error:
            self.invoice_ocr_entries = []
            self.invoice_ocr_status = str(error)

    def set_invoice_ocr_order(self, value: str):
        self.invoice_ocr_order = value
        self.invoice_ocr_status = ""

    def set_invoice_ocr_route(self, value: str):
        self.invoice_ocr_route = value
        self.invoice_ocr_status = ""

    def set_invoice_ocr_store_number(self, value: str):
        self.invoice_ocr_store_number = value
        self.invoice_ocr_rows = [
            {**row, "store_number": value} for row in self.invoice_ocr_rows
        ]
        self.invoice_ocr_status = ""

    def set_invoice_ocr_line_field(self, row_id: str, field: str, value: str):
        if field not in {"store_number", "name", "unit", "quantity", "unit_price", "line_total"}:
            return

        rows = []
        for row in self.invoice_ocr_rows:
            updated = dict(row)
            if updated["id"] == row_id:
                updated[field] = value
                if field in {"quantity", "unit_price"}:
                    quantity = _invoice_decimal(updated["quantity"])
                    unit_price = _invoice_decimal(updated["unit_price"])
                    if quantity is not None and unit_price is not None and quantity >= 0 and unit_price >= 0:
                        updated["line_total"] = format_decimal(quantity * unit_price)
            rows.append(updated)
        self.invoice_ocr_rows = rows
        self.invoice_ocr_status = ""

    def add_invoice_ocr_line(self):
        self.invoice_ocr_rows = self.invoice_ocr_rows + [
            {
                "id": uuid.uuid4().hex,
                "store_number": self.invoice_ocr_store_number,
                "name": "",
                "unit": "",
                "quantity": "",
                "unit_price": "",
                "line_total": "",
            }
        ]
        self.invoice_ocr_status = ""

    def remove_invoice_ocr_line(self, row_id: str):
        self.invoice_ocr_rows = [row for row in self.invoice_ocr_rows if row["id"] != row_id]
        self.invoice_ocr_status = ""

    def clear_invoice_ocr_draft(self):
        if self.invoice_ocr_busy:
            return
        if self.invoice_ocr_draft_id:
            discard_staged_invoice(self.invoice_ocr_draft_id)
        self._reset_invoice_ocr_draft()
        self.invoice_ocr_status = "Черновик очищен"

    def _reset_invoice_ocr_draft(self):
        self.invoice_ocr_draft_id = ""
        self.invoice_ocr_photo_refs = []
        self.invoice_ocr_photo_names = []
        self.invoice_ocr_store_number = ""
        self.invoice_ocr_raw_text = ""
        self.invoice_ocr_rows = []

    async def recognize_invoice_photos(self, files: list[rx.UploadFile]):
        if self.invoice_ocr_busy:
            return
        if self.invoice_ocr_order not in self.invoice_ocr_order_options:
            self.invoice_ocr_status = "Сначала выберите обработанный заказ"
            return
        if self.invoice_ocr_route not in WEIGHT_ROUTES:
            self.invoice_ocr_status = "Сначала выберите маршрут"
            return
        settings = load_ai_settings()
        if not is_yandex_vision_configured(settings):
            self.invoice_ocr_status = "Сначала настройте Yandex Vision OCR на странице «Настройки»"
            return
        if not files:
            self.invoice_ocr_status = "Добавьте хотя бы одну фотографию накладной"
            return
        if len(files) > MAX_PHOTOS:
            self.invoice_ocr_status = f"Можно распознать не более {MAX_PHOTOS} фотографий за раз"
            return
        previous_draft_id = self.invoice_ocr_draft_id
        self.invoice_ocr_busy = True
        self.invoice_ocr_status = "Подготавливаю фотографии..."
        self._reset_invoice_ocr_draft()
        api_key = settings["yandex_vision_api_key"]
        folder_id = settings["yandex_vision_folder_id"]

        if previous_draft_id:
            await asyncio.to_thread(discard_staged_invoice, previous_draft_id)

        draft_id = ""
        try:
            prepared_photos = []
            photo_names = []
            for file in files:
                filename = getattr(file, "filename", None) or file.name
                prepared_photos.append(validate_and_prepare_photo(filename, await file.read()))
                photo_names.append(Path(filename).name)

            draft_id, photo_refs = await asyncio.to_thread(
                stage_invoice_photos,
                [(photo.original, photo.extension) for photo in prepared_photos],
            )
            recognized_pages = []
            parsed_rows = []
            store_number = ""
            photo_count = len(prepared_photos)
            for index, photo in enumerate(prepared_photos, start=1):
                self.invoice_ocr_status = f"Распознаю фото {index} из {photo_count}..."
                try:
                    page = await asyncio.wait_for(
                        asyncio.to_thread(
                            recognize_invoice_page,
                            photo.ocr_content,
                            photo.ocr_mime_type,
                            api_key,
                            folder_id,
                        ),
                        timeout=OCR_TIMEOUT_SECONDS + 5,
                    )
                except TimeoutError as error:
                    raise InvoiceOcrError(
                        f"Распознавание фото {index} из {photo_count} заняло слишком долго. "
                        "Попробуйте загрузить его ещё раз или сделайте фото меньшего размера"
                    ) from error
                recognized_pages.append(page.text)
                parsed_page = parse_invoice_table(page)
                if not store_number:
                    store_number = str(parsed_page["store_number"])
                parsed_rows.extend(parsed_page["items"])

            raw_text = "\n\n".join(page for page in recognized_pages if page.strip()).strip()
            if not raw_text:
                raise InvoiceOcrError("Yandex Vision не распознал текст на фотографиях")
            rows = parsed_rows or parse_invoice_lines(raw_text)
            self.invoice_ocr_draft_id = draft_id
            self.invoice_ocr_photo_refs = photo_refs
            self.invoice_ocr_photo_names = photo_names
            self.invoice_ocr_store_number = store_number
            self.invoice_ocr_raw_text = raw_text
            self.invoice_ocr_rows = [
                {"id": uuid.uuid4().hex, "store_number": store_number, **row}
                for row in rows
            ]
            self.invoice_ocr_busy = False
            self.invoice_ocr_status = (
                "Проверьте таблицу перед сохранением"
                if rows
                else "Текст распознан, но товарные строки не определены. Добавьте их вручную"
            )
        except (InvoiceOcrError, InvoiceJournalError) as error:
            if draft_id:
                await asyncio.to_thread(discard_staged_invoice, draft_id)
            self.invoice_ocr_busy = False
            self._reset_invoice_ocr_draft()
            self.invoice_ocr_status = str(error)
        except Exception:
            if draft_id:
                await asyncio.to_thread(discard_staged_invoice, draft_id)
            self.invoice_ocr_busy = False
            self._reset_invoice_ocr_draft()
            self.invoice_ocr_status = "Не удалось распознать фотографии накладной"

    def save_invoice_ocr_draft(self):
        if self.invoice_ocr_busy:
            return
        if self.invoice_ocr_order not in self.invoice_ocr_order_options:
            self.invoice_ocr_status = "Выберите обработанный заказ"
            return
        if self.invoice_ocr_route not in WEIGHT_ROUTES:
            self.invoice_ocr_status = "Выберите маршрут"
            return
        if not self.invoice_ocr_store_number.strip():
            self.invoice_ocr_status = "Укажите номер магазина"
            return
        if not self.invoice_ocr_draft_id or not self.invoice_ocr_photo_refs:
            self.invoice_ocr_status = "Сначала загрузите и распознайте фотографии"
            return

        try:
            entry = append_invoice_entry(
                self.invoice_ocr_draft_id,
                self.invoice_ocr_order,
                self.invoice_ocr_route,
                self.invoice_ocr_store_number,
                self.invoice_ocr_photo_refs,
                self.invoice_ocr_rows,
            )
        except InvoiceJournalError as error:
            self.invoice_ocr_status = str(error)
            return

        self.invoice_ocr_entries = [format_invoice_journal_entry(entry)] + self.invoice_ocr_entries
        self._reset_invoice_ocr_draft()
        self.invoice_ocr_status = "Накладная сохранена в журнале"

    def load_ai_settings_form(self):
        settings = load_ai_settings()
        self.ai_provider_label = AI_PROVIDER_LABELS.get(
            settings["provider"], AI_PROVIDER_LABELS[PROVIDER_CLAUDE_KEY]
        )
        self.ai_anthropic_key_input = ""
        self.ai_configured = bool(
            settings["anthropic_api_key"] or settings["provider"] == PROVIDER_CLAUDE_CLI
        )
        self.ai_settings_status = ""
        self.yandex_vision_api_key_input = ""
        self.yandex_vision_folder_id_input = ""
        self.yandex_vision_configured = is_yandex_vision_configured(settings)
        self.yandex_vision_settings_status = ""

    def set_ai_provider_label(self, value: str):
        self.ai_provider_label = value

    def set_ai_anthropic_key_input(self, value: str):
        self.ai_anthropic_key_input = value

    def save_ai_settings_form(self):
        provider = AI_PROVIDER_BY_LABEL.get(self.ai_provider_label, PROVIDER_CLAUDE_KEY)

        settings = save_ai_settings(provider, anthropic_api_key=self.ai_anthropic_key_input)

        self.ai_anthropic_key_input = ""
        self.ai_configured = bool(settings["anthropic_api_key"] or provider == PROVIDER_CLAUDE_CLI)
        self.ai_settings_status = "Настройки сохранены" if self.ai_configured else "Настройки сохранены, но ключ не задан"

    def set_yandex_vision_api_key_input(self, value: str):
        self.yandex_vision_api_key_input = value

    def set_yandex_vision_folder_id_input(self, value: str):
        self.yandex_vision_folder_id_input = value

    def save_yandex_vision_settings_form(self):
        settings = load_ai_settings()
        settings = save_ai_settings(
            settings["provider"],
            yandex_vision_api_key=self.yandex_vision_api_key_input,
            yandex_vision_folder_id=self.yandex_vision_folder_id_input,
        )
        self.yandex_vision_api_key_input = ""
        self.yandex_vision_folder_id_input = ""
        self.yandex_vision_configured = is_yandex_vision_configured(settings)
        self.yandex_vision_settings_status = (
            "Настройки сохранены"
            if self.yandex_vision_configured
            else "Укажите ключ Yandex Vision и ID каталога"
        )

    def load_gdemoi_settings_form(self):
        self.gdemoi_api_key_input = ""
        self.gdemoi_configured = gdemoi.is_configured()
        self.gdemoi_settings_status = ""

    def set_gdemoi_api_key_input(self, value: str):
        self.gdemoi_api_key_input = value

    def save_gdemoi_settings_form(self):
        settings = gdemoi.save_settings(self.gdemoi_api_key_input)
        self.gdemoi_api_key_input = ""
        self.gdemoi_configured = gdemoi.is_configured(settings)
        self.gdemoi_settings_status = (
            "Настройки сохранены" if self.gdemoi_configured else "Укажите ключ API ГдеМои"
        )

    def toggle_help_chat(self):
        self.help_chat_open = not self.help_chat_open

    def set_help_chat_model_label(self, value: str):
        self.help_chat_model_label = value

    def set_help_chat_input(self, value: str):
        self.help_chat_input = value

    def clear_help_chat(self):
        self.help_chat_messages = []
        self.help_chat_input = ""
        self.help_chat_status = ""

    @rx.event(background=True)
    async def send_help_chat_message(self):
        """Отправляет сообщение в чат-помощник, не блокируя интерфейс."""

        async with self:
            if self.help_chat_busy:
                return
            text = self.help_chat_input.strip()
            if not text:
                return
            self.help_chat_busy = True
            self.help_chat_status = ""
            self.help_chat_input = ""
            history = list(self.help_chat_messages)
            history.append({"role": "user", "content": text})
            self.help_chat_messages = history
            model = HELP_CHAT_MODEL_BY_LABEL.get(self.help_chat_model_label, HELP_CHAT_MODEL_SONNET)

        try:
            reply = await asyncio.to_thread(send_chat_message, history, model)
        except HelpChatError as error:
            async with self:
                self.help_chat_busy = False
                self.help_chat_status = str(error)
            return
        except Exception as error:
            async with self:
                self.help_chat_busy = False
                self.help_chat_status = f"Непредвиденная ошибка: {error}"
            return

        async with self:
            self.help_chat_messages = self.help_chat_messages + [{"role": "assistant", "content": reply}]
            self.help_chat_busy = False
            self.help_chat_status = ""

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
            self.order_mail_metadata = None
            self.order_record_warning = ""
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
            fills = fills_for(self.active_route_count)
            mode_groups = {
                mode: build_groups(load_stores(paths.stores_file_for(mode)), fills, self.active_route_count)
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

    def set_order_client_name(self, value: str):
        self.order_client_name = value

    def set_mode(self, mode: str):
        self.mode = mode
        self.mode_auto_note = ""
        self.mode_detection_warning = ""
        self._reset_preview()

        if self.uploaded_file_path:
            self.status = "Режим изменён. Постройте предварительный просмотр заново."

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
            fills = fills_for(self.active_route_count)
            groups = build_groups(stores, fills, self.active_route_count)
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

    def load_delivery_report(self):
        report = driver_orders.completed_delivery_report()
        self.delivery_completed_stores = report["completed_stores"]
        self.delivery_line_count = report["line_count"]
        self.delivery_summary = report["summary"]
        self.delivery_items = report["deliveries"]

    def load_returns_report(self):
        if not _admin_session_for_router(self.router):
            self.returns_items = []
            return rx.redirect("/login", replace=True)
        try:
            self.returns_items = [_return_view(item) for item in goods_returns.list_returns()]
        except goods_returns.GoodsReturnError as error:
            self.returns_items = []
            self.returns_message = str(error)

    @rx.var
    def returns_filtered(self) -> list[dict]:
        return [
            item for item in self.returns_items
            if (self.returns_status_filter == "Все" or item["status_label"] == self.returns_status_filter)
            and (self.returns_route_filter == "Все" or item["route_label"] == self.returns_route_filter)
            and (self.returns_driver_filter == "Все" or item["driver_filter"] == self.returns_driver_filter)
            and (not self.returns_date_from or item["submitted_at"][:10] >= self.returns_date_from)
            and (not self.returns_date_to or item["submitted_at"][:10] <= self.returns_date_to)
        ]

    @rx.var
    def returns_route_options(self) -> list[str]:
        return ["Все"] + sorted({item["route_label"] for item in self.returns_items})

    @rx.var
    def returns_driver_options(self) -> list[str]:
        return ["Все"] + sorted({item["driver_filter"] for item in self.returns_items})

    @rx.var
    def returns_totals(self) -> dict[str, str]:
        items = self.returns_filtered
        return {
            "submitted": str(sum(item["status"] == "submitted" for item in items)),
            "accepted": str(sum(item["status"] == "accepted" for item in items)),
            "rejected": str(sum(item["status"] == "rejected" for item in items)),
            "pending_kg": format_decimal(sum((Decimal(item["total_net_kg"]) for item in items if item["status"] == "submitted"), Decimal(0))),
            "accepted_kg": format_decimal(sum((Decimal(item["total_net_kg"]) for item in items if item["status"] == "accepted"), Decimal(0))),
        }

    def set_returns_filter(self, field: str, value: str):
        if field not in {"status", "route", "driver", "date_from", "date_to"}:
            return
        if field.startswith("date_"):
            if value:
                try:
                    datetime.strptime(value, "%Y-%m-%d")
                except ValueError:
                    return
            setattr(self, f"returns_{field}", value)
        else:
            setattr(self, f"returns_{field}_filter", value)

    def begin_return_decision(self, document_id: str, decision: str):
        if not _admin_session_for_router(self.router):
            return rx.redirect("/login", replace=True)
        item = next((row for row in self.returns_items if row["id"] == document_id), None)
        if item is None or item["status"] != "submitted" or decision not in {"accepted", "rejected"}:
            return
        self.returns_decision_id = document_id
        self.returns_decision_revision = int(item["revision"])
        self.returns_decision_kind = decision
        self.returns_decision_comment = ""
        self.returns_message = ""

    def set_return_decision_comment(self, value: str):
        self.returns_decision_comment = value[:2000]

    def cancel_return_decision(self):
        self.returns_decision_id = ""
        self.returns_decision_kind = ""
        self.returns_decision_comment = ""

    def confirm_return_decision(self):
        if not _admin_session_for_router(self.router):
            return rx.redirect("/login", replace=True)
        if not self.returns_decision_id:
            return
        try:
            goods_returns.decide_return(
                self.returns_decision_id, self.returns_decision_revision,
                self.returns_decision_kind, self.returns_decision_comment,
                {"kind": "dashboard", "id": "admin", "name": "Администратор"},
            )
        except goods_returns.GoodsReturnError as error:
            self.returns_message = str(error)
            self.load_returns_report()
            return
        self.cancel_return_decision()
        self.load_returns_report()
        self.returns_message = "Решение сохранено"

    def load_fleet(self):
        data = load_fleet()
        vehicles_by_id = {item.get("id", ""): item for item in data["vehicles"]}
        self.fleet_vehicles = [
            {"tracker_id": "", **item} for item in data["vehicles"]
        ]
        self.fleet_driver_options = [""] + [
            item.get("name", "") for item in data["drivers"]
            if item.get("active") and employee_role(item) == "driver"
        ]
        self.fleet_vehicle_options = [""] + [item.get("plate", "") for item in data["vehicles"] if item.get("active")]
        self.fleet_drivers = [
            {
                **driver,
                "login": driver.get("login") or driver.get("id", ""),
                "role": employee_role(driver),
                "role_label": "Грузчик" if employee_role(driver) == "loader" else "Водитель",
                "default_vehicle": vehicles_by_id.get(driver.get("default_vehicle_id", ""), {}).get("plate", "—"),
            }
            for driver in data["drivers"]
        ]

    def set_fleet_tab(self, value: str):
        self.fleet_tab = value
        self.fleet_status = ""

    def set_fleet_driver_field(self, field: str, value: str):
        if field in {"login", "name", "phone", "rating", "hired_on", "notes", "default_vehicle", "pin", "role"}:
            setattr(self, f"fleet_driver_{field}", value)

    def set_fleet_driver_active(self, value: bool):
        self.fleet_driver_active = value

    def clear_fleet_driver_form(self):
        self.fleet_driver_id = ""
        self.fleet_driver_login = ""
        self.fleet_driver_name = ""
        self.fleet_driver_phone = ""
        self.fleet_driver_rating = "5"
        self.fleet_driver_hired_on = ""
        self.fleet_driver_notes = ""
        self.fleet_driver_default_vehicle = ""
        self.fleet_driver_pin = ""
        self.fleet_driver_role = "driver"
        self.fleet_driver_active = True

    def edit_fleet_driver(self, driver_id: str):
        driver = next((item for item in load_fleet()["drivers"] if item.get("id") == driver_id), None)
        if driver is None:
            self.fleet_status = "Водитель не найден"
            return
        self.fleet_driver_id = driver_id
        self.fleet_driver_login = driver.get("login") or driver_id
        self.fleet_driver_name = driver.get("name", "")
        self.fleet_driver_phone = driver.get("phone", "")
        self.fleet_driver_rating = str(driver.get("rating", 5))
        self.fleet_driver_hired_on = driver.get("hired_on", "")
        self.fleet_driver_notes = driver.get("notes", "")
        self.fleet_driver_default_vehicle = next(
            (
                item.get("plate", "")
                for item in load_fleet()["vehicles"]
                if item.get("id") == driver.get("default_vehicle_id", "")
            ),
            "",
        )
        self.fleet_driver_pin = ""
        self.fleet_driver_role = employee_role(driver)
        self.fleet_driver_active = bool(driver.get("active"))

    def save_fleet_driver(self):
        try:
            default_vehicle_id = ""
            if self.fleet_driver_role == "driver":
                default_vehicle_id = next(
                    (
                        item.get("id", "")
                        for item in load_fleet()["vehicles"]
                        if item.get("plate") == self.fleet_driver_default_vehicle
                    ),
                    "",
                )
                if self.fleet_driver_default_vehicle and not default_vehicle_id:
                    raise FleetError("Выбранный транспорт не найден")
            if self.fleet_driver_id:
                if self.fleet_driver_pin:
                    set_driver_pin(self.fleet_driver_id, self.fleet_driver_pin)
                update_driver(
                    self.fleet_driver_id, self.fleet_driver_name, self.fleet_driver_phone,
                    self.fleet_driver_rating, self.fleet_driver_active, self.fleet_driver_hired_on,
                    self.fleet_driver_notes, default_vehicle_id, self.fleet_driver_login,
                    self.fleet_driver_role,
                )
                self.fleet_status = "Карточка сотрудника обновлена"
            else:
                driver = add_driver(
                    self.fleet_driver_name, self.fleet_driver_phone, self.fleet_driver_rating,
                    self.fleet_driver_active, self.fleet_driver_hired_on, self.fleet_driver_notes,
                    default_vehicle_id, self.fleet_driver_login, self.fleet_driver_role,
                )
                if self.fleet_driver_pin:
                    set_driver_pin(driver["id"], self.fleet_driver_pin)
                self.fleet_status = "Сотрудник добавлен"
            self.clear_fleet_driver_form()
            self.load_fleet()
        except FleetError as error:
            self.fleet_status = str(error)

    def delete_fleet_driver(self, driver_id: str):
        try:
            delete_driver(driver_id)
            self.clear_fleet_driver_form()
            self.load_fleet()
            self.fleet_status = "Водитель удалён"
        except FleetError as error:
            self.fleet_status = str(error)

    def set_fleet_vehicle_field(self, field: str, value: str):
        if field in {"name", "plate", "odometer", "description", "notes", "tracker_id"}:
            setattr(self, f"fleet_vehicle_{field}", value)

    def set_fleet_vehicle_active(self, value: bool):
        self.fleet_vehicle_active = value

    def clear_fleet_vehicle_form(self):
        self.fleet_vehicle_id = ""
        self.fleet_vehicle_name = ""
        self.fleet_vehicle_plate = ""
        self.fleet_vehicle_odometer = "0"
        self.fleet_vehicle_description = ""
        self.fleet_vehicle_notes = ""
        self.fleet_vehicle_active = True
        self.fleet_vehicle_tracker_id = ""

    def edit_fleet_vehicle(self, vehicle_id: str):
        vehicle = next((item for item in load_fleet()["vehicles"] if item.get("id") == vehicle_id), None)
        if vehicle is None:
            self.fleet_status = "Транспорт не найден"
            return
        self.fleet_vehicle_id = vehicle_id
        self.fleet_vehicle_name = vehicle.get("name", "")
        self.fleet_vehicle_plate = vehicle.get("plate", "")
        self.fleet_vehicle_odometer = str(vehicle.get("odometer_km", 0))
        self.fleet_vehicle_description = vehicle.get("description", "")
        self.fleet_vehicle_notes = vehicle.get("notes", "")
        self.fleet_vehicle_active = bool(vehicle.get("active"))
        self.fleet_vehicle_tracker_id = vehicle.get("tracker_id", "")

    def save_fleet_vehicle(self):
        try:
            if self.fleet_vehicle_id:
                update_vehicle(
                    self.fleet_vehicle_id, self.fleet_vehicle_name, self.fleet_vehicle_plate,
                    self.fleet_vehicle_odometer, self.fleet_vehicle_description,
                    self.fleet_vehicle_notes, self.fleet_vehicle_active, self.fleet_vehicle_tracker_id,
                )
                self.fleet_status = "Карточка транспорта обновлена"
            else:
                add_vehicle(
                    self.fleet_vehicle_name, self.fleet_vehicle_plate, self.fleet_vehicle_odometer,
                    self.fleet_vehicle_description, self.fleet_vehicle_notes, self.fleet_vehicle_active,
                    self.fleet_vehicle_tracker_id,
                )
                self.fleet_status = "Транспорт добавлен"
            self.clear_fleet_vehicle_form()
            self.load_fleet()
        except FleetError as error:
            self.fleet_status = str(error)

    def delete_fleet_vehicle(self, vehicle_id: str):
        try:
            delete_vehicle(vehicle_id)
            self.clear_fleet_vehicle_form()
            self.load_fleet()
            self.fleet_status = "Транспорт удалён"
        except FleetError as error:
            self.fleet_status = str(error)

    def ask_delete_fleet_item(self, kind: str, item_id: str):
        if kind in {"driver", "vehicle"}:
            self.fleet_delete_pending_kind = kind
            self.fleet_delete_pending_id = item_id

    def cancel_delete_fleet_item(self):
        self.fleet_delete_pending_kind = ""
        self.fleet_delete_pending_id = ""

    def confirm_delete_fleet_item(self):
        item_id = self.fleet_delete_pending_id
        kind = self.fleet_delete_pending_kind
        self.cancel_delete_fleet_item()
        if kind == "driver":
            self.delete_fleet_driver(item_id)
        elif kind == "vehicle":
            self.delete_fleet_vehicle(item_id)

    def open_route_assignment_dialog(self):
        if (
            not self.preview_ready
            or self.preview_source != self.uploaded_file_path
            or self.preview_mode != self.mode
        ):
            self.status = "Сначала постройте предварительный просмотр для этого режима"
            return
        drivers = active_drivers()
        vehicles = active_vehicles()
        driver_by_name = {item.get("name", ""): item for item in drivers}
        vehicle_by_id = {item.get("id", ""): item for item in vehicles}
        assignments = []
        for index in range(self.active_route_count):
            legacy_name = self.route_driver_names[index] if index < len(self.route_driver_names) else "----"
            driver = driver_by_name.get(legacy_name, {})
            vehicle = vehicle_by_id.get(driver.get("default_vehicle_id", ""), {})
            assignments.append({
                "route": f"route_{index + 1}",
                "label": f"Маршрут №{index + 1}",
                "driver_id": driver.get("id", ""),
                "driver_name": driver.get("name", legacy_name if legacy_name != "----" else ""),
                "vehicle_id": vehicle.get("id", ""),
                "vehicle_name": vehicle.get("name", ""),
                "vehicle_plate": vehicle.get("plate", ""),
                "vehicle_description": vehicle.get("description", ""),
            })
        self.fleet_driver_options = [""] + [item.get("name", "") for item in drivers]
        self.fleet_driver_options += [
            item["driver_name"]
            for item in assignments
            if item["driver_name"] and item["driver_name"] not in self.fleet_driver_options
        ]
        self.fleet_vehicle_options = [""] + [item.get("plate", "") for item in vehicles]
        self.route_assignments = assignments
        self.route_assignment_open = True

    def cancel_route_assignments(self):
        self.route_assignment_open = False
        self.route_assignments = []

    def set_route_assignment_driver(self, index: int, driver_name: str):
        assignments = list(self.route_assignments)
        if not 0 <= index < len(assignments):
            return
        driver = next((item for item in active_drivers() if item.get("name") == driver_name), {})
        vehicle = next((item for item in active_vehicles() if item.get("id") == driver.get("default_vehicle_id")), {})
        assignments[index] = {
            **assignments[index],
            "driver_id": driver.get("id", ""),
            "driver_name": driver.get("name", ""),
            "vehicle_id": vehicle.get("id", ""),
            "vehicle_name": vehicle.get("name", ""),
            "vehicle_plate": vehicle.get("plate", ""),
            "vehicle_description": vehicle.get("description", ""),
        }
        self.route_assignments = assignments

    def set_route_assignment_vehicle(self, index: int, plate: str):
        assignments = list(self.route_assignments)
        if not 0 <= index < len(assignments):
            return
        vehicle = next((item for item in active_vehicles() if item.get("plate") == plate), {})
        assignments[index] = {
            **assignments[index],
            "vehicle_id": vehicle.get("id", ""),
            "vehicle_name": vehicle.get("name", ""),
            "vehicle_plate": vehicle.get("plate", ""),
            "vehicle_description": vehicle.get("description", ""),
        }
        self.route_assignments = assignments

    def confirm_route_assignments(self):
        if (
            not self.preview_ready
            or self.preview_source != self.uploaded_file_path
            or self.preview_mode != self.mode
        ):
            self.cancel_route_assignments()
            self.status = "Предварительный просмотр устарел. Постройте его заново"
            return
        self.route_assignment_open = False
        self.process_order()

    def process_order(self):
        if not self.uploaded_file_path:
            self.status = "Сначала загрузите Excel-файл"
            return
        if not self.order_client_name.strip():
            self.status = "Укажите клиента перед обработкой заказа"
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
            settings = {
                **load_settings(),
                "open_file_after_processing": False,
                "open_folder_after_processing": False,
            }

            stores = load_stores(stores_file)
            fills = fills_for(self.active_route_count)
            groups = build_groups(stores, fills, self.active_route_count)

            assigned_drivers = {
                item["route"]: item["driver_name"]
                for item in self.route_assignments
                if item.get("driver_name")
            }
            output_file, log_file, stats = run_pipeline(
                self.uploaded_file_path,
                settings,
                groups,
                conflict_fill,
                assigned_drivers or None,
            )

            route_totals = list(stats.get("route_totals", {}).values())
            while len(route_totals) < MAX_ROUTES:
                route_totals.append(0)

            self.route_totals = [format_number(total) for total in route_totals]
            self.grand_total = format_number(sum(route_totals))
            self.conflict_count = int(stats.get("conflict_count", 0))
            self.unknown_count = len(stats.get("unknown_stores", []))
            self.output_file = str(output_file)
            self.log_file = str(log_file)
            self.order_record_warning = ""
            order_record = None
            try:
                order_record = create_processed_order_record(
                    self.output_file,
                    self.selected_file,
                    self.order_client_name,
                    self.mode,
                    self.order_mail_metadata,
                )
            except OrderRecordError as error:
                self.order_record_warning = f"Реестр загрузки не обновлён: {error}"
            if self.route_assignments:
                record_order_route_assignments(
                    self.selected_file,
                    self.mode,
                    self.output_file,
                    self.route_assignments,
                )
                published_assignments = [
                    item for item in self.route_assignments
                    if item.get("driver_id")
                ]
                if published_assignments:
                    driver_orders.publish_assignments(
                        self.output_file,
                        self.mode,
                        self.selected_file,
                        published_assignments,
                        order_record,
                    )
            self.route_assignments = []
            self.status = "Обработка завершена"
            if self.order_record_warning:
                self.status += f" · {self.order_record_warning}"

            record_processing(self.selected_file, stats)
            processed_at = was_processed(self.selected_file)
            self.duplicate_note = (
                f"Этот файл уже обрабатывался {processed_at}. "
                "Повторная обработка обновит суммы, а не добавит их ещё раз."
            )
            self.load_history()
            self._reset_preview()

        except driver_orders.DriverOrderError as error:
            self.status = "Файл обработан, но задание водителю не опубликовано"
            self.error_text = (
                f"{error}. Координата относится к обработанному файлу; "
                "проверьте соответствующее значение в исходном заказе и повторите обработку."
            )

        except Exception:
            self.status = "Ошибка обработки"
            self.error_text = traceback.format_exc()

        finally:
            self.is_processing = False


_dispatch_overview = partial(_view__dispatch_overview, State=State)
_dispatch_route_button = partial(_view__dispatch_route_button, State=State)
_routes_editor = partial(_view__routes_editor, State=State)
_template_dialogs = partial(_view__template_dialogs, State=State)
_template_route_tile = partial(_view__template_route_tile, State=State)
_template_store_tile = partial(_view__template_store_tile, State=State)
app_header = partial(_view_app_header, State=State)
app_tabs = partial(_view_app_tabs, State=State)
backup_page = partial(_view_backup_page, State=State)
dashboard_tracking_preview = partial(_view_dashboard_tracking_preview, State=State)
delivery_page = partial(_view_delivery_page, State=State)
event_log_panel = partial(_view_event_log_panel, State=State)
fleet_driver_card = partial(_view_fleet_driver_card, State=State)
fleet_drivers_tab = partial(_view_fleet_drivers_tab, State=State)
fleet_page = partial(_view_fleet_page, State=State)
fleet_vehicle_card = partial(_view_fleet_vehicle_card, State=State)
fleet_vehicles_tab = partial(_view_fleet_vehicles_tab, State=State)
help_chat_widget = partial(_view_help_chat_widget, State=State)
help_page = partial(_view_help_page, State=State)
history_page = partial(_view_history_page, State=State)
history_panel = partial(_view_history_panel, State=State)
history_row = partial(_view_history_row, State=State)
invoice_ocr_line = partial(_view_invoice_ocr_line, State=State)
invoice_ocr_page = partial(_view_invoice_ocr_page, State=State)
mail_item_row = partial(_view_mail_item_row, State=State)
mail_page = partial(_view_mail_page, State=State)
mail_setup_hint = partial(_view_mail_setup_hint, State=State)
order_details_drawer = partial(_view_order_details_drawer, State=State)
order_invoice_row = partial(_view_order_invoice_row, State=State)
order_panel = partial(_view_order_panel, State=State)
order_preview_panel = partial(_view_order_preview_panel, State=State)
order_source_file_row = partial(_view_order_source_file_row, State=State)
orders_page = partial(_view_orders_page, State=State)
overview_page = partial(_view_overview_page, State=State)
page_primary_action = partial(_view_page_primary_action, State=State)
page_tab = partial(_view_page_tab, State=State)
processed_file_row = partial(_view_processed_file_row, State=State)
processing_summary = partial(_view_processing_summary, State=State)
rail_item = partial(_view_rail_item, State=State)
rating_panel = partial(_view_rating_panel, State=State)
real_data_section = partial(_view_real_data_section, State=State)
return_item_card = partial(_view_return_item_card, State=State)
returns_page = partial(_view_returns_page, State=State)
route_assignment_dialog = partial(_view_route_assignment_dialog, State=State)
route_assignment_row = partial(_view_route_assignment_row, State=State)
route_driver_row = partial(_view_route_driver_row, State=State)
route_drivers_panel = partial(_view_route_drivers_panel, State=State)
routes_backup_bar = partial(_view_routes_backup_bar, State=State)
routes_page = partial(_view_routes_page, State=State)
settings_page = partial(_view_settings_page, State=State)
sidebar = partial(_view_sidebar, State=State)
simulation_section = partial(_view_simulation_section, State=State)
start_pause_button = partial(_view_start_pause_button, State=State)
tracking_controls = partial(_view_tracking_controls, State=State)
tracking_legend = partial(_view_tracking_legend, State=State)
tracking_map_panel = partial(_view_tracking_map_panel, State=State)
tracking_page = partial(_view_tracking_page, State=State)
tracking_view_toggle = partial(_view_tracking_view_toggle, State=State)
version_page = partial(_view_version_page, State=State)
volume_chart_panel = partial(_view_volume_chart_panel, State=State)
weight_draft_row = partial(_view_weight_draft_row, State=State)
weight_name_autocomplete_option = partial(_view_weight_name_autocomplete_option, State=State)
weight_name_suggestion_chip = partial(_view_weight_name_suggestion_chip, State=State)
weight_page = partial(_view_weight_page, State=State)
weight_row = partial(_view_weight_row, State=State)


def main_content():
    return rx.match(
        State.current_page,
        ("Заказы", orders_page()),
        ("Помощь", help_page()),
        ("Почта", mail_page()),
        ("Маршруты", routes_page()),
        ("Водители и транспорт", fleet_page()),
        ("Сданный товар", delivery_page()),
        ("Возвраты", returns_page()),
        ("Вес", weight_page()),
        ("OCR накладных", invoice_ocr_page()),
        ("Трекинг", tracking_page()),
        ("История", history_page()),
        ("Настройки", settings_page()),
        ("Версия", version_page()),
        ("Резервные копии", backup_page()),
        overview_page(),
    )


def dashboard_shell():
    return rx.fragment(
        rx.el.a("Перейти к содержимому", href="#dashboard-content", class_name="dashboard-skip-link"),
        rx.el.div(
            sidebar(),
            rx.el.div(app_header(), app_tabs(),
                      rx.el.main(main_content(), id="dashboard-content", tab_index=-1), class_name="main-shell"),
            class_name=rx.cond(State.sidebar_collapsed, "app dashboard-design app-collapsed", "app dashboard-design"),
        ),
        order_details_drawer(), route_assignment_dialog(),
        rx.cond(State.current_page == "Помощь", help_chat_widget(), rx.box(display="none")),
    )


def dashboard():
    return rx.cond(
        State.is_authenticated,
        dashboard_shell(),
        rx.center(
            rx.spinner(size="3"),
            width="100%",
            min_height="100vh",
            background=ui.PAGE,
        ),
    )


def driver_page():
    return rx.center(
        rx.box(id="driver-app", width="100%"),
        width="100%",
        min_height="100vh",
        background=page_bg(),
        class_name="driver-page",
    )


def loader_page():
    return rx.center(
        rx.box(id="loader-app", width="100%"),
        width="100%",
        min_height="100vh",
        background=page_bg(),
        class_name="driver-page",
    )


DASHBOARD_UPLOAD_HANDLERS = frozenset({"handle_upload", "recognize_invoice_photos"})


class DashboardUploadAuth:
    """Проверяет настоящую HTTP-сессию до обработки файлов Reflex."""

    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] == "http" and scope.get("path", "").rstrip("/") == "/_upload":
            request = Request(scope)
            if not _dashboard_download_authorized(request):
                response = JSONResponse({"ok": False, "error": "Требуется вход"}, status_code=401)
                await response(scope, receive, send)
                return
        await self.app(scope, receive, send)


class DashboardAuthMiddleware(rx.Middleware):
    """Не даёт анонимному клиенту вызвать обработчики административного state."""

    _PUBLIC_EVENTS = frozenset({
        "hydrate",
        "load_dashboard",
        "redirect_authenticated_user",
    })

    async def preprocess(self, app, state, event) -> StateUpdate | None:
        prefix = f"{State.get_full_name()}."
        if not event.name.startswith(prefix):
            return None

        event_name = event.name.removeprefix(prefix)
        if event_name in self._PUBLIC_EVENTS:
            return None

        if _admin_session_for_router(event.router_data):
            dashboard_state = await state.get_state(State)
            dashboard_state.is_authenticated = True
            return None

        # HTTP-загрузки Reflex не содержат router_data. Cookie запроса уже
        # проверен DashboardUploadAuth; здесь проверяем живую серверную сессию.
        if event_name in DASHBOARD_UPLOAD_HANDLERS and not event.router_data:
            dashboard_state = await state.get_state(State)
            if _admin_session_for_router(dashboard_state.router):
                dashboard_state.is_authenticated = True
                return None

        return StateUpdate(
            events=Event.from_event_type(
                rx.redirect("/login", replace=True),
                router_data=event.router_data,
            )
        )


PWA_META = [
    {"name": "theme-color", "content": "#ffffff"},
    {"name": "mobile-web-app-capable", "content": "yes"},
    {"name": "apple-mobile-web-app-capable", "content": "yes"},
    {"name": "apple-mobile-web-app-status-bar-style", "content": "default"},
    {"name": "apple-mobile-web-app-title", "content": "Логистика"},
    rx.el.link(rel="manifest", href="/manifest.webmanifest"),
    rx.el.link(rel="icon", href="/icon-192.svg", type="image/svg+xml"),
]


app = rx.App(
    api_transformer=[custom_api, DashboardUploadAuth],
    html_lang="ru",
    head_components=[rx.el.script(src="/theme-preference.js"), rx.el.script(src="/workspace-bootstrap.js"), rx.el.script(src="/route-template-dnd.js")],
    stylesheets=[
        "/theme.css",
        "/dashboard-design.css",
        "/scrollbar.css",
    ],
    style={
        "font_family": ui.FONT_FAMILY,
        "--default-font-family": ui.FONT_FAMILY,
        "background": ui.PAGE,
        "color": ui.INK,
        "font_size": ui.FONT_SIZE_BODY,
    },
)
app.add_middleware(DashboardAuthMiddleware())
app.add_middleware(LoadingAuthMiddleware())
app.add_middleware(TripAuthMiddleware())
app.add_page(vehicle_trips_page, route="/trips", title="Рейсы машин", on_load=TripState.load_page, meta=PWA_META)
app.add_page(
    dashboard,
    route="/",
    title="Обработка заказов",
    on_load=State.load_dashboard,
    meta=PWA_META,
)
app.add_page(
    login_page,
    route="/login",
    title="Вход",
    on_load=State.redirect_authenticated_user,
    meta=PWA_META,
)
app.add_page(
    driver_page,
    route="/driver",
    title="Водитель",
    meta=PWA_META,
)
app.add_page(driver_page, route="/crew", title="Кабинет машины", meta=PWA_META)
app.add_page(
    loader_page,
    route="/loader",
    title="Грузчик",
    meta=PWA_META,
)
app.add_page(
    loading_page,
    route="/loading",
    title="Загрузка",
    on_load=LoadingState.load_loading_page,
    meta=PWA_META,
)
