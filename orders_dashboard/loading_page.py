"""Warehouse loading workspace."""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal, InvalidOperation
from http.cookies import CookieError, SimpleCookie

import reflex as rx
from reflex.state import StateUpdate
from reflex_base.event import Event

from modules import dashboard_sessions, loader_sessions
from modules.fleet import loader_by_id
from modules.order_records import (
    OrderRecordConflict,
    OrderRecordError,
    OrderRecordNotFound,
    list_order_record_summaries,
    load_order_record,
    save_loading_update,
)
from orders_dashboard import theme as ui


ENABLE_WEIGHT_MODE = False


def _cookie(router, name: str) -> str:
    headers = getattr(router, "headers", None)
    if headers is None and isinstance(router, dict):
        headers = router.get("headers", {})
    cookie_header = headers.get("cookie", "") if isinstance(headers, dict) else getattr(headers, "cookie", "")
    try:
        cookies = SimpleCookie(cookie_header or "")
    except CookieError:
        return ""
    value = cookies.get(name)
    return value.value if value else ""


def loading_principal_for_router(router) -> dict | None:
    dashboard_token = _cookie(router, dashboard_sessions.SESSION_COOKIE)
    if dashboard_sessions.valid_session(dashboard_token):
        return {"kind": "dashboard", "id": "admin", "name": "Администратор"}

    loader_token = _cookie(router, loader_sessions.SESSION_COOKIE)
    session = loader_sessions.get_session(loader_token)
    if session is None or session.get("role") != "loader":
        return None
    loader = loader_by_id(str(session.get("loader_id", "")))
    if loader is None or not loader.get("active"):
        return None
    return {
        "kind": "loader",
        "id": str(loader.get("id", "")),
        "name": str(loader.get("name", "Грузчик")),
    }


def _query_param(router, name: str) -> str:
    page = getattr(router, "page", None)
    params = getattr(page, "params", None)
    if params is None and isinstance(router, dict):
        params = router.get("params", {})
    if not isinstance(params, dict):
        return ""
    value = params.get(name, "")
    return str(value[0] if isinstance(value, list) and value else value)


def _format_date(value: str) -> str:
    try:
        return datetime.fromisoformat(value).strftime("%d.%m.%y %H:%M")
    except ValueError:
        return value


def _number(value: str) -> Decimal:
    return Decimal(value or "0")


def _format_number(value: Decimal) -> str:
    rendered = format(value, "f")
    return rendered.rstrip("0").rstrip(".") if "." in rendered else rendered


def _route_summary(record: dict) -> str:
    routes = []
    for route in record.get("routes", []):
        destinations = ", ".join(item.get("name", "") for item in route.get("destinations", []))
        area = str(route.get("area", ""))
        location = f"{area}: {destinations}" if area else destinations
        routes.append(f"{route.get('route_label', '')}: {location}".strip(": "))
    return " · ".join(item for item in routes if item)


def _loading_rows(record: dict, box_counts: dict[str, str]) -> list[dict]:
    return [
        {
            "id": str(line.get("id", "")),
            "name": str(line.get("name", "")),
            "planned_kg": str(line.get("planned_amount", "0")),
            "loaded_box_count": str(box_counts.get(str(line.get("id", "")), "")),
        }
        for line in record.get("loading_lines", [])
    ]


def _loading_totals(rows: list[dict]) -> tuple[str, str]:
    ordered_kg = sum((_number(row["planned_kg"]) for row in rows), Decimal("0"))
    if any(row["loaded_box_count"] == "" for row in rows):
        return _format_number(ordered_kg), ""
    try:
        loaded_boxes = sum((_number(row["loaded_box_count"]) for row in rows), Decimal("0"))
    except (InvalidOperation, ValueError):
        return _format_number(ordered_kg), ""
    return _format_number(ordered_kg), _format_number(loaded_boxes)


class LoadingState(rx.State):
    is_authorized: bool = False
    principal: dict = {}
    order_options: list[dict] = []
    order_option_labels: list[str] = []
    selected_order_label: str = ""
    selected_order_id: str = ""
    back_target: str = "/"
    selected_record: dict = {}
    summary_order_number: str = ""
    summary_client_name: str = ""
    summary_processed_at: str = ""
    summary_mode: str = ""
    summary_routes: str = ""
    summary_received_at: str = ""
    summary_position_count: int = 0
    total_ordered_kg: str = "0"
    total_loaded_boxes: str = ""
    loading_rows: list[dict] = []
    draft_box_counts: dict[str, str] = {}
    summary_expanded: bool = True
    is_read_only: bool = False
    is_dirty: bool = False
    pending_order_id: str = ""
    pending_exit: bool = False
    discard_confirmation_open: bool = False
    status: str = ""
    order_not_found: bool = False
    save_completed: bool = False

    def _refresh_options(self):
        self.order_options = [
            {
                **item,
                "label": f"{item['order_number']} · {item['client_name']} · {_format_date(item['processed_at'])}",
            }
            for item in list_order_record_summaries()
        ]
        self.order_option_labels = [item["label"] for item in self.order_options]

    def _apply_record(self, order_record_id: str) -> bool:
        if not order_record_id:
            self.selected_order_id = ""
            self.selected_order_label = ""
            self.selected_record = {}
            self.summary_order_number = ""
            self.summary_client_name = ""
            self.summary_processed_at = ""
            self.summary_mode = ""
            self.summary_routes = ""
            self.summary_received_at = ""
            self.summary_position_count = 0
            self.total_ordered_kg = "0"
            self.total_loaded_boxes = ""
            self.loading_rows = []
            self.draft_box_counts = {}
            self.is_read_only = False
            return True
        try:
            record = load_order_record(order_record_id)
        except OrderRecordNotFound:
            self.selected_order_id = ""
            self.selected_order_label = ""
            self.selected_record = {}
            self.summary_order_number = ""
            self.summary_client_name = ""
            self.summary_processed_at = ""
            self.summary_mode = ""
            self.summary_routes = ""
            self.summary_received_at = ""
            self.summary_position_count = 0
            self.total_ordered_kg = "0"
            self.total_loaded_boxes = ""
            self.loading_rows = []
            self.draft_box_counts = {}
            self.is_read_only = False
            self.order_not_found = True
            self.status = "Заказ не найден"
            return False

        self.selected_order_id = order_record_id
        self.selected_order_label = next(
            (item["label"] for item in self.order_options if item["id"] == order_record_id),
            "",
        )
        self.selected_record = record
        self.summary_order_number = str(record.get("order_number", ""))
        self.summary_client_name = str(record.get("client_name", ""))
        self.summary_processed_at = _format_date(str(record.get("processed_at", "")))
        self.summary_mode = str(record.get("mode", ""))
        self.summary_routes = _route_summary(record)
        self.summary_received_at = str((record.get("mail_metadata") or {}).get("received_display", ""))
        self.summary_position_count = len(record.get("loading_lines", []))
        self.draft_box_counts = {
            str(line["id"]): str(line.get("loaded_box_count", ""))
            for line in record.get("loading_lines", [])
        }
        self.loading_rows = _loading_rows(record, self.draft_box_counts)
        self.total_ordered_kg, self.total_loaded_boxes = _loading_totals(self.loading_rows)
        self.is_read_only = (record.get("loading") or {}).get("status") == "loaded"
        self.is_dirty = False
        self.order_not_found = False
        self.save_completed = False
        self.status = ""
        return True

    def load_loading_page(self):
        principal = loading_principal_for_router(self.router)
        if principal is None:
            return rx.redirect("/loader", replace=True)
        self.is_authorized = True
        self.principal = principal
        self.back_target = "/?page=history" if _query_param(self.router, "from") == "history" else "/"
        self._refresh_options()
        requested_order_id = _query_param(self.router, "order")
        self._apply_record(requested_order_id)

    def request_order_label(self, label: str):
        order_record_id = next(
            (item["id"] for item in self.order_options if item["label"] == label),
            "",
        )
        return self.request_order(order_record_id)

    def request_order(self, order_record_id: str):
        if order_record_id == self.selected_order_id:
            return
        if self.is_dirty:
            self.pending_order_id = order_record_id
            self.discard_confirmation_open = True
            return
        return self.select_order(order_record_id)

    def select_order(self, order_record_id: str):
        self._apply_record(order_record_id)
        return rx.redirect(f"/loading?order={order_record_id}" if order_record_id else "/loading")

    def cancel_discard(self):
        self.pending_order_id = ""
        self.pending_exit = False
        self.discard_confirmation_open = False

    def confirm_discard(self):
        order_record_id = self.pending_order_id
        exit_page = self.pending_exit
        self.pending_order_id = ""
        self.pending_exit = False
        self.discard_confirmation_open = False
        if exit_page:
            return rx.redirect(self.back_target)
        return self.select_order(order_record_id)

    def set_loaded_box_count(self, line_id: str, value: str):
        if self.is_read_only or line_id not in self.draft_box_counts:
            return
        amounts = dict(self.draft_box_counts)
        amounts[line_id] = value
        self.draft_box_counts = amounts
        self.loading_rows = _loading_rows(self.selected_record, amounts)
        self.total_ordered_kg, self.total_loaded_boxes = _loading_totals(self.loading_rows)
        self.is_dirty = True
        self.save_completed = False
        self.status = ""

    def toggle_summary(self):
        self.summary_expanded = not self.summary_expanded

    def save_loading(self):
        if not self.selected_order_id:
            self.status = "Выберите заказ"
            return
        if self.is_read_only:
            self.status = "Загрузка уже сохранена и доступна только для просмотра"
            return
        if any(value.strip() == "" for value in self.draft_box_counts.values()):
            self.status = "Заполните загрузку для каждой позиции"
            return
        try:
            record = save_loading_update(
                self.selected_order_id,
                int(self.selected_record.get("revision", -1)),
                self.draft_box_counts,
                self.principal,
            )
        except OrderRecordConflict as error:
            self.status = str(error)
            self._apply_record(self.selected_order_id)
            return
        except OrderRecordError as error:
            self.status = str(error)
            return
        self.selected_record = record
        self.draft_box_counts = {
            str(line["id"]): str(line.get("loaded_box_count", ""))
            for line in record.get("loading_lines", [])
        }
        self.loading_rows = _loading_rows(record, self.draft_box_counts)
        self.total_ordered_kg, self.total_loaded_boxes = _loading_totals(self.loading_rows)
        self.is_read_only = (record.get("loading") or {}).get("status") == "loaded"
        self.is_dirty = False
        self.save_completed = True
        self.status = "Загрузка сохранена"
        self._refresh_options()

    def load_next_order(self):
        for item in self.order_options:
            if item["id"] != self.selected_order_id and item["status"] != "loaded":
                return self.select_order(item["id"])
        self.status = "Следующих заказов для загрузки нет"

    def back_to_orders(self):
        if self.is_dirty:
            self.pending_exit = True
            self.discard_confirmation_open = True
            return
        return rx.redirect(self.back_target)


def _loading_summary():
    return rx.vstack(
        rx.button(
            rx.hstack(
                rx.vstack(
                    rx.text(LoadingState.summary_order_number, color=ui.INK, font_weight=ui.FONT_WEIGHT_SEMIBOLD),
                    rx.text(LoadingState.summary_client_name, color=ui.INK_2, font_size="13px"),
                    align="start", spacing="1",
                ),
                rx.spacer(),
                rx.text("Свернуть", color=ui.PURPLE, font_size="13px"),
                width="100%", align="center",
            ),
            on_click=LoadingState.toggle_summary,
            width="100%", padding="0", background=ui.TRANSPARENT, border="0", cursor="pointer",
        ),
        rx.cond(
            LoadingState.summary_expanded,
            rx.vstack(
                rx.text("Обработан: ", LoadingState.summary_processed_at, color=ui.INK_2, font_size="13px"),
                rx.text("Режим: ", LoadingState.summary_mode, color=ui.INK_2, font_size="13px"),
                rx.text("Маршруты: ", LoadingState.summary_routes, color=ui.INK_2, font_size="13px"),
                rx.text("Письмо: ", LoadingState.summary_received_at, color=ui.INK_2, font_size="13px"),
                rx.text("Позиций: ", LoadingState.summary_position_count, color=ui.INK_2, font_size="13px"),
                align="start", spacing="1", width="100%",
            ),
            rx.box(),
        ),
        align="start", spacing="3", width="100%", padding="16px",
        border=f"1px solid {ui.LINE}", border_radius="12px", background=ui.PANEL,
        class_name="loading-summary",
    )


def _loading_table():
    return rx.vstack(
        rx.hstack(
            rx.text("Товар", class_name="loading-table-title"),
            rx.text("Заказано, кг", class_name="loading-table-title"),
            rx.text("Загружено, ящики", class_name="loading-table-title"),
            class_name="loading-table-row loading-table-header",
        ),
        rx.foreach(
            LoadingState.loading_rows,
            lambda row: rx.hstack(
                rx.text(row["name"], color=ui.INK, font_weight=ui.FONT_WEIGHT_MEDIUM, min_width="0"),
                rx.text(row["planned_kg"], " кг", color=ui.INK_2),
                rx.input(
                    value=row["loaded_box_count"],
                    on_change=LoadingState.set_loaded_box_count(row["id"]),
                    type="number",
                    min="0",
                    step="1",
                    disabled=LoadingState.is_read_only,
                    class_name="loading-amount-input",
                ),
                class_name="loading-table-row",
                align="center",
            ),
        ),
        rx.hstack(
            rx.text("Итого", font_weight=ui.FONT_WEIGHT_SEMIBOLD),
            rx.text("Заказано: ", LoadingState.total_ordered_kg, " кг", color=ui.INK_2),
            rx.text("Загружено: ", LoadingState.total_loaded_boxes, " ящ.", color=ui.INK_2),
            rx.spacer(),
            class_name="loading-table-total",
        ),
        width="100%", spacing="0", class_name="loading-table",
    )


def _discard_dialog():
    return rx.cond(
        LoadingState.discard_confirmation_open,
        rx.box(
            rx.vstack(
                rx.heading("Есть несохранённые данные", size="5", color=ui.INK),
                rx.text("Выйти без сохранения?", color=ui.INK_2),
                rx.hstack(
                    rx.button("Остаться", on_click=LoadingState.cancel_discard, class_name="loading-secondary-button"),
                    rx.button("Выйти", on_click=LoadingState.confirm_discard, class_name="loading-primary-button"),
                    width="100%", justify="end", spacing="2",
                ),
                align="start", spacing="4", padding="20px", width="min(420px, calc(100vw - 32px))",
                background=ui.PANEL, border_radius="14px",
            ),
            position="fixed", inset="0", display="flex", align_items="center", justify_content="center",
            background="rgba(20, 25, 36, .45)", z_index="100",
        ),
        rx.box(),
    )


DIRTY_GUARD_JS = """
(() => {
    if (window.__loadingDirtyGuard) return;
    window.__loadingDirtyGuard = true;
    window.addEventListener('beforeunload', (event) => {
        const marker = document.getElementById('loading-dirty-state');
        if (marker?.dataset.dirty !== 'true') return;
        event.preventDefault();
        event.returnValue = '';
    });
})();
"""


def loading_page():
    return rx.cond(
        LoadingState.is_authorized,
        rx.box(
            rx.box(
                id="loading-dirty-state",
                custom_attrs={"data-dirty": LoadingState.is_dirty},
                display="none",
            ),
            rx.script(DIRTY_GUARD_JS),
            rx.vstack(
                rx.hstack(
                    rx.button("← Назад", on_click=LoadingState.back_to_orders, class_name="loading-secondary-button"),
                    rx.vstack(
                        rx.heading("Загрузка", color=ui.INK, size="6"),
                        rx.text("Фактическая загрузка заказа", color=ui.INK_2, font_size="13px"),
                        align="start", spacing="1",
                    ),
                    width="100%", align="center", spacing="3",
                ),
                rx.vstack(
                    rx.text("Заказ", color=ui.INK_2, font_size="13px"),
                    rx.select(
                        LoadingState.order_option_labels,
                        value=LoadingState.selected_order_label,
                        on_change=LoadingState.request_order_label,
                        placeholder="Выберите заказ",
                        width="100%",
                        class_name="loading-select",
                    ),
                    align="start", spacing="1", width="100%",
                ),
                rx.cond(LoadingState.order_not_found, rx.text("Заказ не найден", color=ui.STATUS_RED_TEXT), rx.box()),
                rx.cond(
                    LoadingState.selected_order_id != "",
                    rx.vstack(
                        _loading_summary(),
                        _loading_table(),
                        rx.cond(
                            LoadingState.is_read_only,
                            rx.text("Загрузка сохранена. Доступен режим просмотра.", color=ui.STATUS_GREEN_TEXT),
                            rx.button("Сохранить загрузку", on_click=LoadingState.save_loading, class_name="loading-primary-button"),
                        ),
                        rx.cond(LoadingState.status != "", rx.text(LoadingState.status, color=ui.PURPLE, font_size="13px"), rx.box()),
                        rx.cond(
                            LoadingState.save_completed,
                            rx.hstack(
                                rx.button("К списку заказов", on_click=LoadingState.back_to_orders, class_name="loading-secondary-button"),
                                rx.button("Загрузить следующий заказ", on_click=LoadingState.load_next_order, class_name="loading-primary-button"),
                                wrap="wrap", spacing="2",
                            ),
                            rx.box(),
                        ),
                        align="start", spacing="4", width="100%",
                    ),
                    rx.text("Выберите заказ, чтобы начать загрузку.", color=ui.INK_2),
                ),
                align="start", spacing="5", width="100%", max_width="920px", padding="20px",
                class_name="loading-page-content",
            ),
            _discard_dialog(),
            width="100%", min_height="100vh", background=ui.PAGE, class_name="loading-page",
        ),
        rx.center(rx.spinner(size="3"), width="100%", min_height="100vh", background=ui.PAGE),
    )


class LoadingAuthMiddleware(rx.Middleware):
    _PUBLIC_EVENTS = frozenset({"hydrate", "load_loading_page"})

    async def preprocess(self, app, state, event) -> StateUpdate | None:
        prefix = f"{LoadingState.get_full_name()}."
        if not event.name.startswith(prefix):
            return None
        event_name = event.name.removeprefix(prefix)
        if event_name in self._PUBLIC_EVENTS:
            return None
        if loading_principal_for_router(event.router_data) is not None:
            return None
        return StateUpdate(
            events=Event.from_event_type(
                rx.redirect("/loader", replace=True),
                router_data=event.router_data,
            )
        )
