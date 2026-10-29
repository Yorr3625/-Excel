"""Components presentation helpers."""
from orders_dashboard.constants import (
    ACCENT,
    DASHBOARD_LOGIN_JS,
    PAGE_LABELS,
    RETURN_STATUS_LABELS,
    UPLOAD_ID,
)
from reflex.components.radix.themes.layout.box import Box
from decimal import Decimal
from modules.excel_io import EXCEL_MIME_TYPES
from orders_dashboard.icons import fa_icon
import reflex as rx
from orders_dashboard import theme as ui


class RouteDropTarget(Box):

    def get_event_triggers(self):
        return {
            **super().get_event_triggers(),
            "on_drop": lambda event: [rx.Var(
                _js_expr=f"{event}.dataTransfer.getData('text/plain')",
                _var_type=str,
            )],
        }


def format_decimal(value: Decimal) -> str:
    rendered = format(value.normalize(), "f")
    return rendered.rstrip("0").rstrip(".") if "." in rendered else rendered


def page_bg():
    return ui.PAGE


def surface():
    return ui.PANEL


def surface_alt():
    return ui.STATUS_GRAY_BG


def border():
    return ui.LINE


def text():
    return ui.INK


def muted():
    return ui.INK_2


def button_base(**props):
    return {
        "height": "32px",
        "border_radius": ui.RADIUS_CONTROL,
        "font_weight": ui.FONT_WEIGHT_MEDIUM,
        "cursor": "pointer",
        "class_name": "prototype-interactive",
        **props,
    }


def primary_button(label: str, on_click=None, width: str = "230px", disabled=False):
    return rx.button(
        label,
        on_click=on_click,
        width=width,
        disabled=disabled,
        color=ui.WHITE,
        background=ui.PURPLE,
        border=f"1px solid {ui.PURPLE}",
        _hover={"background": ui.PURPLE_DARK, "border_color": ui.PURPLE_DARK},
        **button_base(),
    )


def secondary_button(label: str, on_click=None, width: str = "156px", disabled=False):
    return rx.button(
        label,
        on_click=on_click,
        width=width,
        disabled=disabled,
        color=ui.INK,
        background=ui.PANEL,
        border=f"1px solid {ui.LINE}",
        _hover={"background": ui.STATUS_GRAY_BG},
        **button_base(),
    )


def icon_button(icon: str, on_click=None, label: str = "", disabled=False):
    return rx.button(
        fa_icon(tag=icon, size=16),
        on_click=on_click,
        disabled=disabled,
        aria_label=label,
        width="32px",
        min_width="32px",
        padding="0",
        color=ui.INK_2,
        background=ui.PANEL,
        border=f"1px solid {ui.LINE}",
        _hover={"background": ui.STATUS_GRAY_BG, "color": ui.INK},
        **button_base(),
    )


def segment_button(label: str, current, on_click):
    active = current == label

    return rx.button(
        label,
        on_click=on_click,
        height="32px",
        min_width="88px",
        border_radius=ui.RADIUS_CONTROL,
        color=rx.cond(active, ui.INK, ui.INK_2),
        background=rx.cond(active, ui.PANEL, ui.TRANSPARENT),
        border=rx.cond(active, f"1px solid {ui.LINE}", "1px solid transparent"),
        _hover={"background": rx.cond(active, ui.PANEL, ui.STATUS_GRAY_BG)},
        font_weight=rx.cond(active, ui.FONT_WEIGHT_MEDIUM, ui.FONT_WEIGHT_REGULAR),
        class_name="prototype-interactive",
    )


def segmented_control(values: list[str], current, setter):
    return rx.hstack(
        *[segment_button(value, current, setter(value)) for value in values],
        spacing="1",
        padding="3px",
        border=f"1px solid {ui.LINE}",
        border_radius=ui.RADIUS_CONTROL,
        background=ui.STATUS_GRAY_BG,
        width="fit-content",
    )


def muted_text(*parts, size=ui.FONT_SIZE_LABEL):
    return rx.text(*parts, color=ui.INK_2, font_size=size)


def metric_card(label: str, value, supporting=None, value_color=ui.INK):
    return rx.vstack(
        rx.text(label, color=ui.INK_2, font_size=ui.FONT_SIZE_LABEL),
        rx.text(
            value,
            color=value_color,
            font_size=ui.FONT_SIZE_METRIC,
            font_weight=ui.FONT_WEIGHT_SEMIBOLD,
            line_height="1.15",
        ),
        supporting or rx.box(),
        align="start",
        spacing="1",
        padding="14px 16px",
        border=f"1px solid {ui.LINE}",
        border_radius=ui.RADIUS_CARD,
        background=ui.PANEL,
        width="100%",
    )


def stat_card(icon: str, tint_key: str, title: str, value, hint_node):
    """Backward-compatible wrapper while remaining screens migrate to metric_card."""

    del icon, tint_key
    return metric_card(title, value, hint_node)


def _pill(label, background, color):
    return rx.text(
        label,
        color=color,
        background=background,
        font_size=ui.FONT_SIZE_LABEL,
        font_weight=ui.FONT_WEIGHT_MEDIUM,
        padding="3px 10px",
        border_radius=ui.RADIUS_PILL,
        white_space="nowrap",
    )


def status_pill(status):
    """One status component for all screens, using the defined color pairs."""

    return rx.match(
        status,
        ("Пришёл", _pill(status, ui.STATUS_GREEN_BG, ui.STATUS_GREEN_TEXT)),
        ("Опоздал", _pill(status, ui.STATUS_AMBER_BG, ui.STATUS_AMBER_TEXT)),
        ("Отсутствует", _pill(status, ui.STATUS_RED_BG, ui.STATUS_RED_TEXT)),
        ("В работе", _pill(status, ui.STATUS_BLUE_BG, ui.STATUS_BLUE_TEXT)),
        ("В пути", _pill(status, ui.STATUS_AMBER_BG, ui.STATUS_AMBER_TEXT)),
        ("Требует внимания", _pill(status, ui.STATUS_AMBER_BG, ui.STATUS_AMBER_TEXT)),
        ("Отгружен", _pill(status, ui.STATUS_GREEN_BG, ui.STATUS_GREEN_TEXT)),
        ("Подтверждено", _pill(status, ui.STATUS_GREEN_BG, ui.STATUS_GREEN_TEXT)),
        ("Просрочен", _pill(status, ui.STATUS_RED_BG, ui.STATUS_RED_TEXT)),
        ("Ошибка", _pill(status, ui.STATUS_RED_BG, ui.STATUS_RED_TEXT)),
        _pill(status, ui.STATUS_GRAY_BG, ui.STATUS_GRAY_TEXT),
    )


def driver_avatar(initials, assigned=True, label=""):
    return rx.cond(
        assigned,
        rx.box(
            initials,
            title=label,
            display="inline-flex",
            align_items="center",
            justify_content="center",
            width="24px",
            height="24px",
            min_width="24px",
            border_radius="50%",
            color=ui.PURPLE_DARK,
            background=ui.PURPLE_BG,
            font_size="10px",
            font_weight=ui.FONT_WEIGHT_SEMIBOLD,
        ),
        rx.box(
            "+",
            title=label,
            display="inline-flex",
            align_items="center",
            justify_content="center",
            width="24px",
            height="24px",
            min_width="24px",
            border=f"1px dashed {ui.LINE_STRONG}",
            border_radius="50%",
            color=ui.INK_3,
            font_size=ui.FONT_SIZE_BODY,
        ),
    )


def employee_avatar(initials):
    return rx.el.span(initials, class_name="personnel-avatar", aria_hidden=True)


def employee_role_pill(role):
    return rx.match(
        role,
        ("loader", _pill("Грузчик", ui.STATUS_GREEN_BG, ui.STATUS_GREEN_TEXT)),
        ("expeditor", _pill("Экспедитор", ui.STATUS_BLUE_BG, ui.STATUS_BLUE_TEXT)),
        _pill("Водитель", ui.PURPLE_BG, ui.PURPLE_DARK),
    )


def personnel_field(label, name, value="", input_type="text", **props):
    return rx.el.label(
        rx.el.span(label),
        rx.el.input(name=name, default_value=value, type=input_type, **props),
        class_name="personnel-field",
    )


def table_container(*children):
    return rx.box(
        *children,
        width="100%",
        overflow="hidden",
        background=ui.PANEL,
        border=f"1px solid {ui.LINE}",
        border_radius=ui.RADIUS_CARD,
    )


def navigation_icon(name, size=19):
    return rx.match(
        name,
        ("layout_dashboard", fa_icon(tag="layout_dashboard", size=size)),
        ("truck", fa_icon(tag="truck", size=size)),
        ("calendar_check", fa_icon(tag="calendar_check", size=size)),
        ("package", fa_icon(tag="package", size=size)),
        ("route", fa_icon(tag="route", size=size)),
        ("file_spreadsheet", fa_icon(tag="file_spreadsheet", size=size)),
        ("scale", fa_icon(tag="scale", size=size)),
        ("settings", fa_icon(tag="settings", size=size)),
        ("mail", fa_icon(tag="mail", size=size)),
        ("history", fa_icon(tag="history", size=size)),
        ("list", fa_icon(tag="list", size=size)),
        ("map", fa_icon(tag="map", size=size)),
        ("camera", fa_icon(tag="camera", size=size)),
        ("save", fa_icon(tag="save", size=size)),
        ("info", fa_icon(tag="info", size=size)),
        fa_icon(tag="circle", size=size),
    )


def theme_selector():
    return rx.el.select(
        rx.el.option("Как на устройстве", value="system"),
        rx.el.option("Светлая", value="light"),
        rx.el.option("Тёмная", value="dark"),
        aria_label="Тема оформления", custom_attrs={"data-theme-select": ""},
        class_name="theme-select", default_value="system",
    )


def design_icon(tag, size=20, **props):
    return fa_icon(tag=tag, size=size, class_name="icon", **props)


def design_button(label, action, icon="", primary=False, **props):
    children = ([design_icon(icon, 17)] if icon else []) + [label]
    return rx.el.button(*children, on_click=action, type="button",
                        class_name="button " + ("button-primary" if primary else "button-secondary"), **props)


def design_heading(title, eyebrow, description, action=None):
    return rx.el.div(
        rx.el.div(rx.el.p(eyebrow, class_name="eyebrow"),
                  rx.el.h1(title, rx.el.span(".", class_name="heading-dot")),
                  rx.el.p(description, class_name="page-description")),
        action if action is not None else rx.fragment(), class_name="page-heading",
    )


def design_page(*children, class_name=""):
    return rx.el.div(*children, rx.el.footer(rx.el.span("Доставка / Рабочее пространство"),
                                            rx.el.span("Заказы и доставка"), class_name="page-footer"),
                     class_name="design-page " + class_name)


def design_panel_heading(number, title, description):
    return rx.el.div(rx.el.span(number, class_name="panel-number"),
                     rx.el.div(rx.el.h3(title), rx.el.p(description)), class_name="panel-heading")


def design_mail_panel(section, *children):
    return rx.el.section(*children, class_name="mail-block " + section)


def design_theme_switch():
    return rx.el.div(
        *[rx.el.button(design_icon(icon, 15), rx.el.span(label, class_name="theme-name"),
                       type="button", custom_attrs={"data-theme-choice": value},
                       aria_label=label + " тема", aria_pressed=False)
          for value, label, icon in (("light", "Светлая", "sun"), ("dark", "Тёмная", "moon"))],
        theme_selector(), class_name="theme-switch", role="group", aria_label="Выбор темы",
    )


def sidebar_logo():
    return rx.el.div(rx.el.span("д", rx.el.span(), class_name="brand-mark"),
                     rx.el.span(rx.el.strong("Доставка"), rx.el.small("Рабочее пространство"), class_name="brand-copy"),
                     class_name="brand")


def loading_rail_item():
    return rx.fragment(
        rx.el.a(design_icon("truck", 18), rx.el.span("Рейсы машин", class_name="nav-text"), href="/trips", class_name="nav-item", title="Рейсы машин"),
        rx.el.button(design_icon("package", 18), rx.el.span("Загрузка и сверка", class_name="nav-text"),
                     on_click=rx.redirect("/loading"), type="button", class_name="nav-item",
                     title="Загрузка и сверка", aria_label="Загрузка и сверка"),
    )


def upload_area():
    return rx.upload(
        rx.vstack(
            rx.el.span(design_icon("upload", 24), class_name="upload-symbol"),
            rx.el.strong("Выберите Excel-файл"),
            rx.el.p("Перетащите книгу сюда или нажмите, чтобы выбрать файл."),
            rx.el.span("Обзор файлов", class_name="file-label"),
            rx.foreach(rx.selected_files(UPLOAD_ID), lambda file: rx.el.span(file, class_name="selected-upload-file")),
            align="center", spacing="3", width="100%",
        ),
        id=UPLOAD_ID, accept=EXCEL_MIME_TYPES, max_files=1,
        aria_label="Выбрать Excel-файл заказа",
        class_name="file-picker", width="100%", border="0", padding="0", cursor="pointer",
    )


def result_metric(label: str, value):
    return rx.vstack(
        rx.text(label, color=muted(), font_size="12px"),
        rx.text(value, color=text(), font_size="22px", font_weight=ui.FONT_WEIGHT_SEMIBOLD),
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
        rx.text(label, color=text(), font_size="14px", font_weight=ui.FONT_WEIGHT_SEMIBOLD),
        rx.spacer(),
        rx.text(value, color=text(), font_size="14px", font_weight=ui.FONT_WEIGHT_SEMIBOLD),
        width="100%",
        padding="11px 12px",
        border_radius="9px",
        background=surface_alt(),
    )


def preview_metric(label: str, value):
    return rx.vstack(
        rx.text(label, color=muted(), font_size="12px"),
        rx.text(value, color=text(), font_size="20px", font_weight=ui.FONT_WEIGHT_SEMIBOLD),
        align="start",
        spacing="1",
        padding="12px",
        border=f"1px solid {border()}",
        border_radius="10px",
        background=surface_alt(),
        width="100%",
    )


def page_shell(*children):
    return rx.vstack(
        *children,
        align="start",
        spacing="4",
        width="100%",
        max_width="1180px",
        padding="18px 16px 40px",
        background=ui.PAGE,
        class_name="app-main-view",
    )


def topbar(title: str, subtitle: str, actions=None):
    return rx.hstack(
        rx.vstack(rx.heading(PAGE_LABELS.get(title, title), size="5"),
                  rx.text(subtitle, color=ui.INK_2, font_size=ui.FONT_SIZE_LABEL), align="start", spacing="1"),
        rx.spacer(),
        *(actions or []),
        width="100%",
        min_height="32px",
        align="center",
        spacing="3",
    )


def panel_shell(*children):
    return rx.vstack(
        *children,
        align="start",
        spacing="3",
        padding="16px",
        border=f"1px solid {ui.LINE}",
        border_radius=ui.RADIUS_CARD,
        background=ui.PANEL,
        width="100%",
    )


def panel_title(icon: str, title: str):
    return rx.hstack(
        fa_icon(tag=icon, size=16, color=ui.INK_2),
        rx.text(
            title,
            color=ui.INK,
            font_size=ui.FONT_SIZE_CARD_TITLE,
            font_weight=ui.FONT_WEIGHT_SEMIBOLD,
        ),
        spacing="2",
        align="center",
    )


def _today_action(label, count, action, note, icon="package", step="", returns=False):
    return rx.el.button(
        rx.el.div(rx.el.span(design_icon(icon, 18), class_name="stage-icon"),
                  rx.el.span(step, class_name="stage-step"), class_name="stage-top"),
        rx.el.h3(label), rx.el.p(note),
        rx.el.div(rx.el.span(count, rx.el.span("возвратов" if returns else "заказов"), class_name="stage-value"),
                  rx.el.span(rx.cond(count == 0, "Нет возвратов" if returns else "Нет заказов", "Открыть"), class_name="stage-state"),
                  class_name="stage-bottom"),
        on_click=action, type="button", aria_label=label,
        class_name="stage-card stage-card-return" if returns else "stage-card",
    )


def weight_field(
    label: str,
    value,
    on_change,
    placeholder: str = "",
    on_blur=None,
    input_type: str = "text",
):
    return rx.vstack(
        rx.text(label, color=text(), font_size="12px", font_weight=ui.FONT_WEIGHT_SEMIBOLD),
        rx.input(
            value=value,
            on_change=on_change,
            on_blur=on_blur,
            type=input_type,
            placeholder=placeholder,
            width="100%",
            height="40px",
        ),
        align="start",
        spacing="1",
        width="100%",
    )


def weight_select_field(label: str, value, on_change, items):
    return rx.vstack(
        rx.text(label, color=text(), font_size="12px", font_weight=ui.FONT_WEIGHT_SEMIBOLD),
        rx.select(
            items,
            value=value,
            on_change=on_change,
            width="100%",
            height="40px",
        ),
        align="start",
        spacing="1",
        width="100%",
    )


def weight_stat(label: str, *value_parts):
    return rx.vstack(
        rx.text(*value_parts, color=text(), font_size="14px", font_weight=ui.FONT_WEIGHT_SEMIBOLD),
        rx.text(label, color=muted(), font_size="11px"),
        align="start",
        spacing="0",
        min_width="120px",
    )


def invoice_ocr_journal_row(item):
    return rx.hstack(
        rx.vstack(
            rx.text(item["order_file"], color=text(), font_weight=ui.FONT_WEIGHT_SEMIBOLD, font_size="13px"),
            rx.text(item["saved_at"], color=muted(), font_size="11px"),
            align="start",
            spacing="1",
            min_width="200px",
        ),
        weight_stat("Маршрут", item["route"]),
        weight_stat("Магазин", item["store_number"]),
        weight_stat("Позиций", item["line_count"]),
        weight_stat("Итого", item["total"]),
        width="100%",
        padding="10px 12px",
        border_radius="10px",
        background=surface_alt(),
        spacing="4",
        align="center",
        wrap="wrap",
    )


def mail_verdict_badge(is_order):
    return rx.cond(
        is_order,
        rx.hstack(
            fa_icon(tag="circle_check", size=13, color=ACCENT),
            rx.text("Похоже на заказ", color=ACCENT, font_size="12px", font_weight=ui.FONT_WEIGHT_SEMIBOLD),
            spacing="2",
            align="center",
        ),
        rx.hstack(
            fa_icon(tag="circle_x", size=13, color=ui.STATUS_RED_TEXT),
            rx.text("Не заказ", color=ui.STATUS_RED_TEXT, font_size="12px", font_weight=ui.FONT_WEIGHT_SEMIBOLD),
            spacing="2",
            align="center",
        ),
    )


def _dispatch_stage_badge(stage):
    return rx.match(
        stage,
        ("Отгрузка завершена", _pill(stage, ui.STATUS_GREEN_BG, ui.STATUS_GREEN_TEXT)),
        ("Отгрузка идёт", _pill(stage, ui.STATUS_BLUE_BG, ui.STATUS_BLUE_TEXT)),
        ("Готов к отгрузке", _pill(stage, ui.STATUS_BLUE_BG, ui.STATUS_BLUE_TEXT)),
        ("Загружен частично", _pill(stage, ui.STATUS_BLUE_BG, ui.STATUS_BLUE_TEXT)),
        ("Ящики учтены, ожидается взвешивание", _pill(stage, ui.STATUS_AMBER_BG, ui.STATUS_AMBER_TEXT)),
        ("Загрузка начата", _pill(stage, ui.STATUS_AMBER_BG, ui.STATUS_AMBER_TEXT)),
        _pill(stage, ui.STATUS_GRAY_BG, ui.STATUS_GRAY_TEXT),
    )


def _dispatch_assignment(assignment):
    return rx.hstack(
        fa_icon(tag="truck", size=16, color=ui.INK_2),
        rx.text(assignment["driver_name"], font_weight=ui.FONT_WEIGHT_MEDIUM),
        muted_text(assignment["vehicle_name"], " · ", assignment["vehicle_plate"]),
        rx.text(rx.cond(assignment["active"], "Актуальное назначение", "Историческое назначение"), class_name="dispatch-assignment-note"),
        wrap="wrap", spacing="2", width="100%", align="center",
    )


def _dispatch_store(store):
    return rx.hstack(
        fa_icon(tag="store", size=15, color=ui.INK_2),
        rx.text(store["name"], flex="1", min_width="0", overflow_wrap="anywhere"),
        muted_text(store["shipped_net_kg"], rx.cond(store["shipped_net_kg"] != "—", " кг", "")),
        rx.text(store["status"], color=rx.cond(store["completed"], ui.STATUS_GREEN_TEXT, ui.INK_2), font_size="11px"),
        width="100%", align="center", spacing="2", class_name="dispatch-store-row",
    )


def _dispatch_trip_card(trip):
    return rx.vstack(
        rx.hstack(
            rx.vstack(
                rx.heading("Заказ ", trip["order_number"], size="3"),
                muted_text(trip["client_name"], " · ", trip["processed_display"]),
                align="start", spacing="1", min_width="0",
            ),
            rx.spacer(),
            _dispatch_stage_badge(trip["stage"]),
            width="100%", align="start", wrap="wrap", spacing="2",
        ),
        rx.cond(
            trip["assignments"].length() > 0,
            rx.vstack(rx.foreach(trip["assignments"], _dispatch_assignment), width="100%", spacing="2"),
            muted_text("Водитель не назначен"),
        ),
        rx.cond(
            (trip["assignments"].length() > 0) & ~trip["has_active_assignment"],
            muted_text("Актуального назначения нет. Показана история."), rx.box(display="none"),
        ),
        rx.cond(trip["limited_data"], muted_text("Старая запись: нет точного распределения загрузки по маршрутам."), rx.box(display="none")),
        rx.hstack(
            rx.text("Загрузка: ", rx.cond(trip["limited_data"], "Нет маршрутных данных", rx.cond(trip["loading_ready"], "Подтверждена", "Не подтверждена"))),
            rx.text("Магазины: ", trip["completed_stores"], " из ", trip["store_count"]),
            wrap="wrap", spacing="3", class_name="dispatch-trip-facts", width="100%",
        ),
        rx.hstack(
            rx.text("Загружено: ", trip["loaded_net_kg"], rx.cond(trip["loaded_net_kg"] != "—", " кг", "")),
            rx.text("Отгружено: ", trip["shipped_net_kg"], rx.cond(trip["shipped_net_kg"] != "—", " кг", "")),
            wrap="wrap", spacing="3", class_name="dispatch-trip-weights", width="100%",
        ),
        rx.cond(trip["return_label"] != "", rx.text(trip["return_label"], " · ", trip["return_net_kg"], " кг", class_name="dispatch-return-note"), rx.box(display="none")),
        rx.el.details(
            rx.el.summary("Магазины маршрута", class_name="dispatch-store-summary"),
            rx.vstack(rx.foreach(trip["stores"], _dispatch_store), width="100%", spacing="0"),
            width="100%",
        ),
        rx.link("Открыть загрузку и сверку", href=trip["loading_href"], class_name="dispatch-loading-link"),
        width="100%", align="start", spacing="3", class_name="dispatch-trip-card",
    )


def tracking_legend_dot(color, label):
    return rx.hstack(
        rx.box(width="10px", height="10px", min_width="10px", border_radius="50%", background=color),
        rx.text(label, color=muted(), font_size="12px"),
        spacing="2",
        align="center",
    )


def event_badge(flag):
    return rx.cond(
        flag == "harsh_brake",
        rx.text("Резкое торможение", color=ui.STATUS_RED_TEXT, font_size="11px", font_weight=ui.FONT_WEIGHT_SEMIBOLD),
        rx.cond(
            flag == "harsh_accel",
            rx.text("Резкий разгон", color=ui.STATUS_AMBER_TEXT, font_size="11px", font_weight=ui.FONT_WEIGHT_SEMIBOLD),
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
            rx.text(v["label"], color=text(), font_size="14px", font_weight=ui.FONT_WEIGHT_SEMIBOLD),
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
        width="100%",
    )


def rating_row(v):
    return rx.hstack(
        rx.box(width="8px", height="8px", min_width="8px", border_radius="50%", background=v["color"]),
        rx.text(v["label"], color=text(), font_size="13px", font_weight=ui.FONT_WEIGHT_SEMIBOLD),
        rx.spacer(),
        rx.text(v["harsh_count"], color=muted(), font_size="12px"),
        rx.text(" рывков", color=muted(), font_size="12px"),
        rx.text(v["score"], color=text(), font_size="14px", font_weight=ui.FONT_WEIGHT_SEMIBOLD),
        spacing="2",
        align="center",
        width="100%",
        padding="10px 12px",
        border_radius="9px",
        background=surface_alt(),
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
            rx.text(v["label"], color=text(), font_size="15px", font_weight=ui.FONT_WEIGHT_SEMIBOLD),
            rx.spacer(),
            rx.text(v["done_count"], color=text(), font_size="13px", font_weight=ui.FONT_WEIGHT_SEMIBOLD),
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
        width="100%",
    )


def settings_toggle_row(label, hint, value, on_change):
    return rx.hstack(
        rx.vstack(
            rx.text(label, color=text(), font_size="14px", font_weight=ui.FONT_WEIGHT_SEMIBOLD),
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


def backup_item_row(item):
    return rx.vstack(
        rx.hstack(
            rx.cond(
                item["valid"],
                fa_icon(tag="circle_check", size=16, color=ACCENT),
                fa_icon(tag="triangle_alert", size=16, color=ui.STATUS_RED_TEXT),
            ),
            rx.text(item["name"], color=text(), font_size="13px", font_weight=ui.FONT_WEIGHT_SEMIBOLD),
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
                        color=ui.STATUS_AMBER_TEXT,
                        font_size="12px",
                    ),
                    rx.box(),
                ),
                spacing="3",
                wrap="wrap",
                width="100%",
            ),
            rx.text(item["error"], color=ui.STATUS_RED_TEXT, font_size="12px"),
        ),
        align="start",
        spacing="2",
        width="100%",
        padding="12px",
        border=f"1px solid {border()}",
        border_radius="9px",
        background=surface_alt(),
    )


def fleet_text_field(label: str, value, on_change, input_type: str = "text"):
    return rx.vstack(
        rx.text(label, color=muted(), font_size="12px"),
        rx.input(value=value, on_change=on_change, type=input_type, width="100%"),
        spacing="1", align="start", width="100%",
    )


def _delivery_difference_color(difference):
    return rx.cond(
        difference < -1,
        ui.STATUS_RED_TEXT,
        rx.cond(difference > 1, ui.STATUS_GREEN_TEXT, text()),
    )


def delivery_summary_row(item):
    return rx.hstack(
        rx.text(item["name"], color=text(), font_weight=ui.FONT_WEIGHT_SEMIBOLD, width="100%"),
        rx.text(item["unit"], color=muted(), width="80px"),
        rx.text(item["planned"], color=text(), width="100px", text_align="right"),
        rx.text(item["delivered"], color=text(), width="100px", text_align="right"),
        rx.text(
            item["difference"],
            color=_delivery_difference_color(item["difference"]),
            width="100px",
            text_align="right",
        ),
        width="100%",
        padding="10px 0",
        border_bottom=f"1px solid {border()}",
        align="center",
    )


def delivery_line_row(line):
    return rx.hstack(
        rx.text(line["name"], color=text(), width="100%"),
        rx.text(line["unit"], color=muted(), width="70px"),
        rx.text("План: ", line["planned"], color=muted(), width="120px", text_align="right"),
        rx.text("Сдано: ", line["delivered"], color=text(), width="130px", text_align="right"),
        rx.text(
            "Разница: ", line["difference"],
            color=_delivery_difference_color(line["difference"]),
            width="140px",
            text_align="right",
        ),
        width="100%",
        padding="8px 0",
        border_bottom=f"1px solid {border()}",
        align="center",
        wrap="wrap",
    )


def delivery_item_card(item):
    return rx.el.details(
        rx.el.summary(
            rx.hstack(
                rx.vstack(
                    rx.text(item["store_name"], color=text(), font_weight=ui.FONT_WEIGHT_SEMIBOLD),
                    rx.text(item["route_label"], " · ", item["driver_name"], color=muted(), font_size="12px"),
                    align="start",
                    spacing="1",
                ),
                rx.spacer(),
                rx.text(item["completed_at"], color=muted(), font_size="12px"),
                width="100%",
                align="center",
            ),
            cursor="pointer",
        ),
        rx.vstack(
            rx.text(
                "Машина: ", item["vehicle_name"], " · ", item["vehicle_plate"],
                color=muted(), font_size="12px",
            ),
            rx.vstack(rx.foreach(item["lines"], delivery_line_row), width="100%", spacing="0"),
            width="100%",
            padding_top="12px",
            spacing="2",
            align="start",
        ),
        width="100%",
        padding="14px",
        border=f"1px solid {border()}",
        border_radius="10px",
        background=surface_alt(),
    )


def _return_view(document: dict) -> dict:
    item = dict(document)
    item["status_label"] = RETURN_STATUS_LABELS[document["status"]]
    item["driver_filter"] = f"{document['driver_name']} · {document['driver_id']}"
    item["lines"] = [
        {
            **line,
            **line["measurement"],
            "residual_kg": format_decimal(Decimal(line["loaded_net_kg"]) - Decimal(line["shipped_net_kg"])),
        }
        for line in document["lines"]
    ]
    item["history"] = [
        {
            "kind_label": RETURN_STATUS_LABELS.get(event["kind"], event["kind"]),
            "at": event["at"],
            "actor_name": event["actor"].get("name") or event["actor"]["id"],
            "comment": event.get("comment", ""),
            "details": " · ".join(
                f"{line['name']}: {line['measurement']['net_weight_kg']} кг; {line['reason']}; {line.get('comment', '')}"
                for line in event.get("lines", [])
            ),
        }
        for event in document["history"]
    ]
    return item


def return_line_row(line):
    return rx.vstack(
        rx.text(line["name"], font_weight=ui.FONT_WEIGHT_SEMIBOLD, color=ui.INK),
        rx.hstack(
            muted_text("Загружено: ", line["loaded_net_kg"], " кг"),
            muted_text("Принято магазинами: ", line["shipped_net_kg"], " кг"),
            muted_text("Остаток: ", line["residual_kg"], " кг"),
            rx.text("Возврат: ", line["net_weight_kg"], " кг", font_weight=ui.FONT_WEIGHT_SEMIBOLD),
            wrap="wrap", spacing="3", width="100%",
        ),
        muted_text("Ящики: ", line["box_count"], " · Тара: ", line["tare_weight_per_box_kg"], " кг/ящ. · Грязный вес: ", line["gross_weight_kg"], " кг"),
        rx.text("Причина: ", line["reason"], color=ui.INK_2, font_size="12px"),
        rx.cond(line["comment"] != "", muted_text(line["comment"]), rx.box()),
        width="100%", align="start", spacing="2", padding="12px 0",
        border_bottom=f"1px solid {ui.LINE_SOFT}",
    )


def help_chat_message_bubble(message):
    is_user = message["role"] == "user"
    return rx.box(
        rx.text(
            message["content"],
            color=rx.cond(is_user, ui.PURPLE_DARK, text()),
            font_size="13px",
            white_space="pre-wrap",
        ),
        padding="8px 12px",
        border_radius="10px",
        background=rx.cond(is_user, ui.PURPLE_BG, surface_alt()),
        max_width="85%",
        margin_left=rx.cond(is_user, "auto", "0"),
    )


def login_page():
    def field(label, identity, icon, password=False):
        return rx.el.div(rx.el.label(label, html_for=identity),
                         rx.el.div(design_icon(icon, 17),
                                   rx.el.input(id=identity, name="password" if password else "username",
                                               placeholder="Введите пароль" if password else "Введите логин",
                                               type="password" if password else "text", required=True,
                                               auto_complete="current-password" if password else "username",
                                               auto_focus=not password), class_name="login-input-wrap"), class_name="login-field")
    return rx.el.div(
        rx.el.div(class_name="animated-gradient", aria_hidden=True),
        rx.el.main(rx.el.section(
            rx.el.span(design_icon("lock", 24), class_name="login-symbol", aria_hidden=True),
            rx.el.div(rx.el.p("Рабочее пространство", class_name="eyebrow"),
                      rx.el.h1("Добро пожаловать", rx.el.span(".", class_name="heading-dot")),
                      rx.el.p("Войдите, чтобы управлять заказами и доставкой."), class_name="login-heading"),
            rx.el.form(field("Логин", "dashboard-login-username", "user"),
                       field("Пароль", "dashboard-login-password", "lock", password=True),
                       rx.el.p(id="dashboard-login-error", role="alert", aria_live="polite"),
                       rx.el.button("Войти", design_icon("arrow_right", 17), type="submit", id="dashboard-login-submit",
                                    class_name="button button-primary login-submit"),
                       on_submit=rx.call_script(DASHBOARD_LOGIN_JS), class_name="login-form", aria_label="Вход в рабочее пространство"),
            rx.el.p(design_icon("lock", 14), "Вход доступен только авторизованным пользователям.", class_name="login-notice"),
            design_theme_switch(), class_name="login-card"), class_name="login-main"),
        rx.el.footer(rx.el.span("Доставка · всё под контролем"), class_name="login-footer"),
        class_name="app dashboard-design login-app",
    )
