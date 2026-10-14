"""Warehouse loading workspace and trip reconciliation."""

from __future__ import annotations

import uuid
from datetime import datetime
from decimal import Decimal, InvalidOperation
from http.cookies import CookieError, SimpleCookie

import reflex as rx
from reflex.state import StateUpdate
from reflex_base.event import Event

from modules import dashboard_sessions, driver_orders, goods_returns, loader_sessions
from modules.fleet import loader_by_id
from modules.order_records import (
    OrderRecordConflict,
    OrderRecordError,
    OrderRecordNotFound,
    ZERO_REASON_OPTIONS,
    calculate_net_weight,
    confirm_route_loading,
    confirm_store_loading,
    loading_line_net_weight,
    loading_batches,
    loading_measurement_parts,
    loading_measurement_totals,
    change_loading_weighing,
    loading_mode_locked,
    route_loading_mode,
    save_store_loading_draft,
    set_route_loading_mode,
    store_loading_available,
    list_order_record_summaries,
    load_order_record,
    is_zero_measurement,
    loading_route_summaries,
    logistics_summary,
    route_loading_ready,
    save_loading_draft,
)
from orders_dashboard import theme as ui


LOADING_SORT_OPTIONS = {
    "source": "Как в заказе",
    "name_asc": "Название: А–Я",
    "name_desc": "Название: Я–А",
    "weight_desc": "Заказанный вес: по убыванию",
    "weight_asc": "Заказанный вес: по возрастанию",
}


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
        "vehicle_id": str(session.get("vehicle_id", "")),
    }


def _query_param(router, name: str) -> str:
    url = getattr(router, "url", None)
    params = getattr(url, "query_parameters", None)
    if params is None and isinstance(router, dict):
        url = router.get("url", {})
        params = url.get("query_parameters") if isinstance(url, dict) else None
        params = params if params is not None else router.get("params", {})
    if not hasattr(params, "get"):
        return ""
    value = params.get(name, "")
    return str(value[0] if isinstance(value, list) and value else value)


def _format_date(value: str) -> str:
    try:
        return datetime.fromisoformat(value).strftime("%d.%m.%y %H:%M")
    except ValueError:
        return value


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


def _measurement(measurement: object) -> dict:
    measurement = measurement if isinstance(measurement, dict) else {}
    result = {key: str(measurement.get(key, "")) for key in (
        "box_count", "tare_weight_per_box_kg", "gross_weight_kg", "net_weight_kg", "zero_reason",
    )}
    if "weighings" in measurement:
        result["weighings"] = [{**_measurement(part), "id": part["id"]} for part in loading_measurement_parts(measurement)]
    return result


def _weighing_rows(measurement: dict, context: dict) -> list[dict]:
    parts = loading_measurement_parts(measurement)
    return [{**context, **part, "weighing_id": str(part.get("id", "")) if "weighings" in measurement else "", "id": context["id"],
             "label": f"Взвешивание {index + 1}", "can_remove": len(parts) > 1,
             "preview_net_weight_kg": _preview_net(part), "needs_zero_reason": is_zero_measurement(part)}
            for index, part in enumerate(parts)]


def _decorate_loading_rows(rows: list[dict]) -> list[dict]:
    for row in rows:
        row["partial_net_weight_kg"] = loading_measurement_totals(row)["partial_net_weight_kg"]
        row["weighings"] = _weighing_rows(row.copy(), {key: row[key] for key in ("id", "order_id", "route_key", "destination_id", "name")})
    return rows


def _preview_net(measurement: dict[str, str]) -> str:
    if "weighings" in measurement:
        return loading_measurement_totals(measurement)["net_weight_kg"]
    if any(measurement[key].strip() == "" for key in ("box_count", "tare_weight_per_box_kg", "gross_weight_kg")):
        return ""
    try:
        return _format_number(
            calculate_net_weight(
                measurement["gross_weight_kg"],
                measurement["tare_weight_per_box_kg"],
                measurement["box_count"],
            )
        )
    except (OrderRecordError, InvalidOperation, ValueError):
        return ""


def _loading_rows(
    record: dict,
    route_key: str,
    measurements: dict[str, dict[str, str]],
) -> list[dict]:
    rows = []
    for line in record.get("loading_lines", []):
        if str(line.get("route_key", "")) != route_key:
            continue
        line_id = str(line.get("id", ""))
        measurement = _measurement(measurements.get(line_id, line.get("measurement")))
        rows.append(
            {
                "id": line_id,
                "order_id": str(record["id"]),
                "route_key": route_key,
                "destination_id": "",
                "name": str(line.get("name", "")),
                "planned_kg": str(line.get("planned_amount", "0")),
                **measurement,
                "needs_zero_reason": is_zero_measurement(measurement),
                "preview_net_weight_kg": _preview_net(measurement),
            }
        )
    return _decorate_loading_rows(rows)


def _store_loading_rows(record: dict, route_key: str, destination: dict) -> list[dict]:
    rows = []
    for position in destination.get("positions", []):
        measurement = _measurement((position.get("loading") or {}).get("measurement"))
        shipment = position.get("shipment") or {}
        shipped = str((shipment.get("measurement") or {}).get("net_weight_kg", "")) if shipment.get("status") == "completed" else ""
        rows.append({
            "id": str(position["id"]), "order_id": str(record["id"]),
            "route_key": route_key, "destination_id": str(destination["id"]),
            "name": str(position.get("name", "")), "planned_kg": str(position.get("planned_amount", "0")),
            **measurement, "needs_zero_reason": is_zero_measurement(measurement),
            "preview_net_weight_kg": _preview_net(measurement), "shipped_net_kg": shipped,
        })
    return _decorate_loading_rows(rows)


def _store_loading_cards(record: dict, route_key: str) -> list[dict]:
    cards = []
    batches = loading_batches(record, route_key)
    published = {batch["id"]: driver_orders.loading_batch_published(batch) for batch in batches}
    released = {identity: (index + 1, published[batch["id"]])
                for index, batch in enumerate(batches) for identity in batch["destination_ids"]}
    for route in record.get("routes", []):
        if route.get("route_key") != route_key:
            continue
        for destination in route.get("destinations", []):
            rows = _store_loading_rows(record, route_key, destination)
            ordered, loaded = _loading_totals(rows)
            status = str((destination.get("loading") or {}).get("status", "new"))
            cards.append({
                "id": str(destination["id"]), "name": str(destination.get("name", "")),
                "planned_kg": ordered, "loaded_net_kg": loaded if status == "loaded" else "",
                "released": destination["id"] in released,
                "status": status, "status_label": (f"Отправлена №{released[destination['id']][0]}" if released[destination["id"]][1] else "Подтверждена, ожидает публикации") if destination["id"] in released else {"new": "Ожидает загрузки", "draft": "Черновик", "loaded": "Подтверждена, ожидает отправки"}.get(status, "Ожидает загрузки"),
            })
    return cards


def _sort_loading_rows(rows: list[dict], sort_order: str) -> list[dict]:
    def name_key(row: dict) -> str:
        return str(row.get("name", "")).strip().casefold().replace("ё", "е")

    if sort_order in ("name_asc", "name_desc"):
        return sorted(rows, key=name_key, reverse=sort_order == "name_desc")
    if sort_order in ("weight_asc", "weight_desc"):
        def weight_key(row: dict) -> tuple[bool, Decimal, str]:
            try:
                weight = Decimal(str(row.get("planned_kg", "")).strip().replace(",", "."))
            except InvalidOperation:
                return True, Decimal(0), name_key(row)
            if not weight.is_finite():
                return True, Decimal(0), name_key(row)
            return False, -weight if sort_order == "weight_desc" else weight, name_key(row)

        return sorted(rows, key=weight_key)
    return list(rows)


def _loading_totals(rows: list[dict]) -> tuple[str, str]:
    ordered = Decimal("0")
    loaded = Decimal("0")
    has_missing = False
    for row in rows:
        try:
            ordered += Decimal(row["planned_kg"] or "0")
            preview = row["preview_net_weight_kg"]
            if preview == "":
                has_missing = True
            else:
                loaded += Decimal(preview)
        except (InvalidOperation, ValueError):
            has_missing = True
    return _format_number(ordered), "" if has_missing else _format_number(loaded)


def _shipment_rows(record: dict) -> tuple[list[dict], int, int]:
    rows = []
    completed_count = 0
    total_count = 0
    for route in record.get("routes", []):
        for destination in route.get("destinations", []):
            total_count += 1
            positions = destination.get("positions", [])
            completed = bool(positions) and all(
                (position.get("shipment") or {}).get("status") == "completed"
                for position in positions
            )
            completed_count += int(completed)
            rows.append(
                {
                    "route": str(route.get("route_label", "")),
                    "store": str(destination.get("name", "")),
                    "status": "Отгружено" if completed else "Ожидает водителя",
                    "completed": completed,
                }
            )
    return rows, completed_count, total_count


def _return_reconciliation(record: dict) -> dict:
    summary = logistics_summary(record)
    accepted = goods_returns.accepted_by_loading_line(str(record["id"]))
    totals = {"returned": Decimal(0), "unexplained": Decimal(0), "excess": Decimal(0)}
    by_product = {}
    for line in record.get("loading_lines", []):
        key = (str(line.get("name", "")).strip().casefold(), str(line.get("unit", "kg")).strip().casefold())
        values = by_product.setdefault(key, {"returned": Decimal(0), "unexplained": Decimal(0), "excess": Decimal(0)})
        returned = Decimal(accepted.get(str(line["id"]), "0"))
        loaded = loading_line_net_weight(record, line)
        shipped = sum((
            Decimal((position["shipment"].get("measurement") or {}).get("net_weight_kg") or "0")
            for route in record.get("routes", [])
            for destination in route.get("destinations", [])
            for position in destination.get("positions", [])
            if position.get("loading_line_id") == line["id"]
            and (position.get("shipment") or {}).get("status") == "completed"
        ), Decimal(0))
        balance = loaded - shipped - returned
        values["returned"] += returned
        values["unexplained"] += max(balance, Decimal(0))
        values["excess"] += max(-balance, Decimal(0))
    for row in summary["items"]:
        source = next(line for line in record["loading_lines"] if str(line["id"]) == row["id"])
        key = (str(source.get("name", "")).strip().casefold(), str(source.get("unit", "kg")).strip().casefold())
        values = by_product[key]
        for field, amount in values.items():
            row[f"{field}_kg"] = _format_number(amount)
            totals[field] += amount
    for field, amount in totals.items():
        summary[f"total_{field}_kg"] = _format_number(amount)
    return summary


class LoadingState(rx.State):
    is_authorized: bool = False
    principal: dict = {}
    order_options: list[dict] = []
    order_option_labels: list[str] = []
    selected_order_label: str = ""
    selected_order_id: str = ""
    route_options: list[dict] = []
    route_option_labels: list[str] = []
    selected_route_label: str = ""
    selected_route_key: str = ""
    route_loaded_count: int = 0
    route_total_count: int = 0
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
    total_loaded_net_kg: str = ""
    loading_rows: list[dict] = []
    loading_sort: str = "source"
    draft_measurements: dict[str, dict[str, str]] = {}
    shipment_rows: list[dict] = []
    shipment_completed_count: int = 0
    shipment_total_count: int = 0
    shipment_status: str = "waiting_loading"
    reconciliation_rows: list[dict] = []
    reconciliation: dict = {}
    summary_expanded: bool = False
    is_read_only: bool = False
    status: str = ""
    order_not_found: bool = False
    save_completed: bool = False
    loading_mode: str = "route"
    mode_locked: bool = False
    stores_available: bool = False
    store_cards: list[dict] = []
    store_search: str = ""
    selected_store_id: str = ""
    selected_store_name: str = ""
    store_confirmed_count: int = 0
    store_confirmed_net_kg: str = "0"
    route_is_ready: bool = False
    _last_weighing_request: str = ""
    partial_has_batches: bool = False
    partial_send_stores: list[dict] = []
    partial_send_net_kg: str = "0"
    partial_waiting_count: int = 0
    partial_blocker: str = ""
    partial_pending_publication: bool = False
    partial_dialog_open: bool = False
    partial_dialog_names: list[str] = []
    partial_dialog_net_kg: str = "0"
    partial_dialog_waiting_count: int = 0
    partial_dialog_error: str = ""
    _partial_revision: int = 0
    _partial_operation_id: str = ""
    _partial_order_id: str = ""
    _partial_route_key: str = ""

    @rx.var
    def sorted_loading_rows(self) -> list[dict]:
        return _sort_loading_rows(self.loading_rows, self.loading_sort)

    def set_loading_sort(self, value: str):
        if value in LOADING_SORT_OPTIONS:
            self.loading_sort = value

    @rx.var
    def filtered_store_cards(self) -> list[dict]:
        query = self.store_search.strip().casefold()
        return [item for item in self.store_cards if not query or query in item["name"].casefold()]

    def set_store_search(self, value: str):
        self.store_search = value

    def select_store(self, destination_id: str):
        if destination_id not in {item["id"] for item in self.store_cards}:
            return
        self.selected_store_id = destination_id
        self._apply_record(self.selected_order_id, self.selected_route_key)

    def next_store(self):
        ids = [item["id"] for item in self.store_cards]
        if self.selected_store_id in ids and len(ids) > 1:
            self.select_store(ids[(ids.index(self.selected_store_id) + 1) % len(ids)])

    def choose_loading_mode(self, label: str):
        mode = {"Общая загрузка": "route", "По магазинам": "stores"}.get(label)
        if mode is None or not self.selected_order_id:
            return
        try:
            set_route_loading_mode(self.selected_order_id, int(self.selected_record["revision"]), self.selected_route_key, mode)
        except OrderRecordError as error:
            self._apply_record(self.selected_order_id, self.selected_route_key)
            self.status = str(error)
            return
        self._apply_record(self.selected_order_id, self.selected_route_key)

    def _patch_loading_measurement(self, record: dict, route_key: str, destination_id: str, position_id: str):
        if str(record["id"]) != self.selected_order_id:
            return
        self.selected_record = record
        if route_key != self.selected_route_key:
            return
        self.mode_locked = True
        if destination_id:
            route = next(item for item in record["routes"] if item["route_key"] == route_key)
            destination = next(item for item in route["destinations"] if item["id"] == destination_id)
            self.store_cards = [
                {**item, "status": "draft", "status_label": "Черновик"} if item["id"] == destination_id else item
                for item in self.store_cards
            ]
            if destination_id != self.selected_store_id:
                return
            position = next(item for item in destination["positions"] if item["id"] == position_id)
            measurement = _measurement((position.get("loading") or {}).get("measurement"))
        else:
            line = next(item for item in record["loading_lines"] if item["id"] == position_id)
            measurement = _measurement(line.get("measurement"))
            self.draft_measurements = {**self.draft_measurements, position_id: measurement}
        # Keep numeric value props unchanged: a delayed ACK must not reset newer local typing.
        self.loading_rows = [
            {
                **row, "preview_net_weight_kg": _preview_net(measurement),
                "partial_net_weight_kg": loading_measurement_totals(measurement)["partial_net_weight_kg"],
                "weighings": [
                    {**old, "preview_net_weight_kg": fresh["preview_net_weight_kg"],
                     "needs_zero_reason": fresh["needs_zero_reason"], "zero_reason": fresh["zero_reason"]}
                    for old, fresh in zip(row["weighings"], _weighing_rows(measurement, row))
                ],
                "needs_zero_reason": is_zero_measurement(measurement), "zero_reason": measurement["zero_reason"],
            } if row["id"] == position_id else row
            for row in self.loading_rows
        ]
        self.total_ordered_kg, self.total_loaded_net_kg = _loading_totals(self.loading_rows)

    def set_context_measurement_field(self, order_id: str, route_key: str, destination_id: str, position_id: str, field: str, value: str, weighing_id: str = ""):
        try:
            if destination_id:
                record = save_store_loading_draft(order_id, route_key, destination_id, position_id, field, value, self.principal, weighing_id)
            else:
                record = save_loading_draft(order_id, route_key, position_id, field, value, self.principal, weighing_id)
        except OrderRecordError as error:
            self._apply_record(self.selected_order_id, self.selected_route_key)
            self.status = str(error)
            return
        self._patch_loading_measurement(record, route_key, destination_id, position_id)
        self.status = "Черновик сохранён"

    def change_context_weighing(self, order_id: str, route_key: str, destination_id: str,
                                position_id: str, revision: int, remove_id: str):
        request = repr((order_id, route_key, destination_id, position_id, revision, remove_id))
        if request == self._last_weighing_request:
            return
        if order_id != self.selected_order_id or route_key != self.selected_route_key:
            return
        # Blur saves queued before the click may advance the form revision.
        # Use the acknowledged revision, while deduplicating the captured click.
        try:
            change_loading_weighing(order_id, int(self.selected_record["revision"]), route_key, destination_id,
                                   position_id, self.principal, remove_id or None)
        except OrderRecordError as error:
            self.status = str(error)
            return
        self._last_weighing_request = request
        self._apply_record(self.selected_order_id, self.selected_route_key)
        self.status = "Взвешивание удалено" if remove_id else "Взвешивание добавлено"

    def confirm_selected_store(self):
        if not self.selected_store_id or self.is_read_only:
            return
        try:
            confirm_store_loading(self.selected_order_id, int(self.selected_record["revision"]), self.selected_route_key, self.selected_store_id, self.principal)
        except OrderRecordError as error:
            self._apply_record(self.selected_order_id, self.selected_route_key)
            self.status = str(error)
            return
        self._apply_record(self.selected_order_id, self.selected_route_key)
        self.status = "Загрузка маршрута подтверждена. Водитель может начать отгрузку." if self.route_is_ready else "Загрузка магазина подтверждена. Выберите любой следующий магазин."
        if self.partial_has_batches:
            self.status = "Загрузка магазина подтверждена. Отправьте следующую загрузку после завершения предыдущей отправки."
        self.save_completed = self.route_is_ready and not self.partial_has_batches
        self._refresh_options()

    def prepare_partial_loading(self):
        if not self.partial_send_stores or self.partial_blocker:
            return
        self._partial_revision = int(self.selected_record["revision"])
        self._partial_order_id = self.selected_order_id
        self._partial_route_key = self.selected_route_key
        self._partial_operation_id = uuid.uuid4().hex
        self.partial_dialog_names = [store["name"] for store in self.partial_send_stores]
        self.partial_dialog_net_kg = self.partial_send_net_kg
        self.partial_dialog_waiting_count = self.partial_waiting_count
        self.partial_dialog_error = ""
        self.partial_dialog_open = True

    def set_partial_dialog_open(self, value: bool):
        self.partial_dialog_open = value

    def finish_partial_loading(self):
        if not self.partial_dialog_open or not self._partial_operation_id:
            return
        if self.selected_order_id != self._partial_order_id or self.selected_route_key != self._partial_route_key:
            self.partial_dialog_open = False
            self.status = "Заказ или маршрут изменился. Выберите магазины заново."
            return
        try:
            snapshot = driver_orders.release_partial_loading(
                self._partial_order_id, self._partial_route_key, self._partial_revision,
                self.principal, self._partial_operation_id,
            )
        except (driver_orders.DriverOrderError, OrderRecordError) as error:
            self._apply_record(self.selected_order_id, self.selected_route_key)
            self.partial_dialog_error = str(error)
            return
        self.partial_dialog_open = False
        self._partial_operation_id = ""
        self._apply_record(self.selected_order_id, self.selected_route_key)
        self.status = f"Отправка №{snapshot['batch_number']} опубликована: {len(snapshot['stores'])} магазинов. Остальные магазины можно загрузить позже."

    def _refresh_options(self):
        self.order_options = [
            {
                **item,
                "label": f"{item['order_number']} · {item['client_name']} · {_format_date(item['processed_at'])}",
            }
            for item in list_order_record_summaries()
        ]
        self.order_option_labels = [item["label"] for item in self.order_options]

    def _clear_record(self):
        self.selected_order_id = ""
        self.selected_order_label = ""
        self.route_options = []
        self.route_option_labels = []
        self.selected_route_label = ""
        self.selected_route_key = ""
        self.route_loaded_count = 0
        self.route_total_count = 0
        self.selected_record = {}
        self.summary_order_number = ""
        self.summary_client_name = ""
        self.summary_processed_at = ""
        self.summary_mode = ""
        self.summary_routes = ""
        self.summary_received_at = ""
        self.summary_position_count = 0
        self.total_ordered_kg = "0"
        self.total_loaded_net_kg = ""
        self.loading_rows = []
        self.draft_measurements = {}
        self.shipment_rows = []
        self.shipment_completed_count = 0
        self.shipment_total_count = 0
        self.shipment_status = "waiting_loading"
        self.reconciliation_rows = []
        self.reconciliation = {}
        self.is_read_only = False
        self.loading_mode = "route"
        self.mode_locked = False
        self.stores_available = False
        self.store_cards = []
        self.store_search = ""
        self.selected_store_id = ""
        self.selected_store_name = ""
        self.store_confirmed_count = 0
        self.store_confirmed_net_kg = "0"
        self.route_is_ready = False
        self.partial_has_batches = False
        self.partial_send_stores = []
        self.partial_send_net_kg = "0"
        self.partial_waiting_count = 0
        self.partial_blocker = ""
        self.partial_pending_publication = False
        self.partial_dialog_open = False
        self._partial_operation_id = ""
        self._partial_order_id = ""
        self._partial_route_key = ""

    def _apply_record(self, order_record_id: str, route_key: str = "") -> bool:
        if not order_record_id:
            self._clear_record()
            return True
        try:
            record = load_order_record(order_record_id)
        except OrderRecordNotFound:
            self._clear_record()
            self.order_not_found = True
            self.status = "Заказ не найден"
            return False

        route_options = loading_route_summaries(record)
        if not route_options:
            route_options = [{
                "route_key": "",
                "route_label": "Все маршруты",
                "status": str((record.get("loading") or {}).get("status", "new")),
                "ready": bool(logistics_summary(record)["loading_ready"]),
            }]
        selected_route_key = route_key or self.selected_route_key
        if selected_route_key not in {item["route_key"] for item in route_options}:
            selected_route_key = route_options[0]["route_key"]
        selected_route = next(item for item in route_options if item["route_key"] == selected_route_key)

        if self.selected_order_id != order_record_id or self.selected_route_key != selected_route_key:
            self.selected_store_id = ""
            self.store_search = ""
            self.partial_dialog_open = False
            self._partial_operation_id = ""
            self._partial_order_id = ""
            self._partial_route_key = ""
        self.selected_order_id = order_record_id
        self.selected_order_label = next(
            (item["label"] for item in self.order_options if item["id"] == order_record_id),
            "",
        )
        self.route_options = [
            {**item, "label": item["route_label"]}
            for item in route_options
        ]
        self.route_option_labels = [item["label"] for item in self.route_options]
        self.selected_route_key = selected_route_key
        self.selected_route_label = str(selected_route["route_label"])
        self.route_total_count = len(route_options)
        self.route_loaded_count = sum(item["status"] == "loaded" for item in route_options)
        self.selected_record = record
        self.summary_order_number = str(record.get("order_number", ""))
        self.summary_client_name = str(record.get("client_name", ""))
        self.summary_processed_at = _format_date(str(record.get("processed_at", "")))
        self.summary_mode = str(record.get("mode", ""))
        self.summary_routes = _route_summary(record)
        self.summary_received_at = str((record.get("mail_metadata") or {}).get("received_display", ""))
        self.draft_measurements = {
            str(line["id"]): _measurement(line.get("measurement"))
            for line in record.get("loading_lines", [])
            if str(line.get("route_key", "")) == selected_route_key
        }
        self.loading_mode = route_loading_mode(record, selected_route_key)
        self.mode_locked = loading_mode_locked(record, selected_route_key)
        self.stores_available = store_loading_available(record, selected_route_key)
        self.store_cards = _store_loading_cards(record, selected_route_key) if self.loading_mode == "stores" else []
        self.store_confirmed_count = sum(item["status"] == "loaded" for item in self.store_cards)
        self.store_confirmed_net_kg = _format_number(sum((Decimal(item["loaded_net_kg"] or "0") for item in self.store_cards), Decimal(0)))
        batches = loading_batches(record, selected_route_key)
        self.partial_has_batches = bool(batches)
        self.partial_pending_publication = bool(batches and not driver_orders.loading_batch_published(batches[-1]))
        if self.partial_pending_publication:
            self.partial_send_stores = [store for store in self.store_cards if store["id"] in batches[-1]["destination_ids"]]
        else:
            self.partial_send_stores = [store for store in self.store_cards if store["status"] == "loaded" and not store["released"]]
        if not batches and selected_route["ready"]:
            self.partial_send_stores = []
        self.partial_send_net_kg = _format_number(sum((Decimal(store["loaded_net_kg"] or "0") for store in self.partial_send_stores), Decimal(0)))
        self.partial_waiting_count = sum(not store["released"] and store not in self.partial_send_stores for store in self.store_cards)
        self.partial_blocker = driver_orders.partial_loading_blocker(order_record_id, selected_route_key) if self.partial_send_stores and not self.partial_pending_publication else ""
        self.selected_store_name = ""
        self.loading_rows = _loading_rows(record, selected_route_key, self.draft_measurements)
        if self.store_cards:
            if self.selected_store_id not in {item["id"] for item in self.store_cards}:
                self.selected_store_id = self.store_cards[0]["id"]
            route = next(item for item in record["routes"] if item["route_key"] == selected_route_key)
            destination = next(item for item in route["destinations"] if item["id"] == self.selected_store_id)
            self.selected_store_name = str(destination.get("name", ""))
            self.loading_rows = _store_loading_rows(record, selected_route_key, destination)
        self.summary_position_count = len(self.loading_rows)
        self.total_ordered_kg, self.total_loaded_net_kg = _loading_totals(self.loading_rows)
        self.reconciliation = _return_reconciliation(record)
        self.reconciliation_rows = self.reconciliation["items"]
        self.shipment_status = self.reconciliation["shipment_status"]
        self.shipment_rows, self.shipment_completed_count, self.shipment_total_count = _shipment_rows(record)
        self.route_is_ready = bool(selected_route["ready"])
        self.is_read_only = self.route_is_ready or any(item["id"] == self.selected_store_id and item["status"] == "loaded" for item in self.store_cards)
        self.order_not_found = False
        self.save_completed = False
        self.status = ""
        return True

    def load_loading_page(self):
        principal = loading_principal_for_router(self.router)
        if principal is None:
            return rx.call_script("window.location.replace('/loader/')")
        self.is_authorized = True
        self.principal = principal
        self.back_target = "/?page=history" if _query_param(self.router, "from") == "history" else "/"
        self._refresh_options()
        self._apply_record(
            _query_param(self.router, "order"),
            _query_param(self.router, "route"),
        )

    def request_order_label(self, label: str):
        order_record_id = next(
            (item["id"] for item in self.order_options if item["label"] == label),
            "",
        )
        return self.request_order(order_record_id)

    def request_order(self, order_record_id: str):
        if order_record_id == self.selected_order_id:
            return
        return self.select_order(order_record_id)

    def select_order(self, order_record_id: str):
        self._apply_record(order_record_id, "")
        return rx.redirect(f"/loading?order={order_record_id}" if order_record_id else "/loading")

    def request_route_label(self, label: str):
        route_key = next(
            (item["route_key"] for item in self.route_options if item["label"] == label),
            "",
        )
        return self.select_route(route_key)

    def select_route(self, route_key: str):
        if not self.selected_order_id or route_key == self.selected_route_key:
            return
        self._apply_record(self.selected_order_id, route_key)
        history_param = "&from=history" if self.back_target == "/?page=history" else ""
        return rx.redirect(
            f"/loading?order={self.selected_order_id}&route={route_key}{history_param}"
        )

    def set_measurement_field(self, line_id: str, field: str, value: str):
        if self.is_read_only or line_id not in self.draft_measurements:
            return
        try:
            record = save_loading_draft(
                self.selected_order_id,
                self.selected_route_key,
                line_id,
                field,
                value,
                self.principal,
            )
        except OrderRecordConflict as error:
            self._apply_record(self.selected_order_id, self.selected_route_key)
            self.status = str(error)
            return
        except OrderRecordError as error:
            self.status = str(error)
            return
        self.selected_record = record
        self._apply_record(self.selected_order_id, self.selected_route_key)
        self.status = "Черновик сохранён"
        self.save_completed = False

    def toggle_summary(self):
        self.summary_expanded = not self.summary_expanded

    def refresh_trip(self):
        if not self.selected_order_id:
            return
        self._refresh_options()
        self._apply_record(self.selected_order_id)
        self.status = "Данные рейса обновлены"

    def save_loading(self):
        if not self.selected_order_id:
            self.status = "Выберите заказ"
            return
        if self.is_read_only:
            self.status = "Загрузка маршрута уже подтверждена"
            return
        try:
            record = confirm_route_loading(
                self.selected_order_id,
                int(self.selected_record.get("revision", -1)),
                self.selected_route_key,
                self.principal,
            )
        except OrderRecordConflict as error:
            self._apply_record(self.selected_order_id, self.selected_route_key)
            self.status = str(error)
            return
        except OrderRecordError as error:
            self.status = str(error)
            return
        self.selected_record = record
        self._apply_record(self.selected_order_id, self.selected_route_key)
        self.save_completed = True
        self.status = "Загрузка маршрута подтверждена. Водитель может начать отгрузку."
        self._refresh_options()

    def load_next_order(self):
        for item in self.order_options:
            if item["id"] != self.selected_order_id and item["status"] != "loaded":
                return self.select_order(item["id"])
        self.status = "Следующих заказов для загрузки нет"

    def back_to_orders(self):
        return rx.redirect(self.back_target)


def _loading_summary():
    return rx.vstack(
        rx.button(
            rx.hstack(
                rx.vstack(
                    rx.text(LoadingState.summary_order_number, class_name="loading-summary-title"),
                    rx.text(LoadingState.summary_client_name, class_name="loading-summary-client"),
                    align="start", spacing="1",
                ),
                rx.spacer(),
                rx.text(rx.cond(LoadingState.summary_expanded, "Свернуть", "Подробнее"), class_name="loading-summary-toggle"),
                width="100%", align="center",
            ),
            aria_expanded=LoadingState.summary_expanded, aria_controls="loading-order-summary",
            on_click=LoadingState.toggle_summary,
            width="100%", padding="0", background=ui.TRANSPARENT, border="0", cursor="pointer",
        ),
        rx.cond(
            LoadingState.summary_expanded,
            rx.vstack(
                rx.text("Обработан: ", LoadingState.summary_processed_at, class_name="loading-summary-meta"),
                rx.text("Режим: ", LoadingState.summary_mode, class_name="loading-summary-meta"),
                rx.text("Маршруты: ", LoadingState.summary_routes, class_name="loading-summary-meta"),
                rx.text("Письмо: ", LoadingState.summary_received_at, class_name="loading-summary-meta"),
                rx.text("Позиций: ", LoadingState.summary_position_count, class_name="loading-summary-meta"),
                id="loading-order-summary", align="start", spacing="1", width="100%",
            ),
            rx.box(display="none"),
        ),
        align="start", spacing="3", width="100%", class_name="loading-summary",
    )


def _loading_context():
    return rx.vstack(
        rx.hstack(
            rx.vstack(
                rx.heading("Параметры рейса", size="3"),
                rx.text("Выберите заказ и маршрут для загрузки", class_name="loading-panel-description"),
                align="start", spacing="1",
            ),
            rx.cond(
                LoadingState.selected_order_id != "",
                rx.text(
                    LoadingState.route_loaded_count,
                    " из ",
                    LoadingState.route_total_count,
                    class_name="loading-count",
                ),
                rx.box(),
            ),
            class_name="loading-panel-heading",
            width="100%",
            align="start",
        ),
        rx.vstack(
            rx.text("Заказ", class_name="loading-field-label"),
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
        rx.cond(
            LoadingState.selected_order_id != "",
            rx.vstack(
                rx.text("Маршрут", class_name="loading-field-label"),
                rx.select(
                    LoadingState.route_option_labels,
                    value=LoadingState.selected_route_label,
                    on_change=LoadingState.request_route_label,
                    width="100%",
                    class_name="loading-select",
                ),
                rx.text(
                    "Подтверждено маршрутов: ",
                    LoadingState.route_loaded_count,
                    " из ",
                    LoadingState.route_total_count,
                    class_name="loading-route-progress",
                ),
                align="start", spacing="1", width="100%",
            ),
            rx.box(),
        ),
        rx.cond(LoadingState.order_not_found, rx.text("Заказ не найден", class_name="loading-message loading-message-error"), rx.box()),
        rx.cond(LoadingState.selected_order_id != "", _loading_summary(), rx.box()),
        align="start", spacing="4", width="100%",
        class_name="loading-panel loading-context-panel",
    )


def _measurement_control(row, field: str, label: str):
    return rx.el.label(
        rx.text(label, class_name="loading-mobile-label"),
        rx.debounce_input(
            rx.el.input(
                value=row[field],
                on_change=lambda value: LoadingState.set_context_measurement_field(row["order_id"], row["route_key"], row["destination_id"], row["id"], field, value, row["weighing_id"]),
                type="text", input_mode="numeric" if field == "box_count" else "decimal",
                disabled=LoadingState.is_read_only, aria_label=row["name"].to(str) + ": " + label,
                class_name="loading-amount-input",
                key=row["order_id"].to(str) + ":" + row["route_key"].to(str) + ":" + row["destination_id"].to(str) + ":" + row["id"].to(str) + ":" + row["weighing_id"].to(str) + ":" + field,
            ),
            debounce_timeout=350, force_notify_on_blur=True, force_notify_by_enter=True,
        ),
        class_name="loading-measurement-control",
    )


def _weighing_controls(part):
    return rx.vstack(
        rx.hstack(
            rx.text(part["label"], class_name="loading-weighing-label"),
            _measurement_control(part, "box_count", "Ящики"),
            _measurement_control(part, "tare_weight_per_box_kg", "Тара, кг/ящик"),
            _measurement_control(part, "gross_weight_kg", "Брутто, кг"),
            rx.text("Нетто: ", part["preview_net_weight_kg"], rx.cond(part["preview_net_weight_kg"] != "", " кг", "—")),
            rx.cond(
                part["can_remove"].to(bool) & ~LoadingState.is_read_only,
                rx.alert_dialog.root(
                    rx.alert_dialog.trigger(rx.button("Удалить", variant="ghost", color_scheme="red")),
                    rx.alert_dialog.content(
                        rx.alert_dialog.title("Удалить взвешивание?"),
                        rx.alert_dialog.description("Вес этой порции будет исключён из итога товара."),
                        rx.hstack(
                            rx.alert_dialog.cancel(rx.button("Отмена", variant="soft")),
                            rx.alert_dialog.action(rx.button("Удалить взвешивание", color_scheme="red", on_click=LoadingState.change_context_weighing(
                                part["order_id"], part["route_key"], part["destination_id"], part["id"], LoadingState.selected_record["revision"].to(int), part["weighing_id"]))),
                            justify="end", margin_top="16px",
                        ),
                    ),
                ), rx.box(),
            ),
            class_name="loading-weighing-fields", width="100%", align="center",
        ),
        rx.cond(
            part["needs_zero_reason"],
            rx.hstack(
                rx.text("Причина нулевой позиции"),
                rx.cond(LoadingState.is_read_only, rx.text(part["zero_reason"]), rx.select(
                    list(ZERO_REASON_OPTIONS), value=part["zero_reason"],
                    on_change=lambda value: LoadingState.set_context_measurement_field(part["order_id"], part["route_key"], part["destination_id"], part["id"], "zero_reason", value, part["weighing_id"]),
                    placeholder="Укажите причину",
                )), wrap="wrap",
            ), rx.box(),
        ),
        class_name="loading-weighing", width="100%", align="start", key=part["weighing_id"].to(str),
    )


def _loading_table():
    return rx.vstack(
        rx.heading("Загрузка", size="3"),
        rx.text(rx.cond(LoadingState.loading_mode == "stores", "Магазин: " + LoadingState.selected_store_name, "Фактические веса маршрута «" + LoadingState.selected_route_label + "»"), class_name="loading-panel-description"),
        rx.hstack(
            rx.el.label("Сортировка товаров", html_for="loading-product-sort"),
            rx.el.select(
                *[rx.el.option(label, value=value) for value, label in LOADING_SORT_OPTIONS.items()],
                id="loading-product-sort", value=LoadingState.loading_sort,
                on_change=LoadingState.set_loading_sort,
                aria_label="Сортировка товаров в загрузке", class_name="loading-store-mode",
            ),
            width="100%", wrap="wrap", align="center", spacing="3",
        ),
        rx.foreach(LoadingState.sorted_loading_rows, lambda row: rx.vstack(
            rx.hstack(
                rx.text(row["name"], class_name="loading-product-name"), rx.spacer(),
                rx.text("Заказано: ", row["planned_kg"], " кг"), wrap="wrap", width="100%",
            ),
            rx.foreach(row["weighings"].to(list[dict]), _weighing_controls),
            rx.hstack(
                rx.cond(~LoadingState.is_read_only, rx.button("+ Добавить взвешивание", variant="soft", on_click=LoadingState.change_context_weighing(
                    row["order_id"], row["route_key"], row["destination_id"], row["id"], LoadingState.selected_record["revision"].to(int), "")), rx.box()),
                rx.spacer(),
                rx.text("Итого нетто: ", row["preview_net_weight_kg"], rx.cond(row["preview_net_weight_kg"] != "", " кг", "не все взвешивания заполнены"), class_name="loading-net-weight"),
                width="100%", wrap="wrap", align="center",
            ),
            rx.cond(row["preview_net_weight_kg"] == "", rx.text(
                "По заполненным взвешиваниям: ", row["partial_net_weight_kg"], " кг. Черновик — заполните остальные порции.",
                class_name="loading-panel-description"), rx.box()),
            class_name="loading-weighing-product", width="100%", align="start", spacing="3", key=row["id"].to(str),
        )),
        rx.hstack(rx.text("Итого заказано: ", LoadingState.total_ordered_kg, " кг"), rx.text("Загружено нетто: ", LoadingState.total_loaded_net_kg, " кг"), class_name="loading-table-total", wrap="wrap"),
        width="100%", spacing="3",
    )


def _shipment_progress():
    return rx.vstack(
        rx.hstack(
            rx.vstack(
                rx.heading("Отгрузка по магазинам", size="3"),
                rx.text(
                    LoadingState.shipment_completed_count,
                    " из ",
                    LoadingState.shipment_total_count,
                    " магазинов подтверждено водителями",
                    class_name="loading-panel-description",
                ),
                align="start", spacing="1",
            ),
            rx.spacer(),
            rx.button("Обновить", on_click=LoadingState.refresh_trip, class_name="loading-secondary"),
            width="100%", align="center",
        ),
        rx.foreach(
            LoadingState.shipment_rows,
            lambda row: rx.hstack(
                rx.text(row["route"], class_name="loading-shipment-route"),
                rx.text(row["store"], class_name="loading-shipment-store", width="100%"),
                rx.text(row["status"], class_name=rx.cond(row["completed"], "loading-shipment-status loading-shipment-status-complete", "loading-shipment-status")),
                width="100%", align="center", class_name="loading-shipment-row",
            ),
        ),
        width="100%", spacing="2", class_name="loading-panel loading-shipment-progress",
    )


def _reconciliation():
    return rx.vstack(
        rx.hstack(
            rx.vstack(
                rx.heading("Итог рейса", size="3"),
                rx.text("Сверка заказа, загрузки и отгрузки", class_name="loading-panel-description"),
                align="start", spacing="1",
            ),
            class_name="loading-panel-heading",
            width="100%",
        ),
        rx.hstack(
            rx.text("Заказано: ", LoadingState.reconciliation["total_ordered_kg"], " кг", class_name="loading-reconciliation-stat"),
            rx.text("Загружено: ", LoadingState.reconciliation["total_loaded_net_kg"], " кг", class_name="loading-reconciliation-stat"),
            rx.text("Отгружено: ", LoadingState.reconciliation["total_shipped_net_kg"], " кг", class_name="loading-reconciliation-stat"),
            rx.text("Недостача заказа: ", LoadingState.reconciliation["total_shortage_kg"], " кг", class_name="loading-reconciliation-stat loading-shortage-stat"),
            rx.text("Возвращено на склад: ", LoadingState.reconciliation["total_returned_kg"], " кг", class_name="loading-reconciliation-stat"),
            rx.text("Необъяснённый остаток: ", LoadingState.reconciliation["total_unexplained_kg"], " кг", class_name="loading-reconciliation-stat"),
            rx.text("Превышение отгрузки над загрузкой: ", LoadingState.reconciliation["total_excess_kg"], " кг", class_name="loading-reconciliation-stat"),
            wrap="wrap", spacing="2", width="100%",
        ),
        rx.box(
            rx.vstack(
                rx.hstack(
                    rx.text("Товар", class_name="loading-table-title"),
                    rx.text("Заказано", class_name="loading-table-title"),
                    rx.text("Загружено", class_name="loading-table-title"),
                    rx.text("Отгружено", class_name="loading-table-title"),
                    rx.text("Недостача заказа", class_name="loading-table-title"),
                    rx.text("Возвращено", class_name="loading-table-title"),
                    rx.text("Остаток / расхождение", class_name="loading-table-title"),
                    class_name="loading-table-row loading-table-header loading-reconciliation-row",
                ),
                rx.foreach(
                    LoadingState.reconciliation_rows,
                    lambda row: rx.hstack(
                        rx.text(row["name"], class_name="loading-product-name"),
                        rx.text(row["planned_kg"], " кг", class_name="loading-table-value", custom_attrs={"data-label": "Заказано"}),
                        rx.text(row["loaded_net_kg"], " кг", class_name="loading-table-value", custom_attrs={"data-label": "Загружено"}),
                        rx.text(row["shipped_net_kg"], " кг", class_name="loading-table-value", custom_attrs={"data-label": "Отгружено"}),
                        rx.text(row["shortage_kg"], " кг", class_name="loading-table-value loading-shortage-stat", custom_attrs={"data-label": "Недостача заказа"}),
                        rx.text(row["returned_kg"], " кг", class_name="loading-table-value", custom_attrs={"data-label": "Возвращено"}),
                        rx.vstack(
                            rx.text(row["unexplained_kg"], " кг", class_name="loading-table-value", custom_attrs={"data-label": "Остаток"}),
                            rx.cond(row["excess_kg"] != "0", rx.text("Превышение: ", row["excess_kg"], " кг", class_name="loading-table-value loading-shortage-stat"), rx.box()),
                            align="end", spacing="1",
                        ),
                        class_name="loading-table-row loading-reconciliation-row",
                    ),
                ),
                width="100%", spacing="0", class_name="loading-table loading-reconciliation",
            ),
            width="100%", class_name="loading-table-wrap",
        ),
        width="100%", spacing="3", class_name="loading-panel loading-reconciliation-panel",
    )


def _loading_mode_control():
    return rx.vstack(
        rx.hstack(
            rx.text("Режим загрузки", font_weight="500"),
            rx.el.select(
                rx.el.option("Общая загрузка", value="Общая загрузка"),
                rx.el.option("По магазинам", value="По магазинам", disabled=~LoadingState.stores_available),
                value=rx.cond(LoadingState.loading_mode == "stores", "По магазинам", "Общая загрузка"),
                on_change=LoadingState.choose_loading_mode, disabled=LoadingState.mode_locked,
                aria_label="Режим загрузки", class_name="loading-store-mode",
            ),
            align="center", wrap="wrap", spacing="3", width="100%",
        ),
        rx.cond(LoadingState.mode_locked, rx.text("Режим зафиксирован: загрузка уже начата.", class_name="loading-panel-description"), rx.box()),
        rx.cond(~LoadingState.stores_available, rx.text("Для этого заказа нет точных связей товаров с магазинами. Доступна общая загрузка.", class_name="loading-panel-description"), rx.box()),
        align="start", spacing="2", width="100%",
    )


def _store_loading_tile(store):
    return rx.button(
        rx.text(store["name"], font_weight="600"),
        rx.text("Заказано: ", store["planned_kg"], " кг"),
        rx.text(store["status_label"], class_name="loading-store-status"),
        rx.cond(store["status"] == "loaded", rx.text("Загружено: ", store["loaded_net_kg"], " кг"), rx.box()),
        on_click=LoadingState.select_store(store["id"]),
        aria_pressed=LoadingState.selected_store_id == store["id"],
        class_name=rx.cond(LoadingState.selected_store_id == store["id"], "loading-store-tile is-selected", "loading-store-tile"),
    )


def _store_loading_selector():
    return rx.vstack(
        rx.hstack(
            rx.text("Подтверждено магазинов: ", LoadingState.store_confirmed_count, " из ", LoadingState.store_cards.length()),
            rx.text("Подтверждённое нетто сборки: ", LoadingState.store_confirmed_net_kg, " кг"),
            width="100%", wrap="wrap", spacing="3",
        ),
        rx.text("Выберите любой магазин. Подтвердите все магазины для полной загрузки или отправьте подтверждённые магазины частично.", class_name="loading-panel-description"),
        rx.input(value=LoadingState.store_search, on_change=LoadingState.set_store_search, placeholder="Найти магазин", aria_label="Поиск магазина для загрузки", width="100%"),
        rx.cond(
            LoadingState.filtered_store_cards.length() > 0,
            rx.box(rx.foreach(LoadingState.filtered_store_cards, _store_loading_tile), class_name="loading-store-grid"),
            rx.text("Магазины по запросу не найдены. Измените поиск; выбранный магазин остаётся открытым."),
        ),
        width="100%", align="start", spacing="3",
    )


def _partial_loading_control():
    return rx.vstack(
        rx.cond(
            LoadingState.partial_has_batches,
            rx.text("Маршрут отправляется частями. Неотправленные магазины остаются в заказе и доступны для дальнейшей загрузки.", class_name="loading-panel-description"),
            rx.box(),
        ),
        rx.cond(
            LoadingState.partial_send_stores.length() > 0,
            rx.vstack(
                rx.text("К отправке: ", LoadingState.partial_send_stores.length(), " магазинов · ", LoadingState.partial_send_net_kg, " кг нетто. После неё останется: ", LoadingState.partial_waiting_count),
                rx.button(
                    rx.cond(LoadingState.partial_pending_publication, "Повторить публикацию отправки",
                            rx.cond(LoadingState.partial_has_batches, "Отправить следующую загрузку", "Завершить загрузку частично")),
                    on_click=LoadingState.prepare_partial_loading,
                    disabled=LoadingState.partial_blocker != "", class_name="loading-primary",
                ),
                rx.cond(LoadingState.partial_blocker != "", rx.text(LoadingState.partial_blocker, class_name="loading-message", aria_live="polite"), rx.box()),
                align="start", width="100%", spacing="2",
            ), rx.box(),
        ),
        rx.alert_dialog.root(
            rx.alert_dialog.content(
                rx.alert_dialog.title("Отправить подтверждённые магазины?"),
                rx.alert_dialog.description("Водителю будут доступны только магазины этой отправки. Остальные не отменяются и остаются ожидающими загрузки."),
                rx.vstack(rx.foreach(LoadingState.partial_dialog_names, lambda name: rx.text(name)), spacing="1", align="start", margin_top="12px"),
                rx.text("Подтверждённое нетто: ", LoadingState.partial_dialog_net_kg, " кг. Остаётся магазинов: ", LoadingState.partial_dialog_waiting_count, margin_top="12px"),
                rx.cond(LoadingState.partial_dialog_error != "", rx.text(LoadingState.partial_dialog_error, color="red", role="alert"), rx.box()),
                rx.hstack(
                    rx.alert_dialog.cancel(rx.button("Отмена", variant="soft")),
                    rx.button("Подтвердить отправку", on_click=LoadingState.finish_partial_loading),
                    justify="end", wrap="wrap", margin_top="16px",
                ),
            ),
            open=LoadingState.partial_dialog_open, on_open_change=LoadingState.set_partial_dialog_open,
        ),
        width="100%", align="start", spacing="3",
    )


def _store_loading_reconciliation():
    return rx.vstack(
        rx.heading("Сверка выбранного магазина", size="3"),
        rx.text("Загрузка ниже — подтверждённые измерения. Отгрузку вводит водитель. Возвраты учитываются отдельно по маршруту.", class_name="loading-panel-description"),
        rx.foreach(LoadingState.sorted_loading_rows, lambda row: rx.box(
            rx.text(row["name"], font_weight="500"),
            rx.text("Заказано: ", row["planned_kg"], " кг · Загружено: ", rx.cond(LoadingState.is_read_only, row["preview_net_weight_kg"].to(str) + " кг", "не подтверждено"),
                    " · Отгружено: ", rx.cond(row["shipped_net_kg"] != "", row["shipped_net_kg"].to(str) + " кг", "не подтверждено")),
            class_name="loading-store-reconciliation-row",
        )),
        align="start", width="100%", spacing="2",
    )


def loading_page():
    return rx.cond(
        LoadingState.is_authorized,
        rx.box(
            rx.hstack(
                rx.hstack(
                    rx.box("Д", class_name="loading-brand-mark"),
                    rx.vstack(
                        rx.text("Доставка", class_name="loading-brand-title"),
                        rx.text("Складская загрузка", class_name="loading-brand-subtitle"),
                        align="start", spacing="0",
                    ),
                    class_name="loading-brand",
                    align="center",
                ),
                rx.hstack(
                    rx.el.select(rx.el.option("Как на устройстве", value="system"), rx.el.option("Светлая", value="light"),
                                 rx.el.option("Тёмная", value="dark"), default_value="system", aria_label="Тема оформления",
                                 custom_attrs={"data-theme-select": ""}, class_name="theme-select"),
                    rx.link("Рейсы машин / Догрузка", href="/trips", class_name="loading-secondary"),
                    rx.button("← Назад", on_click=LoadingState.back_to_orders, class_name="loading-secondary loading-back-button"),
                    align="center", spacing="2", class_name="loading-header-actions",
                ),
                class_name="loading-app-header",
                width="100%",
                align="center",
            ),
            rx.vstack(
                rx.text("Загрузка и сверка", class_name="loading-breadcrumb"),
                rx.hstack(
                    rx.vstack(
                        rx.heading("Рейс: загрузка и отгрузка", size="6"),
                        rx.text("Загрузка склада, отгрузка водителями и итоговая недостача", class_name="loading-page-description"),
                        align="start", spacing="1",
                    ),
                    rx.cond(
                        LoadingState.selected_order_id != "",
                        rx.text(LoadingState.selected_route_label, class_name="loading-route-badge"),
                        rx.box(),
                    ),
                    class_name="loading-route-title",
                    width="100%",
                    align="start",
                ),
                rx.cond(
                    LoadingState.selected_order_id != "",
                    rx.vstack(
                        rx.vstack(
                            _loading_mode_control(),
                            rx.cond(LoadingState.loading_mode == "stores", _store_loading_selector(), rx.box()),
                            _loading_table(),
                            rx.cond(
                                LoadingState.loading_mode == "stores",
                                rx.hstack(
                                    rx.cond(LoadingState.is_read_only,
                                            rx.text("Загрузка магазина подтверждена — доступен просмотр.", class_name="loading-message loading-message-success"),
                                            rx.button("Подтвердить загрузку магазина", on_click=LoadingState.confirm_selected_store, class_name="loading-primary")),
                                    rx.button("Следующий магазин", on_click=LoadingState.next_store, disabled=LoadingState.store_cards.length() < 2, class_name="loading-secondary"),
                                    align="center", width="100%", wrap="wrap", spacing="3",
                                ),
                                rx.cond(
                                    LoadingState.is_read_only,
                                    rx.text("Загрузка маршрута подтверждена. Отгрузку по магазинам вводит водитель этого маршрута.", class_name="loading-message loading-message-success"),
                                    rx.button("Подтвердить загрузку маршрута", on_click=LoadingState.save_loading, class_name="loading-primary"),
                                ),
                            ),
                            rx.cond(LoadingState.loading_mode == "stores", _partial_loading_control(), rx.box()),
                            rx.cond(LoadingState.loading_mode == "stores", _store_loading_reconciliation(), rx.box()),
                            rx.cond(LoadingState.status != "", rx.text(LoadingState.status, class_name="loading-message", aria_live="polite"), rx.box()),
                            rx.cond(
                                LoadingState.save_completed,
                                rx.hstack(
                                    rx.button("К списку заказов", on_click=LoadingState.back_to_orders, class_name="loading-secondary"),
                                    rx.button("Загрузить следующий заказ", on_click=LoadingState.load_next_order, class_name="loading-primary loading-next-button"),
                                    wrap="wrap", spacing="2", width="100%",
                                ),
                                rx.box(),
                            ),
                            align="start", spacing="4", width="100%", class_name="loading-panel loading-measurement-panel",
                        ),
                        _loading_context(),
                        width="100%", class_name="loading-workspace",
                    ),
                    rx.vstack(
                        _loading_context(),
                        rx.text("Выберите заказ, чтобы начать загрузку.", class_name="loading-empty-message"),
                        align="start", spacing="3", width="100%", class_name="loading-empty-workspace",
                    ),
                ),
                rx.cond(LoadingState.route_is_ready | LoadingState.partial_has_batches, _shipment_progress(), rx.box()),
                rx.cond(LoadingState.shipment_status == "shipment_completed", _reconciliation(), rx.box()),
                align="start", spacing="4", width="100%", class_name="loading-shell",
            ),
            width="100%", min_height="100vh", class_name="loading-app-frame",
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
                rx.call_script("window.location.replace('/loader/')"),
                router_data=event.router_data,
            )
        )
