"""Settings presentation helpers."""
from functools import partial
from orders_dashboard.constants import (
    ACCENT,
    AI_PROVIDER_OPTIONS,
    SETTINGS_LABELS,
)
from modules.version import APP_NAME
from orders_dashboard.components import (
    backup_item_row,
    border,
    fleet_text_field,
    muted,
    page_shell,
    panel_shell,
    panel_title,
    primary_button,
    secondary_button,
    segmented_control,
    settings_toggle_row,
    surface_alt,
    text,
    topbar,
    version_release_card,
    weight_field,
    weight_select_field,
)
from orders_dashboard.icons import fa_icon
import reflex as rx
from orders_dashboard import theme as ui


def version_page(*, State):
    return page_shell(
        topbar(
            "Версия",
            "Текущая версия приложения и история обновлений.",
        ),
        panel_shell(
            panel_title("info", "Текущая версия"),
            rx.hstack(
                rx.vstack(
                    rx.text(APP_NAME, color=muted(), font_size="13px"),
                    rx.heading(State.current_version, color=text(), size="8"),
                    rx.text(
                        "Версия хранится в modules/version.py. Журнал изменений — в CHANGELOG.md.",
                        color=muted(),
                        font_size="12px",
                    ),
                    align="start",
                    spacing="1",
                ),
                rx.spacer(),
                fa_icon(tag="circle_check", size=32, color=ACCENT),
                width="100%",
                align="center",
            ),
        ),
        panel_shell(
            panel_title("refresh", "Обновления"),
            rx.vstack(
                rx.hstack(
                    rx.vstack(
                        rx.text(
                            "Текущая версия",
                            color=muted(),
                            font_size="12px",
                        ),
                        rx.text(State.current_version, color=text(), font_weight=ui.FONT_WEIGHT_SEMIBOLD),
                        align="start",
                        spacing="1",
                    ),
                    rx.vstack(
                        rx.text(
                            rx.cond(
                                State.remote_version != "",
                                "Версия на GitHub",
                                "Удалённая версия",
                            ),
                            color=muted(),
                            font_size="12px",
                        ),
                        rx.text(
                            rx.cond(State.remote_version != "", State.remote_version, "—"),
                            color=text(),
                            font_weight=ui.FONT_WEIGHT_SEMIBOLD,
                        ),
                        align="start",
                        spacing="1",
                    ),
                    rx.spacer(),
                    fa_icon(tag="refresh", size=26, color=ACCENT),
                    width="100%",
                    align="center",
                    spacing="6",
                ),
                rx.text(State.update_status, color=muted(), font_size="13px"),
                rx.hstack(
                    primary_button(
                        rx.cond(
                            State.checking_update,
                            "Проверяю...",
                            "Проверить обновления",
                        ),
                        on_click=State.check_for_update,
                        width="220px",
                        disabled=State.checking_update | State.updating_app,
                    ),
                    secondary_button(
                        rx.cond(State.updating_app, "Обновляю...", "Обновить"),
                        on_click=State.update_application,
                        width="150px",
                        disabled=(
                            ~State.update_available
                            | State.checking_update
                            | State.updating_app
                        ),
                    ),
                    spacing="3",
                    wrap="wrap",
                ),
                rx.cond(
                    State.update_available,
                    rx.text(
                        "Новая версия готова к установке. После обновления страница перезагрузится.",
                        color=ACCENT,
                        font_size="12px",
                    ),
                    rx.box(),
                ),
                align="start",
                spacing="3",
                width="100%",
            ),
        ),
        panel_shell(
            panel_title("history", "История обновлений"),
            rx.cond(
                State.version_history.length() > 0,
                rx.vstack(
                    rx.foreach(State.version_history, version_release_card),
                    spacing="3",
                    width="100%",
                ),
                rx.text(
                    "Журнал обновлений пока пуст.",
                    color=muted(),
                    font_size="13px",
                ),
            ),
        ),
    )


def backup_page(*, State):
    return page_shell(
        topbar(
            "Резервные копии",
            "Сохраняйте статистику, историю и настройки перед важными изменениями.",
        ),
        panel_shell(
            panel_title("folder", "Папка хранения"),
            rx.text(
                "В архив попадают JSON-файлы состояния и списки маршрутов. Рабочие Excel-файлы, PDF и логи не копируются.",
                color=muted(),
                font_size="13px",
            ),
            rx.hstack(
                rx.input(
                    value=State.backup_directory,
                    on_change=State.set_backup_directory,
                    placeholder="Путь к папке резервных копий",
                    width="100%",
                    height="42px",
                ),
                primary_button(
                    "Сохранить папку",
                    on_click=State.save_backup_directory_form,
                    width="170px",
                ),
                width="100%",
                align="center",
                spacing="2",
            ),
            rx.text(
                "По умолчанию: data/backups. В веб-дашборде укажите путь на компьютере, где запущено приложение.",
                color=muted(),
                font_size="12px",
            ),
        ),
        panel_shell(
            rx.hstack(
                panel_title("save", "Снимок состояния"),
                rx.spacer(),
                secondary_button(
                    "Обновить список",
                    on_click=State.refresh_backups,
                    width="160px",
                ),
                primary_button(
                    "Создать копию",
                    on_click=State.create_full_backup,
                    width="160px",
                ),
                width="100%",
                align="center",
                wrap="wrap",
            ),
            rx.text(
                "Рекомендуется создавать копию перед обновлением приложения или массовым изменением маршрутов.",
                color=muted(),
                font_size="12px",
            ),
            rx.cond(
                State.backup_items.length() > 0,
                rx.vstack(
                    rx.foreach(State.backup_items, backup_item_row),
                    spacing="2",
                    width="100%",
                    max_height="420px",
                    overflow_y="auto",
                ),
                rx.text("Резервных копий пока нет", color=muted(), font_size="13px"),
            ),
        ),
        panel_shell(
            panel_title("history", "Восстановление"),
            rx.hstack(
                rx.select(
                    State.backup_labels,
                    value=State.selected_backup,
                    on_change=State.set_selected_backup,
                    placeholder="Выберите корректную копию",
                    width="100%",
                ),
                secondary_button(
                    "Восстановить",
                    on_click=State.ask_restore_backup,
                    width="160px",
                    disabled=State.backup_labels.length() == 0,
                ),
                width="100%",
                align="center",
                spacing="2",
            ),
            rx.cond(
                State.restore_confirmation_open,
                rx.vstack(
                    rx.text(
                        "Внимание: восстановление заменит текущую статистику, историю почты, списки маршрутов и настройки. Перед заменой будет создана страховочная копия текущего состояния.",
                        color=ui.STATUS_AMBER_TEXT,
                        font_size="13px",
                        font_weight=ui.FONT_WEIGHT_SEMIBOLD,
                    ),
                    rx.hstack(
                        primary_button(
                            "Да, восстановить",
                            on_click=State.confirm_restore_backup,
                            width="180px",
                        ),
                        secondary_button(
                            "Отмена",
                            on_click=State.cancel_restore_backup,
                            width="120px",
                        ),
                        spacing="2",
                    ),
                    align="start",
                    spacing="3",
                    width="100%",
                    padding="12px",
                    border=f"1px solid {ui.LINE}",
                    border_radius="9px",
                    background=ui.STATUS_AMBER_BG,
                ),
                rx.box(),
            ),
            rx.text(
                "config/mail.json может содержать пароль приложения. Не передавайте такой архив другим людям.",
                color=muted(),
                font_size="12px",
            ),
            rx.cond(
                State.backup_status != "",
                rx.text(State.backup_status, color=muted(), font_size="13px"),
                rx.box(),
            ),
        ),
    )


def settings_page(*, State):
    return page_shell(
        topbar("Настройки", "Поведение программы при обработке заказов."),
        rx.vstack(
            *[
                settings_toggle_row(
                    label,
                    hint,
                    State.settings_data[key],
                    lambda checked, key=key: State.toggle_setting(key, checked),
                )
                for key, (label, hint) in SETTINGS_LABELS.items()
            ],
            spacing="3",
            width="100%",
        ),
        rx.hstack(
            primary_button("Сохранить настройки", on_click=State.save_settings_form, width="220px"),
            rx.text(State.settings_status, color=muted(), font_size="13px"),
            spacing="4",
            align="center",
        ),
        panel_shell(
            rx.hstack(
                panel_title("ai", "Чат-помощник"),
                rx.spacer(),
                rx.cond(
                    State.ai_configured,
                    rx.badge("Настроено", color_scheme="green", variant="soft"),
                    rx.badge("Не настроено", color_scheme="gray", variant="soft"),
                ),
                width="100%",
                align="center",
            ),
            rx.text(
                "Плавающая кнопка чата внизу справа доступна любому, кто откроет сайт — "
                "в том числе по временной ссылке. У чата нет доступа к заказам, весу или "
                "другим настройкам — только обычный разговор.",
                color=muted(),
                font_size="12px",
            ),
            weight_select_field("Способ подключения", State.ai_provider_label, State.set_ai_provider_label, AI_PROVIDER_OPTIONS),
            rx.hstack(
                weight_field(
                    "Ключ Anthropic API",
                    State.ai_anthropic_key_input,
                    State.set_ai_anthropic_key_input,
                    "необходим для «Claude (ключ Anthropic API)»",
                ),
                spacing="3",
                width="100%",
                align="end",
            ),
            rx.hstack(
                secondary_button("Сохранить настройки чата", on_click=State.save_ai_settings_form, width="220px"),
                rx.text(State.ai_settings_status, color=muted(), font_size="13px"),
                spacing="4",
                align="center",
            ),
            rx.text(
                "Ключ хранится локально в config/ai.json и никуда, кроме Anthropic, не "
                "передаётся. Для «Claude через Claude Code CLI» ключ не нужен — "
                "используются учётные данные `ant auth login` на этом компьютере.",
                color=muted(),
                font_size="11px",
            ),
        ),
        panel_shell(
            rx.hstack(
                panel_title("camera", "Yandex Vision OCR"),
                rx.spacer(),
                rx.cond(
                    State.yandex_vision_configured,
                    rx.badge("Настроено", color_scheme="green", variant="soft"),
                    rx.badge("Не настроено", color_scheme="gray", variant="soft"),
                ),
                width="100%",
                align="center",
            ),
            rx.text(
                "Распознаёт фотографии накладных на вкладке «OCR накладных». "
                "Укажите ключ сервисного аккаунта с доступом Vision OCR и ID каталога.",
                color=muted(),
                font_size="12px",
            ),
            rx.hstack(
                weight_field(
                    "Ключ Yandex Vision API",
                    State.yandex_vision_api_key_input,
                    State.set_yandex_vision_api_key_input,
                    "пустое поле оставит сохранённый ключ",
                    input_type="password",
                ),
                weight_field(
                    "ID каталога Yandex Cloud",
                    State.yandex_vision_folder_id_input,
                    State.set_yandex_vision_folder_id_input,
                    "b1g...",
                ),
                spacing="3",
                width="100%",
                align="end",
            ),
            rx.hstack(
                secondary_button(
                    "Сохранить настройки OCR",
                    on_click=State.save_yandex_vision_settings_form,
                    width="220px",
                ),
                rx.text(State.yandex_vision_settings_status, color=muted(), font_size="13px"),
                spacing="4",
                align="center",
            ),
            rx.text(
                "Ключ хранится только локально в config/ai.json, который исключён из Git. "
                "Пустой ключ при сохранении не удаляет ранее сохранённый ключ.",
                color=muted(),
                font_size="11px",
            ),
        ),
        panel_shell(
            rx.hstack(
                panel_title("truck", "GPS-трекер ГдеМои"),
                rx.spacer(),
                rx.cond(
                    State.gdemoi_configured,
                    rx.badge("Настроено", color_scheme="green", variant="soft"),
                    rx.badge("Не настроено", color_scheme="gray", variant="soft"),
                ),
                width="100%",
                align="center",
            ),
            rx.text(
                "Живые координаты трекера ГдеМои А2 подмешиваются в маршрут на "
                "вкладке «Трекинг» (вид «Реальные данные»). Трекер привязывается к "
                "конкретной машине в справочнике «Водители и транспорт» — полем "
                "«ID трекера ГдеМои».",
                color=muted(),
                font_size="12px",
            ),
            weight_field(
                "Ключ API ГдеМои",
                State.gdemoi_api_key_input,
                State.set_gdemoi_api_key_input,
                "пустое поле оставит сохранённый ключ",
                input_type="password",
            ),
            rx.hstack(
                secondary_button("Сохранить ключ ГдеМои", on_click=State.save_gdemoi_settings_form, width="220px"),
                rx.text(State.gdemoi_settings_status, color=muted(), font_size="13px"),
                spacing="4",
                align="center",
            ),
            rx.text(
                "Ключ хранится только локально в config/gdemoi.json, который исключён из Git.",
                color=muted(),
                font_size="11px",
            ),
        ),
    )


def fleet_driver_card(item, *, State):
    return rx.hstack(
        rx.vstack(
            rx.text(item["name"], color=text(), font_size="15px", font_weight=ui.FONT_WEIGHT_SEMIBOLD),
            rx.text(item["login"], color=muted(), font_size="12px"),
            rx.text(item["phone"], color=muted(), font_size="12px"),
            rx.text("Роль: ", item["role_label"], color=muted(), font_size="12px"),
            rx.text("Рейтинг: ", item["rating"], " / 5", color=muted(), font_size="12px"),
            rx.cond(
                item["role"] == "driver",
                rx.text("Транспорт: ", item["default_vehicle"], color=muted(), font_size="12px"),
                rx.box(),
            ),
            rx.text(rx.cond(item["active"], "Активен", "Неактивен"), color=rx.cond(item["active"], ui.STATUS_GREEN_TEXT, ui.STATUS_AMBER_TEXT), font_size="12px"),
            align="start", spacing="1",
        ),
        rx.spacer(),
        rx.hstack(
            rx.button("Изменить", on_click=State.edit_fleet_driver(item["id"]), variant="soft", size="2"),
            rx.button("Удалить", on_click=State.ask_delete_fleet_item("driver", item["id"]), variant="soft", color_scheme="red", size="2"),
            spacing="2",
        ),
        width="100%", padding="14px", border=f"1px solid {border()}", border_radius="10px", background=surface_alt(),
    )


def fleet_vehicle_card(item, *, State):
    return rx.hstack(
        rx.vstack(
            rx.text(item["name"], color=text(), font_size="15px", font_weight=ui.FONT_WEIGHT_SEMIBOLD),
            rx.text(item["plate"], color=text(), font_size="14px"),
            rx.text("Пробег: ", item["odometer_km"], " км", color=muted(), font_size="12px"),
            rx.cond(
                item["tracker_id"] != "",
                rx.text("Трекер ГдеМои: ", item["tracker_id"], color=muted(), font_size="12px"),
                rx.box(),
            ),
            rx.text(rx.cond(item["active"], "Активен", "Неактивен"), color=rx.cond(item["active"], ui.STATUS_GREEN_TEXT, ui.STATUS_AMBER_TEXT), font_size="12px"),
            align="start", spacing="1",
        ),
        rx.spacer(),
        rx.hstack(
            rx.button("Изменить", on_click=State.edit_fleet_vehicle(item["id"]), variant="soft", size="2"),
            rx.button("Удалить", on_click=State.ask_delete_fleet_item("vehicle", item["id"]), variant="soft", color_scheme="red", size="2"),
            spacing="2",
        ),
        width="100%", padding="14px", border=f"1px solid {border()}", border_radius="10px", background=surface_alt(),
    )


def fleet_drivers_tab(*, State):
    return rx.vstack(
        rx.hstack(
            fleet_text_field("Код входа", State.fleet_driver_login, lambda value: State.set_fleet_driver_field("login", value)),
            fleet_text_field("ФИО", State.fleet_driver_name, lambda value: State.set_fleet_driver_field("name", value)),
            fleet_text_field("Телефон", State.fleet_driver_phone, lambda value: State.set_fleet_driver_field("phone", value)),
            rx.vstack(
                rx.text("Роль", color=muted(), font_size="12px"),
                rx.el.select(
                    rx.el.option("Водитель", value="driver"),
                    rx.el.option("Экспедитор", value="expeditor"),
                    rx.el.option("Грузчик", value="loader"),
                    value=State.fleet_driver_role,
                    on_change=lambda value: State.set_fleet_driver_field("role", value),
                    class_name="personnel-select",
                ),
                spacing="1", align="start", width="100%",
            ),
            width="100%", spacing="3",
        ),
        rx.hstack(
            fleet_text_field("Дата приёма", State.fleet_driver_hired_on, lambda value: State.set_fleet_driver_field("hired_on", value), "date"),
            fleet_text_field("PIN-код", State.fleet_driver_pin, lambda value: State.set_fleet_driver_field("pin", value), "password"),
            rx.cond(
                State.fleet_driver_role == "driver",
                rx.vstack(
                    rx.text("Транспорт по умолчанию", color=muted(), font_size="12px"),
                    rx.select(
                        State.fleet_vehicle_options,
                        value=State.fleet_driver_default_vehicle,
                        on_change=lambda value: State.set_fleet_driver_field("default_vehicle", value),
                        placeholder="Не назначен",
                        width="100%",
                    ),
                    spacing="1", align="start", width="100%",
                ),
                rx.box(),
            ),
            rx.vstack(
                rx.text("Активность", color=muted(), font_size="12px"),
                rx.checkbox("Активен", checked=State.fleet_driver_active, on_change=State.set_fleet_driver_active),
                spacing="1", align="start", width="100%",
            ),
            width="100%", spacing="3",
        ),
        rx.text("Оставьте PIN пустым при редактировании, чтобы сохранить прежний PIN.", color=muted(), font_size="11px"),
        fleet_text_field("Заметка", State.fleet_driver_notes, lambda value: State.set_fleet_driver_field("notes", value)),
        rx.hstack(
            primary_button("Сохранить сотрудника", on_click=State.save_fleet_driver),
            secondary_button("Очистить", on_click=State.clear_fleet_driver_form),
            spacing="3",
        ),
        rx.cond(State.fleet_drivers.length() > 0, rx.vstack(rx.foreach(State.fleet_drivers, lambda item: fleet_driver_card(item, State=State)), width="100%", spacing="2"), rx.text("Сотрудников пока нет", color=muted())),
        spacing="3", width="100%", align="start",
    )


def fleet_vehicles_tab(*, State):
    return rx.vstack(
        rx.hstack(
            fleet_text_field("Название / модель", State.fleet_vehicle_name, lambda value: State.set_fleet_vehicle_field("name", value)),
            fleet_text_field("Госномер", State.fleet_vehicle_plate, lambda value: State.set_fleet_vehicle_field("plate", value)),
            fleet_text_field("Пробег, км", State.fleet_vehicle_odometer, lambda value: State.set_fleet_vehicle_field("odometer", value), "number"),
            width="100%", spacing="3",
        ),
        fleet_text_field("Краткое описание", State.fleet_vehicle_description, lambda value: State.set_fleet_vehicle_field("description", value)),
        fleet_text_field("Заметка", State.fleet_vehicle_notes, lambda value: State.set_fleet_vehicle_field("notes", value)),
        rx.vstack(
            fleet_text_field("ID трекера ГдеМои", State.fleet_vehicle_tracker_id, lambda value: State.set_fleet_vehicle_field("tracker_id", value)),
            rx.text(
                "Числовой ID трекера из личного кабинета ГдеМои. Оставьте пустым, если на машине нет трекера.",
                color=muted(), font_size="11px",
            ),
            spacing="1", align="start", width="100%",
        ),
        rx.hstack(
            rx.checkbox("Активен", checked=State.fleet_vehicle_active, on_change=State.set_fleet_vehicle_active),
            primary_button("Сохранить транспорт", on_click=State.save_fleet_vehicle),
            secondary_button("Очистить", on_click=State.clear_fleet_vehicle_form),
            spacing="3", align="center",
        ),
        rx.cond(State.fleet_vehicles.length() > 0, rx.vstack(rx.foreach(State.fleet_vehicles, lambda item: fleet_vehicle_card(item, State=State)), width="100%", spacing="2"), rx.text("Транспорт пока не добавлен", color=muted())),
        spacing="3", width="100%", align="start",
    )


def fleet_page(*, State):
    return page_shell(
        topbar(
            "Водители и транспорт",
            "Локальный справочник для назначения рейсов. Технические GPS-ключи маршрутов не изменяются.",
        ),
        rx.vstack(
            segmented_control(["Водители", "Транспорт"], State.fleet_tab, State.set_fleet_tab),
            rx.cond(State.fleet_tab == "Водители", fleet_drivers_tab(State=State), fleet_vehicles_tab(State=State)),
            rx.cond(
                State.fleet_delete_pending_id != "",
                rx.hstack(
                    rx.text("Удалить карточку без возможности восстановления?", color=ui.STATUS_RED_TEXT, font_size="13px"),
                    rx.button("Удалить", on_click=State.confirm_delete_fleet_item, color_scheme="red", size="2"),
                    secondary_button("Отмена", on_click=State.cancel_delete_fleet_item),
                    spacing="3", align="center", wrap="wrap",
                ),
                rx.box(),
            ),
            rx.cond(State.fleet_status != "", rx.text(State.fleet_status, color=muted(), font_size="13px"), rx.box()),
            width="100%", spacing="4", align="start",
        ),
    )
