"""Dispatcher and warehouse workspace for physical vehicle trips."""
from datetime import date
import json
import uuid

import reflex as rx
from reflex.state import StateUpdate
from reflex_base.event import Event

from modules import driver_orders, vehicle_trips as trips, order_records
from orders_dashboard.loading_page import loading_principal_for_router

LABELS = {"draft": "Черновик", "active": "В пути", "return_pending": "Сверка возврата", "closed": "Закрыт"}


class TripState(rx.State):
    authorized: bool = False
    dispatcher: bool = False
    _principal: dict = {}
    message: str = ""
    choices: list[dict] = []
    chosen: list[str] = []
    trip_date: str = ""
    rows: list[dict] = []
    selected_id: str = ""
    title: str = ""
    status: str = ""
    status_label: str = ""
    revision: int = 0
    operation_id: str = ""
    products: list[dict] = []
    stops: list[dict] = []
    members: list[dict] = []
    history: list[dict] = []
    topups: list[dict] = []
    receipt_lines: list[dict] = []
    product_labels: list[str] = []
    catalogue: list[str] = []
    selected_catalogue: str = ""
    product_label: str = ""
    store_options: list[str] = []
    store_name: str = ""
    amount: str = ""
    comment: str = ""
    difference: str = ""
    topup_id: str = ""
    redirect_stop_id: str = ""
    target_label: str = "В свободный остаток"
    target_options: list[str] = ["В свободный остаток"]
    draft_total: str = "0"
    draft_complete: bool = False
    draft_parts: list[dict] = []
    _measurements: list[dict] = []
    _receipts: dict = {}
    _receipt_key: str = ""
    _target_map: dict = {}
    _amount: str = ""
    _difference: str = ""

    def set_trip_date(self, value: str):
        self.trip_date = value

    def set_product_label(self, value: str):
        self.product_label = value

    def set_selected_catalogue(self, value: str):
        self.selected_catalogue = value

    def set_store_name(self, value: str):
        self.store_name = value

    def set_amount(self, value: str):
        self.amount = self._amount = value

    def set_comment(self, value: str):
        self.comment = value

    def set_difference(self, value: str):
        self.difference = self._difference = value

    def set_target_label(self, value: str):
        self.target_label = value

    def load_page(self):
        principal = loading_principal_for_router(self.router)
        if principal is None:
            return rx.call_script("window.location.replace('/loader/')")
        self.authorized = True
        self._principal = principal
        self.dispatcher = principal["kind"] == "dashboard"
        self.trip_date = date.today().isoformat()
        self.refresh()
        params = self.router.url.query_parameters
        if params.get("trip"):
            self.select_trip(str(params["trip"]))

    def refresh(self):
        self.operation_id = uuid.uuid4().hex
        choices = trips.assignment_choices()
        self.choices = [{"id": item["assignment_id"], "label": " · ".join(str(item.get(key, "")) for key in ("route_label", "source_file", "driver_name", "vehicle_name", "vehicle_plate"))} for item in choices]
        self.catalogue = sorted({line["name"] for item in driver_orders._snapshots(active_only=True) for store in item["stores"] for line in store["lines"] if line.get("unit", "kg") == "kg"})
        self.rows = [{"id": item["id"], "title": item["vehicle_name"] + " · " + item["vehicle_plate"] + " · " + item["driver_name"], "date": item["date"], "status": LABELS[item["status"]]} for item in trips.list_trips()]
        if self.selected_id:
            self._apply(trips.load_trip(self.selected_id))

    def _apply(self, trip):
        self.title = trip["vehicle_name"] + " · " + trip["vehicle_plate"] + " · " + trip["driver_name"]
        self.status = trip["status"]
        self.status_label = LABELS[trip["status"]]
        self.revision = trip["revision"]
        self.products = trips.stock(trip)
        self.product_labels = [item["name"] for item in self.products]
        if self.product_label not in self.product_labels:
            self.product_label = self.product_labels[0] if self.product_labels else ""
        self.stops = [{**stop, "details": "; ".join(line["name"] + ": план " + line["planned"] + ", принято " + line["accepted"] + " кг" + (" · " + line["reason"] if line["reason"] else "") for line in stop["lines"]), "status_label": {"pending": "Ожидает", "completed": "Завершён", "cancelled": "Отменён"}[stop["status"]]} for stop in trip["stops"]]
        self.members = trips.preview_members(trip)
        self._target_map = {stop["name"] + " · " + stop["route_label"] + " · " + stop["id"][:6]: stop["id"] for stop in trip["stops"] if stop["status"] == "pending"}
        self.target_options = ["В свободный остаток", *self._target_map]
        if self.target_label not in self.target_options:
            self.target_label = "В свободный остаток"
        self.history = [{"kind": item["kind"], "at": item["at"], "actor": item["actor"].get("name") or item["actor"]["id"], "details": json.dumps(item.get("details", {}), ensure_ascii=False)} for item in trip["history"]]
        self.topups = [{**item, "name": next(product["name"] for product in trip["products"] if product["id"] == item["product_id"]), "net": order_records.loading_measurement_totals(item["measurement"])["partial_net_weight_kg"]} for item in trip["topups"]]
        stores = {stop["name"] for stop in trip["stops"]} | trips.store_catalogue()
        self.store_options = sorted(stores)
        doc = trip["returns"][-1] if trip["returns"] else None
        self.receipt_lines = []
        if doc:
            self.receipt_lines = [{"id": line["loading_line_id"], "name": line["name"], "declared": line["declared_net_kg"],
                                   "accepted": line.get("accepted_net_kg", ""), "difference": line.get("difference_kg", ""), "value": line.get("accepted_net_kg", line["declared_net_kg"])} for line in doc["lines"]]
            receipt_key = trip["id"] + ":" + doc["id"] + ":" + str(doc["revision"])
            if receipt_key != self._receipt_key:
                self._receipt_key = receipt_key
                self._receipts = {line["id"]: line["value"] for line in self.receipt_lines}
        self.message = trip.get("projection_error", "")

    def select_trip(self, identity: str):
        if identity not in {item["id"] for item in self.rows}:
            return
        self.selected_id = identity
        self.redirect_stop_id = ""
        self.amount = self._amount = ""
        self.difference = self._difference = ""
        self._apply(trips.load_trip(identity))
        self.new_topup()

    def toggle_choice(self, identity: str, checked: bool):
        if identity not in {item["id"] for item in self.choices}:
            return
        self.chosen = [item for item in self.chosen if item != identity] + ([identity] if checked else [])

    def create(self, operation_id: str):
        try:
            trip = trips.create_trip(self.chosen, self.trip_date, self._principal, operation_id)
        except (ValueError, OSError) as error:
            self.message = str(error)
            return
        self.selected_id = trip["id"]
        self.chosen = []
        self.refresh()
        self.new_topup()
        self.message = "Рейс создан. Проверьте маршруты и начните рейс после подтверждения загрузки."

    def _run(self, action, revision, operation_id, *args):
        try:
            action(self.selected_id, revision, *args, self._principal, operation_id)
        except (ValueError, OSError) as error:
            self.message = str(error)
            return False
        self.refresh()
        self.message = self.message or "Операция сохранена"
        return True

    def start(self, revision: int, operation_id: str):
        self._run(trips.start_trip, revision, operation_id)

    def attach(self, identity: str, revision: int, operation_id: str):
        self._run(trips.add_member, revision, operation_id, identity)

    def redirect(self, revision: int, operation_id: str):
        product_id = next((item["id"] for item in self.products if item["name"] == self.product_label), "")
        if self.redirect_stop_id:
            saved = self._run(trips.edit_redirect, revision, operation_id, self.redirect_stop_id, product_id, self._amount, self.store_name)
        else:
            saved = self._run(trips.redirect, revision, operation_id, product_id, self._amount, self.store_name)
        if saved:
            self.redirect_stop_id = ""

    def edit_redirect(self, identity: str):
        stop = next((item for item in self.stops if item["id"] == identity and item["kind"] == "transfer" and item["status"] == "pending"), None)
        if stop:
            self.redirect_stop_id = identity
            self.store_name = stop["name"]
            self.product_label = stop["lines"][0]["name"]
            self.amount = self._amount = stop["lines"][0]["planned"]

    def cancel_draft(self, revision: int, operation_id: str):
        self._run(trips.cancel_draft, revision, operation_id, self.comment)

    def cancel(self, stop_id: str, revision: int, operation_id: str):
        self._run(trips.cancel_stop, revision, operation_id, stop_id, self.comment)

    def add_product(self, revision: int, operation_id: str):
        self._run(trips.add_product, revision, operation_id, self.selected_catalogue)

    def new_topup(self):
        self.topup_id = ""
        self.target_label = "В свободный остаток"
        self._measurements = [{**order_records._empty_measurement(), "id": uuid.uuid4().hex}]
        self._show_parts()

    def _preview(self):
        totals = order_records.loading_measurement_totals({"weighings": self._measurements})
        self.draft_total = totals["partial_net_weight_kg"]
        self.draft_complete = totals["complete"]

    def _show_parts(self):
        self.draft_parts = [{**part, "label": f"Взвешивание {index + 1}"} for index, part in enumerate(self._measurements)]
        self._preview()

    def add_weighing(self):
        self._measurements = [*self._measurements, {**order_records._empty_measurement(), "id": uuid.uuid4().hex}]
        self._show_parts()

    def remove_weighing(self, identity: str):
        if len(self._measurements) <= 1:
            return
        self._measurements = [part for part in self._measurements if part["id"] != identity]
        self._show_parts()

    def edit_measurement(self, identity: str, field: str, value: str):
        if field not in {"box_count", "tare_weight_per_box_kg", "gross_weight_kg", "zero_reason"}:
            return
        self._measurements = [{**part, field: value} if part["id"] == identity else part for part in self._measurements]
        if field == "zero_reason":
            self.draft_parts = [{**part, "zero_reason": value} if part["id"] == identity else part for part in self.draft_parts]
        self._preview()

    def edit_topup(self, identity: str):
        target = next((item for item in self.topups if item["id"] == identity and item["status"] == "draft"), None)
        if target:
            self.topup_id = identity
            self.product_label = target["name"]
            self.target_label = next((label for label, stop_id in self._target_map.items() if stop_id == target.get("target_stop_id")), "В свободный остаток")
            self._measurements = [{**part, "id": part.get("id", uuid.uuid4().hex)} for part in order_records.loading_measurement_parts(target["measurement"])]
            self._show_parts()

    def save_topup(self, revision: int, operation_id: str):
        product_id = next((item["id"] for item in self.products if item["name"] == self.product_label), "")
        measure = {"weighings": self._measurements} if len(self._measurements) > 1 else {key: value for key, value in self._measurements[0].items() if key != "id"}
        try:
            trips.save_topup(self.selected_id, revision, product_id, measure, self._principal, operation_id, self.topup_id, self._target_map.get(self.target_label, ""))
        except (ValueError, OSError) as error:
            self.message = str(error)
            return
        self.refresh()
        self.new_topup()
        self.message = "Черновик догрузки сохранён. Товар появится в остатке после подтверждения."

    def confirm_topup(self, identity: str, revision: int, operation_id: str):
        self._run(trips.confirm_topup, revision, operation_id, identity)

    def cancel_topup(self, identity: str, revision: int, operation_id: str):
        self._run(trips.cancel_topup, revision, operation_id, identity)

    def set_receipt(self, identity: str, value: str):
        self._receipts = {**self._receipts, identity: value}

    def receive(self, revision: int, operation_id: str, reject: bool):
        try:
            trips.receive_return(self.selected_id, revision, self._receipts, self.comment, self._principal, operation_id, reject=reject)
        except (ValueError, OSError) as error:
            self.message = str(error)
            return
        self.refresh()
        self.message = "Возврат обработан. Проверьте остаток и расхождения."

    def resolve(self, revision: int, operation_id: str):
        product_id = next((item["id"] for item in self.products if item["name"] == self.product_label), "")
        self._run(trips.resolve_difference, revision, operation_id, product_id, self._difference, self.comment)

    def close(self, revision: int, operation_id: str):
        self._run(trips.close_trip, revision, operation_id)

    def repair(self):
        trips.repair_projections(self.selected_id)
        self.refresh()


def _confirm(label, event):
    return rx.alert_dialog.root(
        rx.alert_dialog.trigger(rx.button(label, variant="soft")),
        rx.alert_dialog.content(rx.alert_dialog.title(label + "?"), rx.alert_dialog.description("Операция будет записана в журнал движения товара."),
            rx.hstack(rx.alert_dialog.cancel(rx.button("Отмена", variant="soft")), rx.alert_dialog.action(rx.button("Подтвердить", on_click=event)), justify="end", margin_top="16px")),
    )


def _field(label, value, event, input_mode="decimal"):
    return rx.el.label(label, rx.debounce_input(rx.el.input(value=value, on_change=event, type="text", input_mode=input_mode, class_name="loading-amount-input"), debounce_timeout=350, force_notify_on_blur=True, force_notify_by_enter=True), class_name="trip-field")


def _part(part):
    return rx.vstack(
        rx.hstack(rx.text(part["label"]), rx.spacer(), rx.cond(TripState.draft_parts.length() > 1, _confirm("Удалить взвешивание", TripState.remove_weighing(part["id"])), rx.box()), width="100%"),
        rx.hstack(*[_field(label, part[field], TripState.edit_measurement(part["id"], field), input_mode="numeric" if field == "box_count" else "decimal") for field, label in (("box_count", "Ящики"), ("tare_weight_per_box_kg", "Тара, кг/ящик"), ("gross_weight_kg", "Брутто, кг"))], class_name="trip-measurement-fields", width="100%"),
        rx.el.label("Причина нулевого взвешивания (если ящики, тара и брутто равны 0)", rx.select(list(order_records.ZERO_REASON_OPTIONS), value=part["zero_reason"], on_change=TripState.edit_measurement(part["id"], "zero_reason"), placeholder="При необходимости", width="100%")),
        width="100%", class_name="trip-subcard", key=part["id"].to(str),
    )


def _detail():
    return rx.vstack(
        rx.hstack(rx.heading(TripState.title, size="4"), rx.spacer(), rx.text(TripState.status_label), width="100%", wrap="wrap"),
        rx.heading("Маршруты рейса", size="3"),
        rx.foreach(TripState.members, lambda item: rx.vstack(rx.text(item["route_label"], " · Загружено: ", item["loaded"], " кг · Принято магазинами: ", item["shipped"], " кг"), rx.text(item["error"], class_name="loading-message"), align="start", width="100%")),
        rx.cond((TripState.status == "draft") & TripState.dispatcher, rx.vstack(
            rx.text("Подтвердите загрузки. При старте текущие отгрузки будут импортированы без повторного списания."),
            rx.foreach(TripState.choices, lambda item: rx.button("Добавить: " + item["label"].to(str), variant="ghost", on_click=TripState.attach(item["id"], TripState.revision, TripState.operation_id))),
            _confirm("Начать рейс и импортировать факты", TripState.start(TripState.revision, TripState.operation_id)),
            _confirm("Отменить черновик рейса", TripState.cancel_draft(TripState.revision, TripState.operation_id)), width="100%", align="start"), rx.box()),
        rx.heading("Товар в машине", size="3"),
        rx.foreach(TripState.products, lambda item: rx.vstack(
            rx.text(item["name"], font_weight="600"),
            rx.text("Загрузка: ", item["loaded_kg"], " · Догрузки: ", item["topup_kg"], " · Принято магазинами: ", item["shipped_kg"], " кг"),
            rx.text("Остаток: ", item["remaining_kg"], " · Выделено: ", item["reserved_kg"], " · Свободно: ", item["available_kg"], " кг"),
            rx.text("Принято складом: ", item["returned_kg"], " · Расхождение: ", item["adjustment_kg"], " кг"),
            rx.text("Источники: ", item["sources"], class_name="trip-history-details"),
            class_name="trip-subcard", width="100%", align="start")),
        rx.heading("Магазины и дополнительные задания", size="3"),
        rx.foreach(TripState.stops, lambda item: rx.vstack(
            rx.text(item["name"], " · ", item["route_label"], " · ", item["status_label"], font_weight="600"), rx.text(item["details"]),
            rx.cond(TripState.dispatcher & (item["kind"] == "transfer") & (item["status"] == "pending"), rx.hstack(rx.button("Редактировать перенаправление", on_click=TripState.edit_redirect(item["id"]), variant="ghost"), _confirm("Отменить перенаправление", TripState.cancel(item["id"], TripState.revision, TripState.operation_id)), wrap="wrap"), rx.box()),
            width="100%", align="start", class_name="trip-subcard")),
        rx.cond(TripState.status == "active", rx.vstack(
            rx.heading("Операции с товаром", size="3"),
            rx.el.label("Товар", rx.select(TripState.product_labels, value=TripState.product_label, on_change=TripState.set_product_label, placeholder="Выберите товар", width="100%")),
            rx.cond(TripState.dispatcher, rx.vstack(
                rx.el.label("Магазин-получатель", rx.select(TripState.store_options, value=TripState.store_name, on_change=TripState.set_store_name, placeholder="Выберите магазин", custom_attrs={"aria-label": "Магазин-получатель"}, width="100%")),
                _field("Перенаправить, кг", TripState.amount, TripState.set_amount),
                rx.text(rx.cond(TripState.redirect_stop_id != "", "Редактирование существующего задания", "Новое дополнительное задание")),
                _confirm("Перенаправить товар", TripState.redirect(TripState.revision, TripState.operation_id)), align="start", width="100%"), rx.box()),
            rx.heading("Отдельная догрузка", size="3"),
            rx.hstack(rx.select(TripState.catalogue, value=TripState.selected_catalogue, on_change=TripState.set_selected_catalogue, placeholder="Добавить товар из заказов"),
                      _confirm("Добавить товар в рейс", TripState.add_product(TripState.revision, TripState.operation_id)), wrap="wrap"),
            rx.el.label("Куда выделить догрузку", rx.select(TripState.target_options, value=TripState.target_label, on_change=TripState.set_target_label, width="100%")),
            rx.foreach(TripState.draft_parts, _part),
            rx.text("Нетто заполненных взвешиваний: ", TripState.draft_total, " кг", rx.cond(TripState.draft_complete, "", " · Черновик, не все значения заполнены")),
            rx.hstack(rx.button("+ Добавить взвешивание", on_click=TripState.add_weighing, variant="soft"), rx.button("Новый черновик", on_click=TripState.new_topup, variant="ghost"),
                      rx.button("Сохранить черновик догрузки", on_click=TripState.save_topup(TripState.revision, TripState.operation_id)), wrap="wrap"),
            width="100%", align="start", spacing="3"), rx.box()),
        rx.foreach(TripState.topups, lambda item: rx.hstack(
            rx.text("Догрузка: ", item["name"], " · ", item["net"], " кг · ", item["status"]),
            rx.cond(item["status"] == "draft", rx.hstack(rx.button("Редактировать", on_click=TripState.edit_topup(item["id"]), variant="ghost"),
                _confirm("Подтвердить догрузку", TripState.confirm_topup(item["id"], TripState.revision, TripState.operation_id)),
                _confirm("Отменить догрузку", TripState.cancel_topup(item["id"], TripState.revision, TripState.operation_id)), wrap="wrap"), rx.box()), wrap="wrap", class_name="trip-subcard", width="100%")),
        rx.cond(TripState.receipt_lines.length() > 0, rx.vstack(
            rx.heading("Приём возврата и сверка", size="3"),
            rx.foreach(TripState.receipt_lines, lambda item: rx.vstack(
                rx.text(item["name"], " · Заявлено: ", item["declared"], " кг · Принято: ", item["accepted"], " · Разница: ", item["difference"]),
                rx.cond((TripState.status == "return_pending") & (item["accepted"] == ""), _field("Фактически принято складом, кг", item["value"], TripState.set_receipt(item["id"])), rx.box()), width="100%", align="start")),
            rx.cond((TripState.status == "return_pending") & (TripState.receipt_lines[0]["accepted"] == ""), rx.hstack(
                _confirm("Принять возврат", TripState.receive(TripState.revision, TripState.operation_id, False)),
                _confirm("Отклонить возврат", TripState.receive(TripState.revision, TripState.operation_id, True)), wrap="wrap"), rx.box()),
            width="100%", align="start"), rx.box()),
        rx.el.label("Причина / комментарий к отмене или сверке", rx.text_area(value=TripState.comment, on_change=TripState.set_comment, placeholder="Обязателен при отмене, отклонении и оформлении расхождения", width="100%"), width="100%"),
        rx.cond(TripState.dispatcher & (TripState.status != "draft") & (TripState.status != "closed"), rx.vstack(
            rx.el.label("Товар для сверки", rx.select(TripState.product_labels, value=TripState.product_label, on_change=TripState.set_product_label, width="100%")),
            _field("Расхождение, кг (минус — недостача, плюс — излишек)", TripState.difference, TripState.set_difference),
            rx.hstack(_confirm("Оформить расхождение", TripState.resolve(TripState.revision, TripState.operation_id)),
                      _confirm("Закрыть рейс", TripState.close(TripState.revision, TripState.operation_id)), wrap="wrap"), align="start", width="100%"), rx.box()),
        rx.button("Повторить сверку документов", on_click=TripState.repair, variant="soft"),
        rx.heading("Журнал операций", size="3"),
        rx.foreach(TripState.history, lambda item: rx.vstack(rx.text(item["at"], " · ", item["kind"], " · ", item["actor"]), rx.text(item["details"], class_name="trip-history-details"), width="100%", align="start", class_name="trip-subcard")),
        align="start", width="100%", spacing="4", class_name="loading-panel",
    )


def vehicle_trips_page():
    return rx.cond(TripState.authorized, rx.vstack(
        rx.hstack(rx.heading("Рейсы машин", size="6"), rx.spacer(), rx.el.select(rx.el.option("Как на устройстве", value="system"), rx.el.option("Светлая", value="light"), rx.el.option("Тёмная", value="dark"), default_value="system", aria_label="Тема оформления", custom_attrs={"data-theme-select": ""}, class_name="theme-select"), rx.link("← К загрузке", href="/loading"), rx.link("← В дашборд", href="/"), width="100%", wrap="wrap"),
        rx.text("Несколько маршрутов одной машины · остатки · перенаправления · догрузки · возвраты"),
        rx.button("Обновить", on_click=TripState.refresh, variant="soft"),
        rx.cond(TripState.dispatcher, rx.vstack(
            rx.heading("Создать рейс", size="3"), rx.el.label("Дата", rx.input(type="date", value=TripState.trip_date, on_change=TripState.set_trip_date)),
            rx.foreach(TripState.choices, lambda item: rx.checkbox(item["label"], checked=TripState.chosen.contains(item["id"]), on_change=TripState.toggle_choice(item["id"]))),
            _confirm("Создать рейс из выбранных маршрутов", TripState.create(TripState.operation_id)), align="start", width="100%", class_name="loading-panel"), rx.box()),
        rx.foreach(TripState.rows, lambda item: rx.button(item["title"].to(str) + " · " + item["date"].to(str) + " · " + item["status"].to(str), on_click=TripState.select_trip(item["id"]), width="100%", variant="soft", class_name="trip-list-button")),
        rx.cond(TripState.selected_id != "", _detail(), rx.text("Выберите рейс машины")),
        rx.text(TripState.message, role="status", aria_live="polite", class_name="loading-message"),
        align="start", width="100%", spacing="4", class_name="trip-workspace",
    ), rx.center(rx.spinner(), min_height="100vh"))


class TripAuthMiddleware(rx.Middleware):
    async def preprocess(self, app, state, event):
        prefix = TripState.get_full_name() + "."
        if not event.name.startswith(prefix) or event.name.removeprefix(prefix) == "hydrate":
            return None
        principal = loading_principal_for_router(event.router_data)
        if principal is not None:
            workspace = await state.get_state(TripState)
            workspace._principal = principal
            workspace.dispatcher = principal["kind"] == "dashboard"
            return None
        return StateUpdate(events=Event.from_event_type(rx.call_script("window.location.replace('/loader/')"), router_data=event.router_data, token=event.token), final=True)
