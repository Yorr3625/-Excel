"""Workspace presentation helpers."""
from functools import partial
from orders_dashboard.constants import (
    ACCENT,
    HELP_CHAT_MODEL_OPTIONS,
    NAV_GROUPS,
    VOLUME_CHART_DAYS,
    VOLUME_ROUTE_LABELS,
)
from modules.tracking_sim import ROUTE_COLORS
from orders_dashboard.components import (
    _today_action,
    border,
    button_base,
    design_button,
    design_heading,
    design_icon,
    design_page,
    design_theme_switch,
    help_chat_message_bubble,
    loading_rail_item,
    muted,
    muted_text,
    navigation_icon,
    page_shell,
    panel_shell,
    panel_title,
    primary_button,
    secondary_button,
    segmented_control,
    sidebar_logo,
    surface,
    surface_alt,
    text,
    topbar,
)
from orders_dashboard.icons import fa_icon
import reflex as rx
from orders_dashboard import theme as ui


def rail_item(item, *, State):
    if item["target"] == "Шаблоны маршрутов":
        active = (State.current_page == "Маршруты") & State.routes_editor_open
    else:
        active = (State.current_page == item["target"]) & ~((State.current_page == "Маршруты") & State.routes_editor_open)
    return rx.el.button(
        navigation_icon(item["icon"], 18), rx.el.span(item["label"], class_name="nav-text"),
        rx.cond(active, rx.el.span(class_name="active-dot"), rx.fragment()),
        on_click=State.navigate(item["target"]), type="button", title=item["label"],
        aria_label=item["label"], aria_pressed=active,
        class_name=rx.cond(active, "nav-item active", "nav-item"),
    )


def sidebar(*, State):
    return rx.fragment(
        rx.cond(State.mobile_menu_open,
                rx.el.button(aria_label="Закрыть меню", on_click=State.close_mobile_menu, class_name="app-menu-backdrop"),
                rx.fragment()),
        rx.el.aside(
            rx.el.div(sidebar_logo(),
                      rx.el.button(design_icon("x", 18), on_click=State.close_mobile_menu,
                                   aria_label="Закрыть меню", class_name="sidebar-toggle sidebar-close", type="button"),
                      class_name="sidebar-brand-row"),
            rx.el.nav(*[rx.el.div(
                rx.el.p(section, class_name="nav-heading"),
                *[rail_item(item, State=State) for item in NAV_GROUPS if item["section"] == section],
                *([loading_rail_item()] if section == "Работа" else []),
                class_name="nav-group",
            ) for section in ["Работа", "Справочники", "Дополнительно", "Сервис"]],
                class_name="navigation", aria_label="Основная навигация"),
            rx.el.div(rx.el.span("Оформление", class_name="nav-heading"), design_theme_switch(),
                      rx.el.div(rx.el.span("Д", class_name="workspace-avatar"),
                                rx.el.span(rx.el.strong("Логистика"), rx.el.small("Рабочее место")),
                                class_name="workspace"), class_name="sidebar-footer"),
            class_name=rx.cond(State.mobile_menu_open, "sidebar app-sidebar-open", "sidebar"),
            id="dashboard-sidebar", aria_label="Боковая панель",
        ),
    )


def app_header(*, State):
    return rx.el.header(
        rx.el.div(
            rx.el.button(rx.cond(State.sidebar_collapsed, design_icon("panel_left_open", 18), design_icon("panel_left_close", 18)),
                         on_click=State.toggle_sidebar, type="button", class_name="sidebar-toggle desktop-toggle",
                         aria_label=rx.cond(State.sidebar_collapsed, "Развернуть боковое меню", "Свернуть боковое меню"),
                         aria_expanded=~State.sidebar_collapsed, aria_controls="dashboard-sidebar"),
            rx.el.button(design_icon("menu", 18), on_click=State.toggle_mobile_menu, type="button",
                         aria_label="Открыть меню", aria_expanded=State.mobile_menu_open,
                         aria_controls="dashboard-sidebar", class_name="sidebar-toggle mobile-toggle"),
            rx.el.div(rx.el.span("Рабочее пространство", class_name="breadcrumb-root"),
                      design_icon("chevron_right", 12), rx.el.span(State.current_page_label), class_name="breadcrumb"),
            class_name="header-start"),
        rx.cond((State.current_page == "Маршруты") | (State.current_page == "OCR накладных"),
                rx.input(value=State.search_query, on_change=State.set_search_query,
                         placeholder="Заказ, магазин, водитель…", aria_label="Поиск по текущему разделу",
                         class_name="app-search", width="220px"), rx.fragment()),
        rx.el.button(design_icon("log_out", 16), rx.el.span("Выйти"), on_click=State.logout,
                     type="button", class_name="logout"), class_name="topbar",
    )


def page_tab(item, *, State):
    active = State.current_page == item["page"]
    return rx.el.button(
        navigation_icon(item["icon"], 16), item["label"], type="button",
        on_click=State.set_page(item["page"]), aria_pressed=active,
        class_name=rx.cond(active, "page-tab selected", "page-tab"),
    )


def page_primary_action(*, State):
    return rx.match(
        State.current_page,
        (
            "Dashboard",
            primary_button("Добавить заказ", on_click=State.set_page("Заказы"), width="150px"),
        ),
        (
            "Маршруты",
            rx.cond(State.routes_editor_open, primary_button("Добавить маршрут", on_click=State.add_route, width="170px"), rx.box()),
        ),
        rx.box(),
    )


def app_tabs(*, State):
    return rx.cond(
        (State.current_tabs.length() > 1) | State.routes_editor_open,
        rx.hstack(
            rx.cond(State.current_tabs.length() > 1, rx.hstack(rx.foreach(State.current_tabs, lambda item: page_tab(item, State=State)), spacing="0", overflow_x="auto", min_width="0"), rx.box(display="none")),
            rx.spacer(), page_primary_action(State=State), width="100%", min_height="45px", padding="0 20px",
            background=ui.PANEL, border_bottom=f"1px solid {ui.LINE}", align="center", spacing="3", class_name="app-tabs",
        ), rx.box(display="none"),
    )


def volume_chart_panel(*, State):
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
                *[
                    rx.recharts.bar(data_key=label, stack_id="a", fill=ROUTE_COLORS[index])
                    for index, label in enumerate(VOLUME_ROUTE_LABELS)
                ],
                data=State.volume_chart_data,
                margin={"left": 0, "right": 8, "top": 4, "bottom": 0},
            ),
            width="100%",
            height=280,
        ),
    )


def dashboard_tracking_preview(*, State):
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


def overview_page(*, State):
    return design_page(
        design_heading("Сегодня", "Обзор рабочего дня", "Заказы, загрузка и отгрузка — всё в одном месте.",
                       design_button("Добавить заказ", State.set_page("Заказы"), "plus", primary=True)),
        rx.cond(State.pending_trip_unloads > 0, rx.el.section(
            rx.el.p("Выгрузки на бумаге, ожидающие внесения: ", State.pending_trip_unloads),
            rx.el.a("Внести веса и сверить рейсы →", href="/trips", class_name="button button-secondary"),
            class_name="pending-trip-note", role="status"), rx.fragment()),
        rx.el.section(
            rx.el.div(rx.el.span(design_icon("package"), class_name="summary-icon"),
                      rx.el.div(rx.el.h2("Обработано заказов"), rx.el.p("Сводка по обработке файлов")), class_name="summary-title"),
            rx.el.dl(rx.el.div(rx.el.dt("Сегодня"), rx.el.dd(State.orders_today_count)),
                     rx.el.div(rx.el.dt("За весь период"), rx.el.dd(State.orders_total_count)), class_name="summary-values"),
            class_name="summary", aria_label="Обработка заказов"),
        rx.el.section(
            rx.el.div(rx.el.div(rx.el.h2("Этапы доставки"), rx.el.p("Заказы, обработанные сегодня")),
                      rx.el.div(segmented_control(["Город", "Область"], State.today_mode, State.set_today_mode),
                                design_button("Обновить", [State.load_history, State.load_today_overview], "refresh_cw"),
                                class_name="toolbar-controls"), class_name="section-toolbar"),
            rx.el.p("Направление: ", State.today_mode, class_name="direction-caption"),
            rx.cond(State.today_error != "", rx.el.p(State.today_error, role="alert"),
                rx.el.div(
                    _today_action("Ожидают загрузки", State.today_waiting, State.open_today_stage("Ожидает загрузки"), "Загрузка ещё не начата", "clock", "01 / Загрузка"),
                    _today_action("Загрузка начата", State.today_drafts, State.open_today_stage("Загрузка начата"), "Черновики, ожидающие подтверждения", "package", "02 / Подготовка"),
                    _today_action("Готовы к отгрузке", State.today_ready, State.open_today_stage("Готов к отгрузке"), "Загрузка подтверждена", "circle_check", "03 / Готовность"),
                    _today_action("Отгрузка идёт", State.today_shipping, State.open_today_stage("Отгрузка идёт"), "Есть подтверждённые позиции отгрузки", "truck", "04 / Отгрузка"),
                    _today_action("Отгрузка завершена", State.today_completed, State.open_today_stage("Отгрузка завершена"), "Все магазины рейса завершены", "circle_check", "05 / Завершение"),
                    _today_action("Возвраты на проверке", State.today_returns, State.set_page("Возвраты"), "Все даты и направления", "undo_2", "Отдельный процесс", returns=True),
                    class_name="stage-grid")), class_name="workflow"),
        rx.el.details(rx.el.summary(rx.el.span(design_icon("file_text", 17), class_name="history-icon"),
                                    rx.el.span(rx.el.strong("История объёмов"), rx.el.small("Архив обработанных заказов")),
                                    design_icon("chevron_right", 16)),
                      rx.el.div(volume_chart_panel(State=State), class_name="design-history-content"), class_name="history"),
    )


def help_page(*, State):
    return page_shell(
        topbar("Помощь", "Короткие инструкции и чат-помощник."),
        panel_shell(
            rx.heading("Ежедневная работа", size="3"),
            muted_text("Заказы: загрузите файл, укажите клиента и направление, проверьте просмотр и подтвердите обработку."),
            muted_text("Рейсы: выберите маршрут и заказ. Откройте загрузку и сверку, чтобы увидеть складские измерения и отгрузку."),
            muted_text("Возвраты: проверьте документ водителя и примите или отклоните его с комментарием."),
            muted_text("Шаблоны маршрутов меняют будущие заказы. Учёт веса — отдельный журнал, а не форма загрузки рейса."),
        ),
        panel_shell(rx.heading("Чат-помощник", size="3"),
                    muted_text("Обычный чат без доступа к заказам и измерениям. Подключение настраивается в настройках."),
                    secondary_button("Открыть чат", on_click=State.toggle_help_chat, width="150px")),
    )


def help_chat_widget(*, State):
    return rx.fragment(
        rx.cond(
            State.help_chat_open,
            rx.vstack(
                rx.hstack(
                    fa_icon(tag="ai", size=15, color=ACCENT),
                    rx.text("Чат-помощник", color=text(), font_weight=ui.FONT_WEIGHT_SEMIBOLD, font_size="14px"),
                    rx.spacer(),
                    rx.button(
                        fa_icon(tag="x", size=13),
                        on_click=State.toggle_help_chat,
                        size="1",
                        variant="ghost",
                        color=muted(),
                        cursor="pointer",
                    ),
                    width="100%",
                    align="center",
                ),
                segmented_control(HELP_CHAT_MODEL_OPTIONS, State.help_chat_model_label, State.set_help_chat_model_label),
                rx.vstack(
                    rx.cond(
                        State.help_chat_messages.length() > 0,
                        rx.fragment(rx.foreach(State.help_chat_messages, help_chat_message_bubble)),
                        rx.text(
                            "Здравствуйте! Чем могу помочь? Это обычный чат — доступа к "
                            "заказам, весу и настройкам у него нет.",
                            color=muted(),
                            font_size="12px",
                        ),
                    ),
                    rx.cond(
                        State.help_chat_busy,
                        rx.text("Печатает...", color=muted(), font_size="12px"),
                        rx.box(),
                    ),
                    spacing="2",
                    width="100%",
                    align="start",
                    overflow_y="auto",
                    flex="1",
                ),
                rx.cond(
                    State.help_chat_status != "",
                    rx.text(State.help_chat_status, color=ui.STATUS_RED_TEXT, font_size="12px"),
                    rx.box(),
                ),
                rx.hstack(
                    rx.input(
                        value=State.help_chat_input,
                        on_change=State.set_help_chat_input,
                        placeholder="Напишите сообщение...",
                        width="100%",
                        height="38px",
                        disabled=State.help_chat_busy,
                    ),
                    rx.button(
                        fa_icon(tag="send", size=14),
                        on_click=State.send_help_chat_message,
                        disabled=State.help_chat_busy,
                        **button_base(height="38px", background=ACCENT, color=ui.WHITE),
                    ),
                    width="100%",
                    align="center",
                ),
                spacing="3",
                width="340px",
                height="460px",
                padding="14px",
                border_radius="14px",
                background=surface(),
                border=f"1px solid {border()}",
                position="fixed",
                bottom="92px",
                right="24px",
                z_index="999",
            ),
            rx.box(),
        ),
        rx.button(
            fa_icon(tag="ai", size=20, color=ui.INK_2),
            on_click=State.toggle_help_chat,
            position="fixed",
            bottom="24px",
            right="24px",
            width="48px",
            height="48px",
            border_radius=ui.RADIUS_PILL,
            color=ui.INK_2,
            background=ui.PANEL,
            border=f"1px solid {ui.LINE}",
            cursor="pointer",
            z_index="999",
            _hover={"background": ui.STATUS_GRAY_BG, "color": ui.INK},
            class_name="prototype-interactive",
            aria_label="Открыть помощника",
        ),
    )
