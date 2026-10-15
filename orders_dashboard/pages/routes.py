"""Routes presentation helpers."""
from functools import partial
from orders_dashboard.constants import DISPATCH_STAGES
from modules.config import MAX_ROUTES
from modules.tracking_sim import (
    ROUTE_COLORS,
    ROUTE_LABELS,
)
from orders_dashboard.components import (
    RouteDropTarget,
    _dispatch_trip_card,
    border,
    icon_button,
    muted,
    muted_text,
    page_shell,
    primary_button,
    rating_row,
    real_vehicle_card,
    secondary_button,
    segment_button,
    segmented_control,
    stat_card,
    surface,
    surface_alt,
    text,
    topbar,
    tracking_legend_dot,
    vehicle_card,
)
from orders_dashboard.icons import fa_icon
import reflex as rx
from orders_dashboard import theme as ui


def routes_backup_bar(*, State):
    return rx.hstack(
        secondary_button("Сохранить маршруты", on_click=State.save_routes, width="190px"),
        secondary_button("Создать копию", on_click=State.create_route_backup, width="150px"),
        rx.spacer(),
        fa_icon(tag="history", size=16, color=ui.INK_3),
        rx.select(
            State.route_backup_labels,
            value=State.selected_route_backup,
            on_change=State.set_selected_route_backup,
            placeholder="Резервные копии",
            width="250px",
        ),
        secondary_button("Восстановить", on_click=State.restore_route_backup, width="140px"),
        spacing="2",
        align="center",
        width="100%",
        wrap="wrap",
    )


def _dispatch_route_button(route, *, State):
    selected = State.dispatch_selected_route == route["route_key"]
    return rx.button(
        rx.hstack(
            rx.text(route["label"], font_weight=ui.FONT_WEIGHT_SEMIBOLD),
            rx.spacer(),
            rx.cond(selected, rx.text("Выбран", class_name="dispatch-selected-mark"), rx.box()),
            width="100%", align="center",
        ),
        rx.text("Рейсов: ", route["trip_count"], class_name="dispatch-route-caption"),
        rx.text("Магазины: ", route["completed_stores"], " / ", route["store_count"], class_name="dispatch-route-caption"),
        on_click=State.select_dispatch_route(route["route_key"]),
        aria_pressed=selected,
        class_name=rx.cond(selected, "dispatch-route-button dispatch-route-selected", "dispatch-route-button"),
    )


def _dispatch_overview(*, State):
    return rx.vstack(
        rx.hstack(
            rx.vstack(
                rx.heading("Обзор рейсов", size="4"),
                muted_text("Подтверждённая загрузка и отгрузка по каждому заказу."),
                align="start", spacing="1",
            ),
            rx.spacer(),
            rx.link(rx.button("Рейсы машин", variant="soft"), href="/trips"),
            secondary_button("Редактировать маршруты", on_click=State.open_routes_editor, width="210px"),
            width="100%", align="center", wrap="wrap", spacing="3",
        ),
        rx.hstack(
            rx.vstack(
                muted_text("Дата обработки заказа"),
                rx.input(type="date", value=State.dispatch_date, on_change=State.set_dispatch_date, aria_label="Дата обработки заказа"),
                align="start", spacing="1",
            ),
            rx.vstack(
                muted_text("Направление"),
                segmented_control(["Город", "Область"], State.dispatch_mode, State.set_dispatch_mode),
                align="start", spacing="1",
            ),
            rx.vstack(
                muted_text("Этап рейса"),
                rx.select.root(
                    rx.select.trigger(aria_label="Этап рейса", width="100%"),
                    rx.select.content(*[rx.select.item(stage, value=stage) for stage in DISPATCH_STAGES]),
                    value=State.dispatch_stage, on_change=State.set_dispatch_stage,
                ),
                align="start", spacing="1", width="230px", max_width="100%",
            ),
            secondary_button("Обновить", on_click=State.load_dispatch, width="120px"),
            rx.cond((State.dispatch_stage != "Все") | (State.search_query != ""), secondary_button("Сбросить фильтры", on_click=State.reset_dispatch_filters, width="170px"), rx.box()),
            width="100%", align="end", wrap="wrap", spacing="3", class_name="dispatch-filters",
        ),
        rx.cond(State.dispatch_message != "", rx.text(State.dispatch_message, role="status"), rx.box()),
        rx.cond(
            State.dispatch_routes.length() == 0,
            rx.vstack(
                rx.heading("Рейсов по выбранным условиям нет", size="3"),
                muted_text("Измените дату, направление или этап рейса."),
                secondary_button("Сбросить фильтры", on_click=State.reset_dispatch_filters, width="170px"),
                align="start", spacing="3", class_name="dispatch-empty",
            ),
            rx.box(
                rx.vstack(
                    rx.text("Маршруты", class_name="dispatch-panel-title"),
                    rx.cond(
                        State.dispatch_routes.length() > 0,
                        rx.foreach(State.dispatch_routes, lambda route: _dispatch_route_button(route, State=State)),
                        muted_text("Маршрутов по выбранным условиям нет."),
                    ),
                    width="100%", align="start", spacing="2", class_name="dispatch-route-list",
                ),
                rx.vstack(
                    rx.button("← К маршрутам", on_click=State.back_to_dispatch_routes, class_name="dispatch-mobile-back"),
                    rx.hstack(
                        rx.heading(State.dispatch_selected_label, size="4"),
                        rx.spacer(),
                        muted_text("Рейсов: ", State.dispatch_selected_trips.length()),
                        width="100%", align="center", wrap="wrap", spacing="2",
                    ),
                    rx.cond(
                        State.dispatch_selected_trips.length() > 0,
                        rx.foreach(State.dispatch_selected_trips, _dispatch_trip_card),
                        rx.vstack(
                            fa_icon(tag="route", size=28, color=ui.INK_3),
                            rx.text("Рейсов по выбранным условиям нет", font_weight=ui.FONT_WEIGHT_MEDIUM),
                            muted_text("Измените дату, направление или фильтры. Шаблоны магазинов доступны в редакторе."),
                            secondary_button("Сбросить фильтры", on_click=State.reset_dispatch_filters, width="170px"),
                            width="100%", align="start", spacing="3", class_name="dispatch-trip-card",
                        ),
                    ),
                    width="100%", align="start", spacing="3", class_name="dispatch-detail",
                ),
                class_name=rx.cond(State.dispatch_mobile_detail, "dispatch-workspace dispatch-show-detail", "dispatch-workspace"),
                width="100%",
            ),
        ),
        width="100%", align="start", spacing="4",
    )


def _template_route_tile(route, *, State):
    return RouteDropTarget.create(
        rx.button(
            rx.text(route["label"], font_weight="600"),
            rx.text(route["area"], class_name="route-template-caption"),
            rx.text("Магазинов: ", route["count"]),
            rx.cond(State.search_query != "", rx.text("Найдено: ", route["matches"], class_name="route-template-caption"), rx.box()),
            on_click=State.select_template_route(route["index"]),
            aria_pressed=State.selected_route_index == route["index"],
            class_name="route-template-route-button",
        ),
        on_drop=State.drop_template_store(route["index"]),
        custom_attrs={"data-route-drop": route["index"]},
        class_name=rx.cond(State.selected_route_index == route["index"], "route-template-route is-selected", "route-template-route"),
    )


def _template_store_tile(store, *, State):
    return rx.box(
        rx.hstack(
            rx.checkbox(checked=store["selected"], on_change=lambda _: State.toggle_template_store(store["name"]), aria_label="Выбрать " + store["name"].to(str)),
            rx.text(store["name"], class_name="route-template-store-name"),
            rx.el.span("⠿", draggable=True, title="Перетащите на плитку другого маршрута", aria_hidden=True,
                       custom_attrs={"data-route-drag": "true", "data-source": State.selected_route_index, "data-name": store["name"]},
                       class_name="route-template-drag-handle"),
            width="100%", align="start", spacing="2",
        ),
        rx.hstack(
            rx.button("Переместить в…", on_click=State.open_template_move(store["name"]), class_name="route-template-action"),
            rx.spacer(),
            icon_button("x", on_click=State.remove_route_store(State.selected_route_index, store["name"]), label="Удалить " + store["name"].to(str)),
            width="100%", align="center",
        ),
        class_name=rx.cond(store["selected"], "route-template-store is-selected", "route-template-store"),
    )


def _template_dialogs(*, State):
    return rx.fragment(
        rx.dialog.root(
            rx.dialog.content(
                rx.dialog.title("Переместить магазины"),
                rx.dialog.description("Перенос меняет только шаблоны будущих заказов. После переноса сохраните маршруты."),
                rx.text("Из: Маршрут №", State.template_move_source + 1, margin_top="12px"),
                rx.text("Магазинов: ", State.template_move_stores.length()),
                rx.box(rx.foreach(State.template_move_stores, lambda name: rx.text(name)), class_name="route-template-move-names"),
                rx.select(State.template_move_options, value=State.template_move_target, on_change=State.set_template_move_target,
                          placeholder="Выберите маршрут", aria_label="Целевой маршрут", width="100%"),
                rx.cond(State.template_move_error != "", rx.text(State.template_move_error, role="alert"), rx.box()),
                rx.hstack(secondary_button("Отмена", on_click=State.close_template_move), primary_button("Переместить", on_click=State.confirm_template_move),
                          justify="end", wrap="wrap", margin_top="16px"),
                max_width="480px",
            ),
            open=State.template_move_source >= 0,
            on_open_change=State.set_template_move_open,
        ),
        rx.alert_dialog.root(
            rx.alert_dialog.content(
                rx.alert_dialog.title("Отменить изменения шаблонов?"),
                rx.alert_dialog.description("Все несохранённые добавления, удаления и переносы магазинов будут отменены."),
                rx.hstack(secondary_button("Оставить изменения", on_click=State.cancel_template_discard), primary_button("Отменить изменения", on_click=State.discard_template_changes),
                          wrap="wrap", justify="end", margin_top="16px"),
            ),
            open=State.template_discard_open,
        ),
    )


def _routes_editor(*, State):
    return rx.vstack(
        rx.hstack(
            rx.vstack(
                rx.heading("Шаблоны маршрутов", size="4"),
                muted_text("Изменения применяются к будущим заказам, не к опубликованным рейсам."),
                align="start", spacing="1",
            ),
            rx.spacer(),
            secondary_button("К обзору рейсов", on_click=State.close_routes_editor, width="160px"),
            width="100%", align="center", wrap="wrap", spacing="3",
        ),
        segmented_control(["Город", "Область"], State.routes_source, State.set_routes_source),
        rx.box(
            rx.foreach(State.template_routes, lambda route: _template_route_tile(route, State=State)),
            rx.cond(State.active_route_count < MAX_ROUTES, rx.button("+ Новый маршрут", on_click=State.add_route, class_name="route-template-new-route"), rx.box()),
            class_name="route-template-routes",
        ),
        rx.vstack(
            rx.hstack(rx.heading(State.selected_route_label, size="3"), rx.spacer(), muted_text("Всего магазинов: ", State.template_store_count), width="100%", wrap="wrap"),
            muted_text("Перетащите магазин на плитку маршрута или нажмите «Переместить в…»."),
            rx.hstack(
                rx.text("Выбрано: ", State.template_selected_stores.length()),
                rx.button("Выбрать найденные", on_click=State.select_template_matches, class_name="route-template-action"),
                rx.button("Снять выделение", on_click=State.clear_template_selection, class_name="route-template-action"),
                rx.button("Переместить выбранные", on_click=State.open_template_move(""), disabled=State.template_selected_stores.length() == 0, class_name="route-template-action"),
                width="100%", wrap="wrap", align="center", spacing="3",
            ),
            rx.cond(
                State.template_stores.length() > 0,
                rx.box(rx.foreach(State.template_stores, lambda store: _template_store_tile(store, State=State)), class_name="route-template-stores"),
                rx.text(rx.cond(State.template_store_count == 0, "В этом маршруте пока нет магазинов. Добавьте новый или перенесите из другого маршрута.", "По запросу магазины не найдены. Измените поиск или выберите другой маршрут.")),
            ),
            rx.hstack(
                rx.input(placeholder="Название нового магазина", value=State.new_store_input, on_change=State.set_new_store, aria_label="Название нового магазина", width="100%"),
                secondary_button("Добавить", on_click=State.add_store),
                width="100%", align="center", spacing="2",
            ),
            width="100%", align="start", spacing="3", class_name="route-template-detail",
        ),
        rx.hstack(
            rx.cond(State.template_dirty, rx.text("Есть несохранённые изменения", role="status"), muted_text("Все изменения сохранены")),
            rx.spacer(),
            rx.button("Отменить изменения", on_click=State.request_template_discard, disabled=~State.template_dirty, class_name="route-template-action"),
            width="100%", wrap="wrap", align="center",
        ),
        routes_backup_bar(State=State),
        _template_dialogs(State=State),
        rx.cond(State.routes_status != "", rx.text(State.routes_status, role="status"), rx.box()),
        width="100%", align="start", spacing="4",
    )


def routes_page(*, State):
    return page_shell(
        rx.input(
            value=State.search_query, on_change=State.set_search_query,
            placeholder="Заказ, магазин, водитель…", aria_label="Поиск по текущему разделу",
            width="100%", class_name="dispatch-mobile-search",
        ),
        rx.cond(State.routes_editor_open, _routes_editor(State=State), _dispatch_overview(State=State)),
        rx.alert_dialog.root(
            rx.alert_dialog.content(
                rx.alert_dialog.title("Сохранить изменения маршрутов?"),
                rx.alert_dialog.description("Состав магазинов изменён. Сохраните его или явно откажитесь от изменений перед переходом."),
                rx.cond(State.route_editor_error != "", rx.text(State.route_editor_error, role="status"), rx.box()),
                rx.hstack(
                    secondary_button("Остаться", on_click=State.cancel_route_editor_transition, width="110px"),
                    secondary_button("Не сохранять", on_click=State.finish_route_editor_transition(False), width="140px"),
                    primary_button("Сохранить", on_click=State.finish_route_editor_transition(True), width="130px"),
                    spacing="2", justify="end", wrap="wrap", margin_top="16px",
                ),
                max_width="520px",
            ),
            open=State.route_editor_pending_action != "",
        ),
    )


def start_pause_button(*, State):
    return rx.cond(
        State.tracking_running,
        secondary_button("Пауза", on_click=State.stop_tracking, width="130px"),
        primary_button("Старт симуляции", on_click=State.start_tracking, width="180px"),
    )


def tracking_controls(*, State):
    return rx.hstack(
        segmented_control(["Город", "Область"], State.tracking_source, State.set_tracking_source),
        rx.spacer(),
        start_pause_button(State=State),
        secondary_button("Сброс", on_click=State.reset_tracking, width="110px"),
        spacing="3",
        align="center",
        width="100%",
    )


def tracking_legend(*, State):
    return rx.hstack(
        *[
            rx.cond(index < State.active_route_count, tracking_legend_dot(color, label), rx.box())
            for index, (label, color) in enumerate(zip(ROUTE_LABELS, ROUTE_COLORS))
        ],
        tracking_legend_dot(ui.STATUS_AMBER_TEXT, "Резкий разгон"),
        tracking_legend_dot(ui.STATUS_RED_TEXT, "Резкое торможение"),
        spacing="5",
        wrap="wrap",
        width="100%",
    )


def tracking_map_panel(*, State):
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
        tracking_legend(State=State),
        align="start",
        spacing="4",
        padding="18px",
        border=f"1px solid {border()}",
        border_radius="14px",
        background=surface(),
        width="100%",
    )


def rating_panel(*, State):
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
        padding="18px",
        border=f"1px solid {border()}",
        border_radius="14px",
        background=surface(),
        width="100%",
    )


def event_log_panel(*, State):
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
        padding="18px",
        border=f"1px solid {border()}",
        border_radius="14px",
        background=surface(),
        width="100%",
    )


def tracking_view_toggle(*, State):
    return rx.hstack(
        segment_button(
            "Демонстрация", rx.cond(State.tracking_view == "Симуляция", "Демонстрация", State.tracking_view),
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


def simulation_section(*, State):
    return rx.vstack(
        rx.text("Демонстрационные данные. Не используются для учёта рейсов.", role="status", color=ui.STATUS_AMBER_TEXT),
        tracking_controls(State=State),
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
        tracking_map_panel(State=State),
        rx.grid(
            rx.foreach(State.vehicles, vehicle_card),
            columns="2",
            spacing="4",
            width="100%",
        ),
        rx.grid(
            rating_panel(State=State),
            event_log_panel(State=State),
            columns="2",
            spacing="4",
            width="100%",
            align_items="start",
        ),
        spacing="4",
        width="100%",
    )


def real_data_section(*, State):
    return rx.vstack(
        rx.hstack(
            rx.text(
                "Данные от водителей и GPS-трекеров ГдеМои за сегодня — обновляется каждые ~5 сек.",
                color=muted(), font_size="13px",
            ),
            rx.spacer(),
            secondary_button("Обновить", on_click=State.refresh_real_data, width="120px"),
            width="100%",
            align="center",
        ),
        rx.cond(
            State.gdemoi_poll_status != "",
            rx.text(State.gdemoi_poll_status, color=ui.STATUS_AMBER_TEXT, font_size="12px"),
            rx.box(),
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


def tracking_page(*, State):
    return page_shell(
        topbar(
            "Трекинг",
            "Реальные данные от водителей. Демонстрация не отражает выполнение заказов.",
            actions=[tracking_view_toggle(State=State)],
        ),
        rx.cond(
            State.tracking_view == "Симуляция",
            simulation_section(State=State),
            real_data_section(State=State),
        ),
    )
