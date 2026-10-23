"""Mail presentation helpers."""
from functools import partial
from orders_dashboard.constants import (
    ACCENT,
    MAIL_APP_PASSWORD_URL,
)
from modules.mail_watcher import KIND_MESSAGE
from orders_dashboard.components import (
    border,
    design_button,
    design_heading,
    design_icon,
    design_mail_panel,
    design_page,
    mail_verdict_badge,
    muted,
    panel_shell,
    panel_title,
    primary_button,
    secondary_button,
    segment_button,
    segmented_control,
    surface_alt,
    text,
)
from orders_dashboard.icons import fa_icon
import reflex as rx
from orders_dashboard import theme as ui


def mail_setup_hint(*, State):
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
                font_weight=ui.FONT_WEIGHT_SEMIBOLD,
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
                font_weight=ui.FONT_WEIGHT_SEMIBOLD,
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
                font_weight=ui.FONT_WEIGHT_SEMIBOLD,
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
                    ui.STATUS_RED_TEXT,
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


def mail_item_row(item, *, State):
    return rx.el.article(
        rx.el.div(
            rx.el.div(rx.cond(item["is_invoice"], design_icon("file_pdf", 18),
                              rx.cond(item["has_attachment"], design_icon("file_spreadsheet", 18), design_icon("mail", 18))),
                      rx.el.h3(rx.cond(item["has_attachment"], item["file"],
                                       rx.cond(item["subject"] != "", item["subject"], "Письмо без вложений"))),
                      class_name="mail-card-title"),
            rx.cond(item["has_attachment"] & (item["subject"] != ""), rx.el.p(item["subject"], class_name="mail-subject"), rx.fragment()),
            rx.el.dl(rx.el.div(rx.el.dt("Отправитель"), rx.el.dd(item["sender"])),
                     rx.el.div(rx.el.dt("Получено"), rx.el.dd(item["received"])),
                     rx.el.div(rx.el.dt("Источник"), rx.el.dd(item["source"])),
                     rx.el.div(rx.el.dt("Направление"), rx.el.dd(item["mode"])), class_name="mail-meta"),
            rx.cond(item["is_order"], rx.el.p("Магазинов найдено: ", item["matches"], class_name="field-hint"), rx.fragment()),
            rx.cond(item["is_invoice"], rx.el.p(rx.cond(item["order_file"] != "", "Привязана к: " + item["order_file"].to(str), "Ещё не привязана к заказу"),
                                               class_name="field-hint"), rx.fragment()),
            class_name="mail-card-content"),
        rx.el.div(
            rx.el.div(rx.cond(item["is_invoice"], rx.badge("Накладная", color_scheme="blue", variant="soft"),
                              rx.cond(item["kind"] == KIND_MESSAGE, rx.badge("Письмо", color_scheme="gray", variant="soft"),
                                      mail_verdict_badge(item["is_order"]))), class_name="mail-status"),
            rx.cond(item["is_order"],
                    design_button("Взять в обработку", State.take_mail_order(item["path"], item["file"], item["received"]), "arrow_right", primary=True),
                    rx.cond(item["is_invoice"], design_button("Открыть PDF", State.open_mail_attachment(item["path"]), "file_pdf"),
                            rx.el.span("Нет действий", class_name="mail-card-placeholder"))),
            class_name="mail-card-actions"),
        rx.cond((~item["is_order"]) & (~item["is_invoice"]) & (item["reason"] != ""),
                rx.el.p(design_icon("info", 16), item["reason"], class_name="mail-message"), rx.fragment()),
        class_name="mail-card",
    )


def mail_page(*, State):
    return design_page(
        design_heading("Почта", "Входящие заказы", "Проверка писем, вложения и обработка заказов — в одном месте."),
        rx.cond(
            State.mail_configured,
            rx.vstack(
                rx.cond(
                    State.mail_credentials_editing,
                    mail_setup_hint(State=State),
                    rx.box(),
                ),
                design_mail_panel("mail-connection",
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
                    rx.text(
                        "Проверяются все письма выбранной почтовой папки, включая старые и письма от новых отправителей. Первая проверка может занять время.",
                        color=muted(), font_size="12px",
                    ),
                    rx.cond(
                        State.mail_error != "",
                        rx.text(State.mail_error, color=ui.STATUS_RED_TEXT, font_size="12px"),
                        rx.box(),
                    ),
                ),
                rx.cond(
                    State.mail_notification != "",
                    design_mail_panel("mail-notification",
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
                            font_weight=ui.FONT_WEIGHT_SEMIBOLD,
                        ),
                    ),
                    rx.box(),
                ),
                design_mail_panel("mail-errors",
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
                                            font_weight=ui.FONT_WEIGHT_SEMIBOLD,
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
                                        color=ui.STATUS_RED_TEXT,
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
                design_mail_panel("mail-filters",
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
                    rx.cond(
                        State.mail_categories.length() > 1,
                        rx.vstack(
                            rx.text(
                                "Направление накладных",
                                color=muted(),
                                font_size="12px",
                                font_weight="600",
                            ),
                            rx.flex(
                                rx.foreach(
                                    State.mail_categories,
                                    lambda category: segment_button(
                                        category,
                                        State.mail_category,
                                        State.set_mail_category(category),
                                    ),
                                ),
                                gap="8px",
                                wrap="wrap",
                                width="100%",
                            ),
                            spacing="2",
                            width="100%",
                        ),
                        rx.box(),
                    ),
                ),
                rx.cond(
                    State.mail_result_count > 0,
                    design_mail_panel("mail-inbox",
                        panel_title("mail", "Письма и вложения"),
                        rx.text("Найдено записей: ", State.mail_result_count, color=muted(), font_size="13px"),
                        rx.vstack(
                            rx.foreach(State.mail_items, lambda item: mail_item_row(item, State=State)),
                            spacing="3",
                            width="100%",
                            class_name="mail-card-grid",
                        ),
                        rx.cond(
                            State.mail_page_count > 1,
                            rx.hstack(
                                secondary_button("← Новее", on_click=State.set_mail_page(State.mail_page - 1),
                                                 disabled=State.mail_page <= 1),
                                rx.text("Страница ", State.mail_page, " из ", State.mail_page_count),
                                secondary_button("Старее →", on_click=State.set_mail_page(State.mail_page + 1),
                                                 disabled=State.mail_page >= State.mail_page_count),
                                align="center", wrap="wrap", spacing="3", width="100%",
                            ),
                            rx.box(),
                        ),
                    ),
                    rx.el.p("Нет сообщений по выбранным фильтрам", class_name="mail-empty", role="status"),
                ),
                spacing="4",
                width="100%",
                class_name="mail-design-grid",
            ),
            mail_setup_hint(State=State),
        ),
        class_name="mail-page",
    )
