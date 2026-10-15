"""Orders presentation helpers."""
from functools import partial
from modules.config import MAX_ROUTES
from modules.route_drivers import ROUTE_AREAS
from orders_dashboard.constants import (
    SUPPORTED_EXCEL_LABEL,
    UPLOAD_ID,
)
from orders_dashboard.components import (
    border,
    design_button,
    design_heading,
    design_icon,
    design_page,
    design_panel_heading,
    muted,
    page_shell,
    panel_shell,
    panel_title,
    preview_metric,
    primary_button,
    result_metric,
    route_result,
    secondary_button,
    surface,
    surface_alt,
    text,
    topbar,
    upload_area,
)
from orders_dashboard.icons import fa_icon
import reflex as rx
from orders_dashboard import theme as ui


def order_panel(*, State):
    return rx.el.section(
        rx.el.div(rx.el.div(rx.el.h2("Новый заказ"), rx.el.p("От файла до обработки — три простых шага.")),
                  class_name="order-section-heading"),
        rx.el.ol(*[rx.el.li(rx.el.span(number), label) for number, label in
                   (("01", "Выбрать файл"), ("02", "Указать параметры"), ("03", "Подтвердить"))],
                 class_name="order-steps", aria_label="Порядок обработки"),
        rx.el.div(
            rx.el.section(design_panel_heading("01", "Файл заказа", "Выберите книгу Excel на компьютере"),
                upload_area(), rx.el.p(f"Поддерживаются {SUPPORTED_EXCEL_LABEL}", class_name="field-hint"),
                rx.el.div(rx.el.div(rx.el.strong("Загрузить выбранный файл"), rx.el.p("Выбор файла не означает загрузку в приложение.")),
                          rx.button(design_icon("upload", 17), "Загрузить",
                                    on_click=State.handle_upload(rx.upload_files(upload_id=UPLOAD_ID)),
                                    type="button", class_name="button button-secondary",
                                    disabled=State.is_processing),
                          class_name="upload-action"),
                rx.el.p("Загруженный файл: ", State.selected_file, class_name="field-hint"),
                class_name="order-panel upload-panel"),
            rx.el.section(design_panel_heading("02", "Параметры заказа", "Клиент и направление обработки"),
                rx.el.div(rx.el.label("Клиент", rx.el.span("Обязательно", class_name="required-label"), html_for="order-client", class_name="field-label"),
                          rx.input(id="order-client", value=State.order_client_name, on_change=State.set_order_client_name,
                                   placeholder="Укажите клиента", width="100%", class_name="text-input"),
                          rx.el.p("Клиент необходим для последующей загрузки заказа.", class_name="field-hint"), class_name="form-field"),
                rx.el.fieldset(rx.el.legend("Режим обработки", class_name="field-label"),
                    rx.el.div(*[rx.el.button(design_icon(icon), rx.el.strong(mode), rx.el.small(description),
                                            type="button", on_click=State.set_mode(mode), aria_pressed=State.mode == mode,
                                            class_name=rx.cond(State.mode == mode, "mode-card selected", "mode-card"))
                               for mode, icon, description in (("Город", "layout_grid", "Городские маршруты"), ("Область", "map", "Областные маршруты"))],
                              class_name="mode-options"), class_name="processing-mode"),
                rx.cond(State.mode_auto_note != "", rx.el.p(State.mode_auto_note, class_name="field-hint"), rx.fragment()),
                rx.el.div(rx.el.span(design_icon("file_text", 16), "Проверьте данные перед обработкой"),
                          design_button(rx.cond(State.is_previewing, "Анализ…", "Показать просмотр"), State.preview_order, disabled=State.is_processing),
                          class_name="preview-action"), class_name="order-panel parameters-panel"), class_name="order-grid"),
        rx.cond(State.duplicate_note != "", rx.el.p(State.duplicate_note, class_name="design-warning", role="status"), rx.fragment()),
        rx.cond(State.preview_ready, order_preview_panel(State=State), rx.fragment()),
        rx.el.section(rx.el.div(rx.el.span("03", class_name="panel-number"),
                                rx.el.div(rx.el.h3("Подтверждение обработки"), rx.el.p("Загрузите файл и проверьте параметры заказа.")),
                                class_name="confirmation-copy"),
                      design_button(rx.cond(State.is_processing, "Обработка…", "Подтвердить обработку"),
                                    State.open_route_assignment_dialog, "arrow_right", primary=True, disabled=State.is_processing),
                      class_name="confirmation-panel"),
        rx.el.div(design_icon("clock", 16), rx.el.span(State.status), class_name="order-status", role="status"),
        rx.cond(State.output_file != "", processing_summary(State=State), rx.fragment()),
        rx.cond(State.error_text != "", rx.code_block(State.error_text, language="python", width="100%", max_height="260px", overflow_y="auto"), rx.fragment()),
        class_name="order-workspace order-form", id="new-order",
    )


def order_preview_panel(*, State):
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
        rx.text(State.preview_file_info, color=text(), font_size="13px", font_weight=ui.FONT_WEIGHT_SEMIBOLD),
        rx.text(State.preview_sheet_info, color=muted(), font_size="12px"),
        rx.text(
            "Режим: ",
            State.preview_mode,
            color=text(),
            font_size="13px",
            font_weight=ui.FONT_WEIGHT_SEMIBOLD,
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
            rx.text("По маршрутам", color=text(), font_size="13px", font_weight=ui.FONT_WEIGHT_SEMIBOLD),
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
                rx.text("Найденные магазины", color=text(), font_size="13px", font_weight=ui.FONT_WEIGHT_SEMIBOLD),
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
                rx.text("Предупреждения", color=ui.STATUS_AMBER_TEXT, font_size="13px", font_weight=ui.FONT_WEIGHT_SEMIBOLD),
                rx.foreach(
                    State.preview_warnings,
                    lambda warning: rx.text(f"⚠ {warning}", color=text(), font_size="12px"),
                ),
                align="start",
                spacing="1",
                width="100%",
                padding="10px 12px",
                border=f"1px solid {ui.LINE}",
                border_radius="10px",
                background=ui.STATUS_AMBER_BG,
            ),
            rx.box(),
        ),
        rx.cond(
            State.preview_unknown_stores.length() > 0,
            rx.vstack(
                rx.text("Неизвестные магазины", color=text(), font_size="13px", font_weight=ui.FONT_WEIGHT_SEMIBOLD),
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
                rx.text("Конфликты", color=text(), font_size="13px", font_weight=ui.FONT_WEIGHT_SEMIBOLD),
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


def processing_summary(*, State):
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
                rx.cond(
                    index < State.active_route_count,
                    route_result(f"Маршрут №{index + 1}", State.route_totals[index]),
                    rx.box(),
                )
                for index in range(MAX_ROUTES)
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


def history_panel(*, State):
    return rx.vstack(
        rx.hstack(
            fa_icon(tag="history", size=17, color=text()),
            rx.heading("Последние обработки", color=text(), size="4"),
            spacing="2",
            align="center",
        ),
        rx.vstack(
            history_row(
                State.history_1_file,
                State.history_1_time,
                State.history_1_date_relation,
             State=State),
            history_row(
                State.history_2_file,
                State.history_2_time,
                State.history_2_date_relation,
             State=State),
            history_row(
                State.history_3_file,
                State.history_3_time,
                State.history_3_date_relation,
             State=State),
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


def history_row(filename, time, date_relation="", loading_href="", loading_label="Загрузить", *, State):
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
            rx.text(filename, color=text(), font_weight=ui.FONT_WEIGHT_SEMIBOLD, font_size="14px"),
            rx.text("Обработка заказа", color=muted(), font_size="12px"),
            align="start",
            spacing="1",
        ),
        rx.spacer(),
        rx.text(time, color=muted(), font_size="13px"),
        rx.cond(
            date_relation != "",
            rx.badge(date_relation, color_scheme="green", variant="soft"),
            rx.box(),
        ),
        rx.cond(
            loading_href != "",
            rx.link(
                rx.button(
                    loading_label,
                    height="32px",
                    padding="0 10px",
                    color=ui.PURPLE_DARK,
                    background=ui.PURPLE_BG,
                    border="1px solid transparent",
                    border_radius=ui.RADIUS_CONTROL,
                    font_size="12px",
                    cursor="pointer",
                ),
                href=loading_href,
            ),
            rx.box(),
        ),
        spacing="3",
        align="center",
        width="100%",
        padding="12px",
        border_radius="10px",
        background=surface_alt(),
        cursor="pointer",
        on_click=State.open_order_details(filename, time, date_relation),
        _hover={"background": ui.STATUS_GRAY_BG},
    )


def route_driver_row(index: int, area: str, *, State):
    return rx.hstack(
        rx.text(f"Маршрут №{index + 1}", color=text(), font_size="13px", font_weight=ui.FONT_WEIGHT_SEMIBOLD, min_width="110px"),
        rx.text(area, color=muted(), font_size="12px", min_width="150px"),
        rx.input(
            value=State.route_driver_names[index],
            on_change=lambda value: State.set_route_driver_name(index, value),
            width="220px",
            height="36px",
        ),
        spacing="3",
        align="center",
        width="100%",
    )


def route_drivers_panel(*, State):
    return panel_shell(
        panel_title("truck", "Водители по маршрутам"),
        rx.text(
            "Имя водителя показывается в колонтитуле печатных листов маршрута и во "
            "вкладке «Вес». Поменяйте местами, если водители на маршрутах поменялись.",
            color=muted(),
            font_size="12px",
        ),
        rx.vstack(
            *[
                rx.cond(index < State.active_route_count, route_driver_row(index, area, State=State), rx.box())
                for index, area in enumerate(ROUTE_AREAS)
            ],
            spacing="2",
            width="100%",
        ),
        rx.hstack(
            primary_button("Сохранить водителей", on_click=State.save_route_drivers_form, width="220px"),
            rx.text(State.route_drivers_status, color=muted(), font_size="13px"),
            spacing="4",
            align="center",
        ),
    )


def orders_page(*, State):
    return design_page(design_heading("Заказы", "Обработка Excel", "Загрузите файл, укажите клиента и выберите направление доставки."),
                       order_panel(State=State), class_name="orders-page")


def processed_file_row(item, *, State):
    return rx.hstack(
        fa_icon(tag="file_spreadsheet", size=17, color=muted()),
        rx.vstack(
            rx.text(
                item["filename"],
                color=text(),
                font_weight=ui.FONT_WEIGHT_SEMIBOLD,
                font_size="14px",
                word_break="break-all",
            ),
            rx.text(
                item["folder"], " · ", item["modified_at"], " · ", item["size_label"],
                color=muted(),
                font_size="12px",
            ),
            align="start",
            spacing="1",
            min_width="0",
        ),
        rx.spacer(),
        secondary_button(
            "Скачать",
            on_click=State.download_processed_file(item["relative_path"]),
            width="100px",
        ),
        spacing="3",
        align="center",
        width="100%",
        padding="12px",
        border_radius="10px",
        background=surface_alt(),
    )


def history_page(*, State):
    return page_shell(
        topbar("История", "Обработанные заказы и файлы для скачивания."),
        panel_shell(
            panel_title("history", "История файлов"),
            rx.text(State.processed_file_status, color=ui.PURPLE_DARK, font_size="13px"),
            rx.cond(
                State.history_items.length() > 0,
                rx.vstack(
                    rx.foreach(
                        State.history_items,
                        lambda item: history_row(
                            item["file"],
                            item["time"],
                            item["date_relation"],
                            item["loading_href"],
                            item["loading_label"],
                         State=State),
                    ),
                    spacing="2",
                    width="100%",
                ),
                rx.fragment(),
            ),
            rx.cond(
                State.processed_file_items.length() > 0,
                rx.vstack(
                    rx.foreach(State.processed_file_items, lambda item: processed_file_row(item, State=State)),
                    spacing="2",
                    width="100%",
                ),
                rx.fragment(),
            ),
            rx.cond(
                (State.history_items.length() == 0) & (State.processed_file_items.length() == 0),
                rx.text("Обработанных файлов пока нет", color=muted(), font_size="13px"),
                rx.fragment(),
            ),
        ),
    )
