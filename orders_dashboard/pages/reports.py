"""Reports presentation helpers."""
from functools import partial
from orders_dashboard.constants import (
    ACCENT,
    INVOICE_OCR_UPLOAD_ID,
    RETURN_STATUS_LABELS,
    WEIGHT_ROUTES,
    WEIGHT_ROUTE_FILTER_OPTIONS,
    WEIGHT_ROUTE_OPTIONS,
    WEIGHT_STAGE_FILTER_OPTIONS,
    WEIGHT_STAGE_OPTIONS,
)
from modules.invoice_ocr import MAX_PHOTOS
from modules.weight_log import STAGE_STORE_SHIPMENT
from orders_dashboard.components import (
    border,
    delivery_item_card,
    delivery_summary_row,
    invoice_ocr_journal_row,
    metric_card,
    muted,
    muted_text,
    page_shell,
    panel_shell,
    panel_title,
    primary_button,
    return_line_row,
    secondary_button,
    segmented_control,
    stat_card,
    status_pill,
    surface,
    surface_alt,
    text,
    topbar,
    weight_field,
    weight_select_field,
    weight_stat,
)
from orders_dashboard.icons import fa_icon
import reflex as rx
from orders_dashboard import theme as ui


def weight_row(item, *, State):
    return rx.hstack(
        rx.vstack(
            rx.text(item["name"], color=text(), font_weight=ui.FONT_WEIGHT_SEMIBOLD, font_size="14px"),
            rx.text(item["date"], color=muted(), font_size="11px"),
            align="start",
            spacing="1",
            min_width="180px",
        ),
        rx.cond(
            item["stage"] != "",
            weight_stat("Этап", item["stage"]),
            weight_stat("Этап", "—"),
        ),
        weight_stat("Ящиков", item["box_count"]),
        weight_stat("Средний вес ящика, кг", item["avg_weight"]),
        rx.cond(
            item["exact_weight"] != "",
            weight_stat("Грязный вес, кг", item["exact_weight"]),
            weight_stat("Грязный вес, кг", "—"),
        ),
        weight_stat("Чистый вес, кг", item["total"]),
        rx.cond(
            item["order_file"] != "",
            weight_stat("Заказ", item["order_file"]),
            weight_stat("Заказ", "—"),
        ),
        rx.cond(
            item["route"] != "",
            weight_stat("Маршрут / водитель", item["route"], " (", item["driver"], ")"),
            weight_stat("Маршрут / водитель", "—"),
        ),
        rx.cond(
            item["store"] != "",
            weight_stat("Магазин", item["store"]),
            rx.box(),
        ),
        rx.spacer(),
        rx.cond(
            State.weight_delete_confirm_id == item["id"],
            rx.hstack(
                rx.text("Удалить?", color=muted(), font_size="12px"),
                rx.button(
                    fa_icon(tag="circle_check", size=15, color=ui.STATUS_RED_TEXT),
                    on_click=State.confirm_delete_weight_row,
                    size="1",
                    variant="ghost",
                    cursor="pointer",
                ),
                rx.button(
                    fa_icon(tag="circle_x", size=15),
                    on_click=State.cancel_delete_weight_row,
                    size="1",
                    variant="ghost",
                    color=muted(),
                    cursor="pointer",
                ),
                spacing="1",
                align="center",
            ),
            rx.hstack(
                rx.button(
                    fa_icon(tag="edit", size=13),
                    on_click=State.start_edit_weight_row(item["id"]),
                    size="1",
                    variant="ghost",
                    color=muted(),
                    cursor="pointer",
                ),
                rx.button(
                    fa_icon(tag="x", size=13),
                    on_click=State.ask_delete_weight_row(item["id"]),
                    size="1",
                    variant="ghost",
                    color=muted(),
                    cursor="pointer",
                ),
                spacing="1",
            ),
        ),
        spacing="4",
        align="center",
        width="100%",
        padding="10px 12px",
        border_radius="10px",
        background=surface_alt(),
        wrap="wrap",
    )


def weight_name_autocomplete_option(item_id, name, *, State):
    return rx.box(
        rx.text(name, font_size="13px", color=text()),
        on_mouse_down=State.accept_weight_name_suggestion(item_id, name),
        padding="6px 10px",
        cursor="pointer",
        width="100%",
        border_radius="6px",
        _hover={"background": surface_alt()},
    )


def weight_draft_row(item, *, State):
    return rx.hstack(
        rx.box(
            rx.input(
                value=item["name"],
                on_change=lambda value: State.set_weight_draft_field(item["id"], "name", value),
                on_blur=State.suggest_weight_draft_avg(item["id"]),
                on_key_down=lambda key, info: State.handle_weight_name_key(item["id"], key),
                placeholder="Наименование",
                width="100%",
            ),
            rx.cond(
                (State.weight_autocomplete_row == item["id"]) & (State.weight_autocomplete_matches.length() > 0),
                rx.vstack(
                    rx.foreach(
                        State.weight_autocomplete_matches,
                        lambda name: weight_name_autocomplete_option(item["id"], name, State=State),
                    ),
                    position="absolute",
                    top="100%",
                    left="0",
                    margin_top="4px",
                    width="240px",
                    background=surface(),
                    border=f"1px solid {border()}",
                    border_radius="8px",
                    padding="4px",
                    spacing="0",
                    z_index="20",
                ),
                rx.box(),
            ),
            position="relative",
            width="100%",
            min_width="190px",
        ),
        rx.input(
            value=item["box_count"],
            on_change=lambda value: State.set_weight_draft_field(item["id"], "box_count", value),
            placeholder="Ящиков",
            width="100px",
        ),
        rx.input(
            value=item["avg_weight"],
            on_change=lambda value: State.set_weight_draft_field(item["id"], "avg_weight", value),
            placeholder="Ср. вес ящика, кг",
            width="130px",
        ),
        rx.input(
            value=item["exact_weight"],
            on_change=lambda value: State.set_weight_draft_field(item["id"], "exact_weight", value),
            placeholder="Грязный вес",
            width="120px",
        ),
        rx.input(
            value=item["net_weight"],
            on_change=lambda value: State.set_weight_draft_field(item["id"], "net_weight", value),
            placeholder="Чистый вес (уже посчитан)",
            width="170px",
        ),
        rx.cond(
            State.weight_stage == STAGE_STORE_SHIPMENT,
            rx.select(
                State.weight_draft_store_options,
                value=item["store"],
                on_change=lambda value: State.set_weight_draft_field(item["id"], "store", value),
                width="180px",
            ),
            rx.box(),
        ),
        rx.button(
            fa_icon(tag="x", size=13),
            on_click=State.remove_weight_draft_row(item["id"]),
            variant="ghost",
            color=muted(),
            cursor="pointer",
            aria_label="Удалить строку",
        ),
        width="100%",
        spacing="2",
        align="center",
        wrap="wrap",
    )


def weight_name_suggestion_chip(name, *, State):
    return rx.button(
        name,
        on_click=State.add_weight_draft_row_with_name(name),
        size="1",
        variant="soft",
        color_scheme="gray",
        cursor="pointer",
        border_radius="999px",
    )


def weight_page(*, State):
    return page_shell(
        topbar(
            "Вес",
            "Отдельный журнал взвешиваний. Загрузка конкретного рейса вводится на странице «Загрузка и сверка».",
        ),
        rx.el.details(
            rx.el.summary("Как рассчитывается вес", class_name="dispatch-store-summary"),
            muted_text("Нетто = брутто − ящики × тара одного ящика. В этом журнале также можно ввести известный чистый вес напрямую. Этапы: загрузка, остаток вечером и отгрузка по магазинам."),
            width="100%",
        ),
        panel_shell(
            panel_title("scale", "Этап"),
            segmented_control(WEIGHT_STAGE_OPTIONS, State.weight_stage, State.set_weight_stage),
        ),
        panel_shell(
            panel_title("route", "Привязка"),
            rx.hstack(
                weight_select_field("Заказ", State.weight_order, State.set_weight_order, State.weight_order_options),
                weight_select_field("Маршрут", State.weight_route, State.set_weight_route, WEIGHT_ROUTE_OPTIONS),
                spacing="3",
                width="100%",
                align="end",
            ),
        ),
        panel_shell(
            panel_title("list", "Позиции"),
            rx.cond(
                State.weight_name_suggestions.length() > 0,
                rx.vstack(
                    rx.hstack(
                        muted_text("Позиции из заказа (", State.weight_name_suggestions.length(), ")"),
                        rx.text(
                            rx.cond(State.weight_suggestions_expanded, "Скрыть", "Показать"),
                            on_click=State.toggle_weight_suggestions,
                            color=ACCENT,
                            font_size="12px",
                            font_weight=ui.FONT_WEIGHT_SEMIBOLD,
                            cursor="pointer",
                        ),
                        spacing="3",
                        align="center",
                    ),
                    rx.cond(
                        State.weight_suggestions_expanded,
                        rx.hstack(
                            rx.foreach(State.weight_name_suggestions, lambda name: weight_name_suggestion_chip(name, State=State)),
                            spacing="2",
                            wrap="wrap",
                        ),
                        rx.box(),
                    ),
                    align="start",
                    spacing="2",
                    width="100%",
                ),
                rx.box(),
            ),
            rx.vstack(
                rx.foreach(State.weight_draft_rows, lambda item: weight_draft_row(item, State=State)),
                spacing="2",
                width="100%",
            ),
            rx.hstack(
                secondary_button("+ Добавить строку", on_click=State.add_weight_draft_row, width="180px"),
                primary_button("Сохранить всё", on_click=State.submit_weight_draft_rows, width="160px"),
                rx.text(State.weight_status, color=ui.STATUS_RED_TEXT, font_size="13px"),
                spacing="4",
                align="center",
            ),
        ),
        panel_shell(
            rx.hstack(
                panel_title("list", "Записи"),
                rx.spacer(),
                rx.text("Чистый вес по списку: ", State.weight_total, " кг", color=text(), font_size="13px", font_weight=ui.FONT_WEIGHT_SEMIBOLD),
                width="100%",
                align="center",
            ),
            rx.hstack(
                weight_select_field(
                    "Фильтр по этапу", State.weight_filter_stage, State.set_weight_filter_stage,
                    WEIGHT_STAGE_FILTER_OPTIONS,
                ),
                weight_select_field(
                    "Фильтр по заказу", State.weight_filter_order, State.set_weight_filter_order,
                    State.weight_order_filter_options,
                ),
                weight_select_field(
                    "Фильтр по маршруту", State.weight_filter_route, State.set_weight_filter_route,
                    WEIGHT_ROUTE_FILTER_OPTIONS,
                ),
                spacing="3",
                width="100%",
                align="end",
            ),
            rx.hstack(
                stat_card(
                    "truck", "blue", "Загрузка",
                    State.weight_reconciliation["loaded"] + " кг", rx.box(),
                ),
                stat_card(
                    "route", "green", "Отгрузка по магазинам",
                    State.weight_reconciliation["shipped"] + " кг", rx.box(),
                ),
                stat_card(
                    "boxes", "violet", "Выгрузка (остаток)",
                    State.weight_reconciliation["unloaded"] + " кг", rx.box(),
                ),
                rx.cond(
                    State.weight_reconciliation["has_difference"] != "",
                    stat_card(
                        "triangle_alert", "red", "Разница",
                        State.weight_reconciliation["difference"] + " кг",
                        rx.text("Не сошлось — проверьте позиции", color=ui.STATUS_RED_TEXT, font_size="11px", font_weight=ui.FONT_WEIGHT_SEMIBOLD),
                    ),
                    stat_card(
                        "circle_check", "green", "Разница",
                        "0 кг",
                        rx.text("Сошлось", color=muted(), font_size="11px"),
                    ),
                ),
                spacing="3",
                width="100%",
                wrap="wrap",
            ),
            rx.cond(
                State.weight_visible_rows.length() > 0,
                rx.vstack(
                    rx.foreach(State.weight_visible_rows, lambda item: weight_row(item, State=State)),
                    spacing="2",
                    width="100%",
                ),
                rx.text("Совпадающих записей нет", color=muted(), font_size="13px"),
            ),
        ),
    )


def invoice_ocr_line(item, *, State):
    return rx.hstack(
        rx.input(
            value=item["store_number"],
            on_change=lambda value: State.set_invoice_ocr_line_field(item["id"], "store_number", value),
            placeholder="Магазин",
            width="130px",
        ),
        rx.input(
            value=item["name"],
            on_change=lambda value: State.set_invoice_ocr_line_field(item["id"], "name", value),
            placeholder="Наименование",
            width="100%",
            min_width="190px",
        ),
        rx.input(
            value=item["unit"],
            on_change=lambda value: State.set_invoice_ocr_line_field(item["id"], "unit", value),
            placeholder="Ед.",
            width="90px",
        ),
        rx.input(
            value=item["quantity"],
            on_change=lambda value: State.set_invoice_ocr_line_field(item["id"], "quantity", value),
            placeholder="Кол-во",
            width="110px",
        ),
        rx.input(
            value=item["unit_price"],
            on_change=lambda value: State.set_invoice_ocr_line_field(item["id"], "unit_price", value),
            placeholder="Цена",
            width="110px",
        ),
        rx.input(
            value=item["line_total"],
            on_change=lambda value: State.set_invoice_ocr_line_field(item["id"], "line_total", value),
            placeholder="Сумма",
            width="120px",
        ),
        rx.button(
            fa_icon(tag="x", size=13),
            on_click=State.remove_invoice_ocr_line(item["id"]),
            variant="ghost",
            color=muted(),
            cursor="pointer",
            aria_label="Удалить строку",
        ),
        width="100%",
        spacing="2",
        align="center",
        wrap="wrap",
    )


def invoice_ocr_page(*, State):
    return page_shell(
        topbar(
            "OCR накладных",
            "Выберите заказ и маршрут, загрузите фотографии и проверьте распознанные позиции перед сохранением.",
        ),
        panel_shell(
            panel_title("route", "1. Привязка"),
            rx.hstack(
                weight_select_field(
                    "Обработанный заказ",
                    State.invoice_ocr_order,
                    State.set_invoice_ocr_order,
                    State.invoice_ocr_order_options,
                ),
                weight_select_field(
                    "Маршрут",
                    State.invoice_ocr_route,
                    State.set_invoice_ocr_route,
                    WEIGHT_ROUTES,
                ),
                spacing="3",
                width="100%",
                align="end",
            ),
            rx.cond(
                State.invoice_ocr_order_options.length() == 0,
                rx.text(
                    "Сначала обработайте хотя бы один заказ — только обработанные заказы можно привязать к накладной.",
                    color=muted(),
                    font_size="12px",
                ),
                rx.box(),
            ),
        ),
        panel_shell(
            panel_title("camera", "2. Фотографии накладной"),
            rx.upload(
                rx.vstack(
                    fa_icon(tag="camera", size=24, color=ACCENT),
                    rx.text("Выберите фотографии JPG, PNG или WEBP", color=text(), font_weight=ui.FONT_WEIGHT_SEMIBOLD),
                    rx.text(
                        f"До {MAX_PHOTOS} фотографий, не более 10 МБ каждая. OCR запускается только после нажатия кнопки.",
                        color=muted(),
                        font_size="12px",
                    ),
                    rx.vstack(
                        rx.foreach(
                            rx.selected_files(INVOICE_OCR_UPLOAD_ID),
                            lambda file: rx.text(file, color=ACCENT, font_size="12px"),
                        ),
                        align="start",
                        spacing="1",
                        width="100%",
                    ),
                    align="center",
                    spacing="2",
                    width="100%",
                ),
                id=INVOICE_OCR_UPLOAD_ID,
                accept={
                    "image/jpeg": [".jpg", ".jpeg"],
                    "image/png": [".png"],
                    "image/webp": [".webp"],
                },
                max_files=MAX_PHOTOS,
                border=f"1px dashed {border()}",
                border_radius="10px",
                background=surface_alt(),
                padding="20px",
                width="100%",
                cursor="pointer",
            ),
            rx.hstack(
                primary_button(
                    rx.cond(State.invoice_ocr_busy, "Распознаю...", "Распознать фотографии"),
                    on_click=State.recognize_invoice_photos(
                        rx.upload_files(upload_id=INVOICE_OCR_UPLOAD_ID)
                    ),
                    disabled=State.invoice_ocr_busy,
                    width="230px",
                ),
                rx.text(State.invoice_ocr_status, color=muted(), font_size="13px"),
                spacing="4",
                align="center",
                wrap="wrap",
            ),
        ),
        rx.cond(
            State.invoice_ocr_draft_id != "",
            panel_shell(
                rx.hstack(
                    panel_title("list", "3. Проверка перед сохранением"),
                    rx.spacer(),
                    rx.text("Итого: ", State.invoice_ocr_total, color=text(), font_weight=ui.FONT_WEIGHT_SEMIBOLD),
                    width="100%",
                    align="center",
                ),
                rx.text(
                    "OCR может ошибаться. Проверьте все наименования, единицы, количество, цены и суммы.",
                    color=ui.STATUS_AMBER_TEXT,
                    font_size="12px",
                    font_weight=ui.FONT_WEIGHT_SEMIBOLD,
                ),
                weight_field(
                    "Номер магазина",
                    State.invoice_ocr_store_number,
                    State.set_invoice_ocr_store_number,
                    "Например, ФМ 16",
                ),
                rx.text("Исходный текст OCR", color=text(), font_size="13px", font_weight=ui.FONT_WEIGHT_SEMIBOLD),
                rx.box(
                    rx.text(
                        State.invoice_ocr_raw_text,
                        color=text(),
                        white_space="pre-wrap",
                        font_size="12px",
                    ),
                    width="100%",
                    max_height="180px",
                    overflow_y="auto",
                    padding="12px",
                    border_radius="10px",
                    background=surface_alt(),
                ),
                rx.hstack(
                    rx.text("Магазин", color=muted(), font_size="11px", width="130px"),
                    rx.text("Наименование", color=muted(), font_size="11px", min_width="190px", width="100%"),
                    rx.text("Ед.", color=muted(), font_size="11px", width="90px"),
                    rx.text("Количество", color=muted(), font_size="11px", width="110px"),
                    rx.text("Цена за ед.", color=muted(), font_size="11px", width="110px"),
                    rx.text("Сумма", color=muted(), font_size="11px", width="120px"),
                    rx.box(width="32px"),
                    width="100%",
                    spacing="2",
                    wrap="wrap",
                ),
                rx.vstack(
                    rx.foreach(State.invoice_ocr_rows, lambda item: invoice_ocr_line(item, State=State)),
                    spacing="2",
                    width="100%",
                ),
                secondary_button("Добавить строку", on_click=State.add_invoice_ocr_line, width="170px"),
                rx.hstack(
                    primary_button(
                        "Сохранить накладную",
                        on_click=State.save_invoice_ocr_draft,
                        disabled=State.invoice_ocr_busy,
                        width="210px",
                    ),
                    secondary_button(
                        "Очистить черновик",
                        on_click=State.clear_invoice_ocr_draft,
                        disabled=State.invoice_ocr_busy,
                        width="180px",
                    ),
                    spacing="3",
                    wrap="wrap",
                ),
            ),
            rx.box(),
        ),
        panel_shell(
            panel_title("history", "Сохранённые накладные"),
            rx.cond(
                State.invoice_ocr_entries.length() > 0,
                rx.vstack(
                    rx.foreach(State.invoice_ocr_entries, invoice_ocr_journal_row),
                    spacing="2",
                    width="100%",
                    max_height="360px",
                    overflow_y="auto",
                ),
                rx.text("Сохранённых накладных пока нет", color=muted(), font_size="13px"),
            ),
        ),
    )


def order_invoice_row(item, linked: bool, *, State):
    return rx.vstack(
        rx.hstack(
            fa_icon(tag="file_pdf", size=16, color=ui.STATUS_BLUE_TEXT),
            rx.text(item["file"], color=text(), font_size="13px", font_weight=ui.FONT_WEIGHT_SEMIBOLD),
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
            secondary_button(
                "Скачать",
                on_click=State.download_linked_invoice_file(item["file"]),
                width="120px",
            ),
            spacing="2",
            wrap="wrap",
        ),
        align="start",
        spacing="2",
        width="100%",
        padding="14px",
        border=f"1px solid {border()}",
        border_radius="10px",
        background=surface_alt(),
    )


def order_source_file_row(*, State):
    return rx.vstack(
        rx.hstack(
            fa_icon(tag="file_spreadsheet", size=16, color=ui.STATUS_BLUE_TEXT),
            rx.text(State.selected_order, color=text(), font_size="13px", font_weight=ui.FONT_WEIGHT_SEMIBOLD),
            width="100%",
            align="center",
        ),
        rx.text("Исходный файл заказа", color=muted(), font_size="12px"),
        secondary_button(
            "Скачать",
            on_click=State.download_order_source_file,
            width="120px",
        ),
        align="start",
        spacing="2",
        width="100%",
        padding="14px",
        border=f"1px solid {border()}",
        border_radius="10px",
        background=surface_alt(),
    )


def order_details_drawer(*, State):
    return rx.cond(
        State.order_details_open,
        rx.fragment(
            rx.box(
                position="fixed",
                inset="0",
                background=ui.OVERLAY,
                z_index="90",
                on_click=State.close_order_details,
            ),
            rx.vstack(
                rx.hstack(
                    rx.vstack(
                        rx.text("ЗАКАЗ", color=muted(), font_size="11px", font_weight=ui.FONT_WEIGHT_SEMIBOLD),
                        rx.heading(State.selected_order, color=text(), size="5"),
                        rx.hstack(
                            rx.text(
                                State.selected_order_time_label,
                                ": ",
                                State.selected_order_time,
                                color=muted(),
                                font_size="12px",
                            ),
                            rx.cond(
                                State.selected_order_date_relation != "",
                                rx.badge(
                                    State.selected_order_date_relation,
                                    color_scheme="green",
                                    variant="soft",
                                ),
                                rx.box(),
                            ),
                            spacing="2",
                            align="center",
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
                        rx.heading("Файл заказа", color=text(), size="4"),
                        order_source_file_row(State=State),
                        rx.divider(),
                        rx.heading("Привязанные накладные", color=text(), size="4"),
                        rx.cond(
                            State.order_invoices.length() > 0,
                            rx.vstack(
                                rx.foreach(
                                    State.order_invoices,
                                    lambda item: order_invoice_row(item, True, State=State),
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
                                    lambda item: order_invoice_row(item, False, State=State),
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
                                    lambda item: order_invoice_row(item, False, State=State),
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
                padding="18px",
                background=surface(),
                border_left=f"1px solid {border()}",
                z_index="100",
            ),
        ),
        rx.box(),
    )


def delivery_page(*, State):
    return page_shell(
        topbar(
            "Сданный товар",
            "Фактические количества из завершённых магазинов. План, сдано и разница считаются отдельно для каждого товара и единицы измерения.",
        ),
        rx.hstack(
            stat_card("circle_check", "green", "Завершено магазинов", State.delivery_completed_stores, rx.box()),
            stat_card("list", "violet", "Товарных строк", State.delivery_line_count, rx.box()),
            width="100%",
            spacing="3",
            wrap="wrap",
        ),
        panel_shell(
            panel_title("list", "Свод по товарам"),
            rx.hstack(
                rx.text("Товар", color=muted(), font_size="12px", width="100%"),
                rx.text("Ед.", color=muted(), font_size="12px", width="80px"),
                rx.text("План", color=muted(), font_size="12px", width="100px", text_align="right"),
                rx.text("Сдано", color=muted(), font_size="12px", width="100px", text_align="right"),
                rx.text("Разница", color=muted(), font_size="12px", width="100px", text_align="right"),
                width="100%",
                align="center",
            ),
            rx.cond(
                State.delivery_summary.length() > 0,
                rx.vstack(rx.foreach(State.delivery_summary, delivery_summary_row), width="100%", spacing="0"),
                muted_text("Завершённых магазинов пока нет."),
            ),
        ),
        panel_shell(
            panel_title("package", "Завершённые магазины"),
            rx.cond(
                State.delivery_items.length() > 0,
                rx.vstack(rx.foreach(State.delivery_items, delivery_item_card), width="100%", spacing="2"),
                muted_text("Завершённых магазинов пока нет."),
            ),
        ),
    )


def return_item_card(item, *, State):
    return rx.el.details(
        rx.el.summary(
            rx.hstack(
                rx.vstack(
                    rx.text("Заказ ", item["order_number"], " · ", item["route_label"], font_weight=ui.FONT_WEIGHT_SEMIBOLD),
                    muted_text(item["driver_name"], " · ", item["vehicle_plate"]),
                    muted_text(item["submitted_at"], " · версия ", item["version"]),
                    align="start", spacing="1",
                ),
                rx.spacer(),
                rx.text(item["total_net_kg"], " кг", font_weight=ui.FONT_WEIGHT_SEMIBOLD),
                status_pill(item["status_label"]),
                width="100%", wrap="wrap", align="center", spacing="3",
            ),
            cursor="pointer",
        ),
        rx.vstack(
            rx.foreach(item["lines"].to(list[dict]), return_line_row),
            rx.cond(
                item["status"] == "submitted",
                rx.hstack(
                    primary_button("Принять возврат", on_click=State.begin_return_decision(item["id"], "accepted")),
                    secondary_button("Отклонить", on_click=State.begin_return_decision(item["id"], "rejected")),
                    wrap="wrap", spacing="2",
                ),
                rx.box(),
            ),
            rx.text("История документа", font_weight=ui.FONT_WEIGHT_SEMIBOLD),
            rx.foreach(
                item["history"].to(list[dict]),
                lambda event: rx.vstack(
                    muted_text(event["at"], " · ", event["kind_label"], " · ", event["actor_name"]),
                    rx.cond(event["comment"] != "", rx.text(event["comment"], font_size="12px"), rx.box()),
                    rx.cond(event["details"] != "", muted_text(event["details"]), rx.box()),
                    width="100%", align="start", spacing="1",
                ),
            ),
            padding_top="12px", spacing="3", width="100%", align="start",
        ),
        width="100%", padding="14px", border=f"1px solid {ui.LINE}",
        border_radius=ui.RADIUS_CONTROL, background=ui.PANEL,
    )


def returns_page(*, State):
    return page_shell(
        topbar("Возвраты", "Остаток текущего рейса. Принятие подтверждает поступление товара на склад, но не меняет недостачу заказа."),
        rx.hstack(
            rx.vstack(
                muted_text("Статус"),
                rx.select(["Все", *RETURN_STATUS_LABELS.values()], value=State.returns_status_filter, on_change=State.set_returns_filter("status")),
                align="start", spacing="1",
            ),
            rx.vstack(
                muted_text("Маршрут"),
                rx.select(State.returns_route_options, value=State.returns_route_filter, on_change=State.set_returns_filter("route")),
                align="start", spacing="1",
            ),
            rx.vstack(
                muted_text("Водитель"),
                rx.select(State.returns_driver_options, value=State.returns_driver_filter, on_change=State.set_returns_filter("driver"), width="100%"),
                align="start", spacing="1", width="300px", max_width="100%",
            ),
            rx.vstack(
                muted_text("Подача с"),
                rx.input(type="date", value=State.returns_date_from, on_change=State.set_returns_filter("date_from"), aria_label="Подача с"),
                align="start", spacing="1",
            ),
            rx.vstack(
                muted_text("Подача по"),
                rx.input(type="date", value=State.returns_date_to, on_change=State.set_returns_filter("date_to"), aria_label="Подача по"),
                align="start", spacing="1",
            ),
            secondary_button("Обновить", on_click=State.load_returns_report),
            wrap="wrap", align="end", spacing="3", width="100%",
        ),
        rx.grid(
            metric_card("На проверке", State.returns_totals["submitted"]),
            metric_card("Принято", State.returns_totals["accepted"]),
            metric_card("Отклонено", State.returns_totals["rejected"]),
            columns=rx.breakpoints(initial="1", sm="3"), width="100%", spacing="3",
        ),
        rx.grid(
            metric_card("Заявлено к проверке, кг", State.returns_totals["pending_kg"]),
            metric_card("Принято на склад, кг", State.returns_totals["accepted_kg"]),
            columns=rx.breakpoints(initial="1", sm="2"), width="100%", spacing="3",
        ),
        rx.cond(State.returns_message != "", rx.text(State.returns_message, role="status"), rx.box()),
        panel_shell(
            panel_title("package", "Журнал возвратов"),
            muted_text("Показатели рассчитаны по выбранным фильтрам. Отклонение заявки не является списанием товара."),
            rx.cond(
                State.returns_filtered.length() > 0,
                rx.vstack(rx.foreach(State.returns_filtered, lambda item: return_item_card(item, State=State)), width="100%", spacing="3"),
                muted_text("Возвратов по выбранным условиям нет."),
            ),
        ),
        rx.alert_dialog.root(
            rx.alert_dialog.content(
                rx.alert_dialog.title(rx.cond(State.returns_decision_kind == "accepted", "Подтвердить приёмку?", "Отклонить возврат?")),
                rx.alert_dialog.description(rx.cond(
                    State.returns_decision_kind == "accepted",
                    "Подтвердите, что все указанные товары и вес фактически приняты складом. Решение нельзя отменить.",
                    "Укажите, что нужно исправить. Водитель сможет отправить новую версию документа.",
                )),
                rx.text_area(
                    value=State.returns_decision_comment, on_change=State.set_return_decision_comment,
                    placeholder="Комментарий (обязателен при отклонении)", max_length=2000,
                    aria_label="Комментарий администратора", width="100%", margin_top="12px",
                ),
                rx.text(State.returns_message, role="status", margin_top="8px"),
                rx.hstack(
                    secondary_button("Отмена", on_click=State.cancel_return_decision),
                    primary_button("Подтвердить решение", on_click=State.confirm_return_decision),
                    wrap="wrap", justify="end", margin_top="12px",
                ),
                max_width="460px",
            ),
            open=State.returns_decision_id != "",
        ),
    )


def route_assignment_row(item, index, *, State):
    return rx.hstack(
        rx.text(item["label"], color=text(), font_weight=ui.FONT_WEIGHT_SEMIBOLD, min_width="130px"),
        rx.select(
            State.fleet_driver_options,
            value=item["driver_name"],
            on_change=lambda value: State.set_route_assignment_driver(index, value),
            placeholder="Водитель не назначен",
            width="100%",
        ),
        rx.vstack(
            rx.select(
                State.fleet_vehicle_options,
                value=item["vehicle_plate"],
                on_change=lambda value: State.set_route_assignment_vehicle(index, value),
                placeholder="Транспорт не назначен",
                width="100%",
            ),
            rx.cond(
                item["vehicle_id"] != "",
                rx.vstack(
                    rx.text("Марка / модель: ", item["vehicle_name"], color=muted(), font_size="12px"),
                    rx.text("Госномер: ", item["vehicle_plate"], color=muted(), font_size="12px"),
                    rx.text(
                        "Краткое описание: ",
                        rx.cond(item["vehicle_description"] != "", item["vehicle_description"], "Не указано"),
                        color=muted(),
                        font_size="12px",
                    ),
                    spacing="1",
                    width="100%",
                ),
                rx.box(),
            ),
            spacing="1",
            width="100%",
        ),
        width="100%", spacing="3", align="center", wrap="wrap",
    )


def route_assignment_dialog(*, State):
    return rx.cond(
        State.route_assignment_open,
        rx.box(
            rx.box(
                rx.vstack(
                    rx.text("Назначение рейсов", color=text(), font_size="20px", font_weight=ui.FONT_WEIGHT_SEMIBOLD),
                    rx.text("Выберите водителя и транспорт для каждого активного маршрута. Поля можно оставить пустыми.", color=muted(), font_size="13px"),
                    rx.vstack(rx.foreach(State.route_assignments, lambda item, index: route_assignment_row(item, index, State=State)), width="100%", spacing="3"),
                    rx.hstack(
                        secondary_button("Отмена", on_click=State.cancel_route_assignments),
                        primary_button("Обработать заказ", on_click=State.confirm_route_assignments),
                        justify="end", width="100%", spacing="3",
                    ),
                    spacing="4", width="100%", align="start",
                ),
                width="min(760px, calc(100vw - 32px))", max_height="calc(100vh - 32px)", overflow_y="auto", padding="24px", border_radius="14px", background=surface(), box_shadow="0 16px 48px rgba(0,0,0,.28)",
            ),
            position="fixed", inset="0", z_index="1000", background="rgba(0,0,0,.45)", display="flex", align_items="center", justify_content="center", padding="16px",
        ),
        rx.box(),
    )
