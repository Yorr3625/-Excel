from pathlib import Path
from datetime import datetime
import asyncio
import json
import traceback

import reflex as rx

from modules.config import build_groups, load_settings, load_stores, save_settings, save_stores
from modules.pipeline import detect_mode, process_order as run_pipeline
from modules.styles import blue_fill, conflict_fill, green_fill, purple_fill, yellow_fill
from modules.tracking_sim import (
    ROUTE_COLORS,
    ROUTE_LABELS,
    advance_tick,
    build_map_svg,
    init_vehicles,
)


ACCENT = "#1f883d"
ACCENT_HOVER = "#1a7f37"
UPLOAD_ID = "order_upload"
PROCESSED_FILES = Path("processed_files.json")

NAV_ITEMS = [
    ("Dashboard", "layout_dashboard"),
    ("Заказы", "package"),
    ("Маршруты", "route"),
    ("Трекинг", "truck"),
    ("История", "history"),
    ("Настройки", "settings"),
]

ICON_TINTS = {
    "green": (ACCENT, "rgba(31, 136, 61, 0.16)"),
    "blue": ("#2f6fed", "rgba(47, 111, 237, 0.16)"),
    "violet": ("#7c5cff", "rgba(124, 92, 255, 0.16)"),
}

SETTINGS_LABELS = {
    "open_file_after_processing": (
        "Открывать файл после обработки",
        "Открыть готовый Excel-файл сразу после обработки.",
    ),
    "open_folder_after_processing": (
        "Открывать папку после обработки",
        "Открыть папку с результатом, если файл не открывается.",
    ),
    "create_logs": (
        "Вести лог обработки",
        "Сохранять текстовый лог каждой обработки в папку logs.",
    ),
    "save_backup": (
        "Сохранять резервную копию",
        "Хранить резервную копию исходного файла перед обработкой.",
    ),
    "show_errors": (
        "Показывать ошибки",
        "Выводить подробный текст ошибки обработки на экран.",
    ),
}


def load_processed_files():
    if not PROCESSED_FILES.exists():
        return {}

    try:
        return json.loads(PROCESSED_FILES.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}


def save_processed_file(filename: str):
    data = load_processed_files()
    data[filename] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    PROCESSED_FILES.write_text(
        json.dumps(data, ensure_ascii=False, indent=4),
        encoding="utf-8",
    )


def format_number(value):
    return f"{float(value):,.0f}".replace(",", " ")


class State(rx.State):
    selected_file: str = "Файл не выбран"
    uploaded_file_path: str = ""
    mode: str = "Область"
    mode_auto_note: str = ""
    theme: str = "dark"
    status: str = "Ожидает загрузки файла"
    is_processing: bool = False
    output_file: str = ""
    log_file: str = ""
    grand_total: str = "0"
    route_1_total: str = "0"
    route_2_total: str = "0"
    route_3_total: str = "0"
    route_4_total: str = "0"
    conflict_count: int = 0
    unknown_count: int = 0
    error_text: str = ""
    history_1_file: str = "Нет обработок"
    history_1_time: str = ""
    history_2_file: str = "Нет обработок"
    history_2_time: str = ""
    history_3_file: str = "Нет обработок"
    history_3_time: str = ""

    orders_today_count: int = 0
    orders_total_count: int = 0
    stores_total_count: int = 0

    current_page: str = "Dashboard"

    routes_source: str = "Область"
    route_1_stores: list[str] = []
    route_2_stores: list[str] = []
    route_3_stores: list[str] = []
    route_4_stores: list[str] = []
    new_store_1: str = ""
    new_store_2: str = ""
    new_store_3: str = ""
    new_store_4: str = ""
    routes_status: str = ""

    tracking_source: str = "Область"
    tracking_running: bool = False
    vehicles: list[dict] = []
    tracking_event_log: list[str] = []

    settings_data: dict[str, bool] = {
        "open_file_after_processing": True,
        "open_folder_after_processing": False,
        "create_logs": True,
        "save_backup": True,
        "show_errors": True,
    }
    settings_status: str = ""

    def set_page(self, page: str):
        self.current_page = page

        if page == "Маршруты":
            self.load_routes()
        elif page == "Настройки":
            self.load_settings_form()
        elif page == "Трекинг" and not self.vehicles:
            self.init_tracking()

    def load_routes(self):
        stores_file = "stores_city.json" if self.routes_source == "Город" else "stores_region.json"
        data = load_stores(stores_file)
        self.route_1_stores = list(data.get("route_1", []))
        self.route_2_stores = list(data.get("route_2", []))
        self.route_3_stores = list(data.get("route_3", []))
        self.route_4_stores = list(data.get("route_4", []))
        self.routes_status = ""

    def set_routes_source(self, value: str):
        self.routes_source = value
        self.load_routes()

    def set_new_store_1(self, value: str):
        self.new_store_1 = value

    def set_new_store_2(self, value: str):
        self.new_store_2 = value

    def set_new_store_3(self, value: str):
        self.new_store_3 = value

    def set_new_store_4(self, value: str):
        self.new_store_4 = value

    def add_store_1(self):
        value = self.new_store_1.strip()
        if value and value not in self.route_1_stores:
            self.route_1_stores = self.route_1_stores + [value]
        self.new_store_1 = ""

    def add_store_2(self):
        value = self.new_store_2.strip()
        if value and value not in self.route_2_stores:
            self.route_2_stores = self.route_2_stores + [value]
        self.new_store_2 = ""

    def add_store_3(self):
        value = self.new_store_3.strip()
        if value and value not in self.route_3_stores:
            self.route_3_stores = self.route_3_stores + [value]
        self.new_store_3 = ""

    def add_store_4(self):
        value = self.new_store_4.strip()
        if value and value not in self.route_4_stores:
            self.route_4_stores = self.route_4_stores + [value]
        self.new_store_4 = ""

    def remove_store_1(self, name: str):
        self.route_1_stores = [item for item in self.route_1_stores if item != name]

    def remove_store_2(self, name: str):
        self.route_2_stores = [item for item in self.route_2_stores if item != name]

    def remove_store_3(self, name: str):
        self.route_3_stores = [item for item in self.route_3_stores if item != name]

    def remove_store_4(self, name: str):
        self.route_4_stores = [item for item in self.route_4_stores if item != name]

    def save_routes(self):
        stores_file = "stores_city.json" if self.routes_source == "Город" else "stores_region.json"
        data = {
            "route_1": self.route_1_stores,
            "route_2": self.route_2_stores,
            "route_3": self.route_3_stores,
            "route_4": self.route_4_stores,
        }
        save_stores(data, stores_file)
        self.routes_status = f"Сохранено в {stores_file}"

    def load_settings_form(self):
        data = load_settings()
        self.settings_data = {key: bool(data.get(key, False)) for key in SETTINGS_LABELS}
        self.settings_status = ""

    def toggle_setting(self, key: str, value: bool):
        self.settings_data = {**self.settings_data, key: value}

    def save_settings_form(self):
        save_settings(dict(self.settings_data))
        self.settings_status = "Настройки сохранены"

    def init_tracking(self):
        stores_file = "stores_city.json" if self.tracking_source == "Город" else "stores_region.json"
        self.vehicles = init_vehicles(stores_file)
        self.tracking_event_log = []

    def set_tracking_source(self, value: str):
        self.tracking_running = False
        self.tracking_source = value
        self.init_tracking()

    def reset_tracking(self):
        self.tracking_running = False
        self.init_tracking()

    def stop_tracking(self):
        self.tracking_running = False

    @rx.event(background=True)
    async def start_tracking(self):
        async with self:
            if self.tracking_running or not self.vehicles:
                return
            self.tracking_running = True

        while True:
            await asyncio.sleep(1.0)

            async with self:
                if not self.tracking_running:
                    return

                updated, events = advance_tick(self.vehicles)
                self.vehicles = updated

                if events:
                    self.tracking_event_log = (events + self.tracking_event_log)[:40]

    @rx.var
    def map_svg(self) -> str:
        return build_map_svg(self.vehicles)

    @rx.var
    def ranked_vehicles(self) -> list[dict]:
        return sorted(self.vehicles, key=lambda v: v["score"], reverse=True)

    @rx.var
    def tracking_total_distance(self) -> str:
        return format_number(sum(v["distance_km"] for v in self.vehicles))

    @rx.var
    def tracking_total_fuel(self) -> str:
        return format_number(sum(v["fuel_l"] for v in self.vehicles))

    @rx.var
    def tracking_total_cost(self) -> str:
        return format_number(sum(v["cost"] for v in self.vehicles))

    @rx.var
    def tracking_total_harsh(self) -> int:
        return sum(v["harsh_count"] for v in self.vehicles)

    @rx.var
    def tracking_avg_score(self) -> int:
        if not self.vehicles:
            return 100
        return round(sum(v["score"] for v in self.vehicles) / len(self.vehicles))

    def load_history(self):
        data = load_processed_files()
        items = sorted(data.items(), key=lambda item: item[1], reverse=True)[:3]
        placeholders = [("Нет обработок", "")] * 3
        items = items + placeholders[len(items):]

        self.history_1_file, self.history_1_time = items[0]
        self.history_2_file, self.history_2_time = items[1]
        self.history_3_file, self.history_3_time = items[2]

        self.orders_total_count = len(data)
        today = datetime.now().strftime("%Y-%m-%d")
        self.orders_today_count = sum(1 for ts in data.values() if ts.startswith(today))

        self.refresh_stores_total()

    def refresh_stores_total(self):
        total = 0

        for filename in ("stores_city.json", "stores_region.json"):
            try:
                store_data = load_stores(filename)
            except (OSError, json.JSONDecodeError):
                continue

            total += sum(len(names) for names in store_data.values())

        self.stores_total_count = total

    async def handle_upload(self, files: list[rx.UploadFile]):
        if not files:
            self.status = "Сначала выберите Excel-файл"
            return

        for file in files:
            data = await file.read()
            filename = getattr(file, "filename", None) or file.name
            upload_dir = rx.get_upload_dir()
            upload_dir.mkdir(parents=True, exist_ok=True)
            output_path = upload_dir / filename
            output_path.write_bytes(data)

            self.selected_file = filename
            self.uploaded_file_path = str(output_path)
            self.status = f"Файл загружен: {filename}"
            self.output_file = ""
            self.log_file = ""
            self.error_text = ""

            self.detect_and_set_mode()

    def detect_and_set_mode(self):
        self.mode_auto_note = ""

        try:
            fills = [green_fill, yellow_fill, blue_fill, purple_fill]
            mode_groups = {
                "Город": build_groups(load_stores("stores_city.json"), fills),
                "Область": build_groups(load_stores("stores_region.json"), fills),
            }

            mode, scores = detect_mode(self.uploaded_file_path, mode_groups, conflict_fill)

            self.mode = mode
            self.mode_auto_note = (
                f"Определено автоматически: «{mode}» "
                f"(совпадений — Город: {scores['Город']}, Область: {scores['Область']})"
            )

        except Exception:
            self.mode_auto_note = "Не удалось определить режим автоматически, выберите вручную"

    def set_mode(self, mode: str):
        self.mode = mode
        self.mode_auto_note = ""

    def set_theme(self, theme: str):
        self.theme = theme

    def set_dark_mode(self, enabled: bool):
        self.theme = "dark" if enabled else "light"

    def process_order(self):
        if not self.uploaded_file_path:
            self.status = "Сначала загрузите Excel-файл"
            return

        self.is_processing = True
        self.status = "Обработка заказа..."
        self.error_text = ""

        try:
            stores_file = "stores_city.json" if self.mode == "Город" else "stores_region.json"
            settings = load_settings()

            stores = load_stores(stores_file)
            fills = [green_fill, yellow_fill, blue_fill, purple_fill]
            groups = build_groups(stores, fills)

            output_file, log_file, stats = run_pipeline(
                self.uploaded_file_path,
                settings,
                groups,
                conflict_fill,
            )

            route_totals = list(stats.get("route_totals", {}).values())
            while len(route_totals) < 4:
                route_totals.append(0)

            self.route_1_total = format_number(route_totals[0])
            self.route_2_total = format_number(route_totals[1])
            self.route_3_total = format_number(route_totals[2])
            self.route_4_total = format_number(route_totals[3])
            self.grand_total = format_number(sum(route_totals))
            self.conflict_count = int(stats.get("conflict_count", 0))
            self.unknown_count = len(stats.get("unknown_stores", []))
            self.output_file = str(output_file)
            self.log_file = str(log_file)
            self.status = "Обработка завершена"

            save_processed_file(self.selected_file)
            self.load_history()

        except Exception:
            self.status = "Ошибка обработки"
            self.error_text = traceback.format_exc()

        finally:
            self.is_processing = False


def theme_value(light: str, dark: str):
    return rx.cond(State.theme == "light", light, dark)


def page_bg():
    return theme_value("#f6f8fa", "#0b0f14")


def surface():
    return theme_value("#ffffff", "#111820")


def surface_alt():
    return theme_value("#f1f4f7", "#16212b")


def border():
    return theme_value("#d9e1e8", "#24313d")


def text():
    return theme_value("#101820", "#f3f6f8")


def muted():
    return theme_value("#66717d", "#8b98a5")


def button_base(**props):
    return {
        "height": "44px",
        "border_radius": "9px",
        "font_weight": "700",
        "transition": "160ms ease",
        "cursor": "pointer",
        **props,
    }


def primary_button(label: str, on_click=None, width: str = "230px"):
    return rx.button(
        label,
        on_click=on_click,
        width=width,
        color="white",
        background=ACCENT,
        _hover={"background": ACCENT_HOVER},
        **button_base()
    )


def secondary_button(label: str, on_click=None, width: str = "156px"):
    return rx.button(
        label,
        on_click=on_click,
        width=width,
        color=text(),
        background=surface_alt(),
        border=f"1px solid {border()}",
        _hover={"background": theme_value("#e4ebf1", "#223140")},
        **button_base()
    )


def nav_button(label: str, icon: str):
    active = State.current_page == label

    return rx.button(
        rx.icon(tag=icon, size=17),
        rx.text(label, font_size="14px"),
        on_click=State.set_page(label),
        width="100%",
        justify_content="flex-start",
        gap="10px",
        color=rx.cond(active, "white", muted()),
        background=rx.cond(active, ACCENT, "transparent"),
        _hover={"background": rx.cond(active, ACCENT_HOVER, theme_value("#edf2f7", "#16212b"))},
        **button_base(height="42px", font_weight=rx.cond(active, "700", "500"))
    )


def segment_button(label: str, current, on_click):
    active = current == label

    return rx.button(
        label,
        on_click=on_click,
        height="36px",
        min_width="96px",
        border_radius="7px",
        color=rx.cond(active, "white", muted()),
        background=rx.cond(active, ACCENT, "transparent"),
        border=rx.cond(active, f"1px solid {ACCENT}", "1px solid transparent"),
        box_shadow=rx.cond(active, "0 0 0 3px rgba(31, 136, 61, 0.18)", "none"),
        _hover={
            "background": rx.cond(active, ACCENT_HOVER, theme_value("#e4ebf1", "#223140"))
        },
        font_weight=rx.cond(active, "700", "600"),
    )


def segmented_control(values: list[str], current, setter):
    return rx.hstack(
        *[
            segment_button(value, current, setter(value))
            for value in values
        ],
        spacing="1",
        padding="4px",
        border=f"1px solid {border()}",
        border_radius="10px",
        background=surface_alt(),
        width="fit-content",
    )


def muted_text(*parts, size="12px"):
    return rx.text(*parts, color=muted(), font_size=size)


def stat_card(icon: str, tint_key: str, title: str, value, hint_node):
    color, tint_bg = ICON_TINTS[tint_key]

    return rx.hstack(
        rx.box(
            rx.icon(tag=icon, size=20, color=color),
            display="flex",
            align_items="center",
            justify_content="center",
            width="44px",
            height="44px",
            min_width="44px",
            border_radius="12px",
            background=tint_bg,
        ),
        rx.vstack(
            rx.text(value, color=text(), font_size="26px", font_weight="800", line_height="1.1"),
            rx.text(title, color=muted(), font_size="13px", font_weight="600"),
            hint_node,
            align="start",
            spacing="1",
        ),
        spacing="4",
        align="center",
        padding="18px",
        border=f"1px solid {border()}",
        border_radius="14px",
        background=surface(),
        box_shadow=theme_value("0 1px 3px rgba(16, 24, 32, 0.06)", "none"),
        width="100%",
    )


def sidebar_logo():
    return rx.hstack(
        rx.box(
            rx.icon(tag="boxes", size=18, color="white"),
            display="flex",
            align_items="center",
            justify_content="center",
            width="34px",
            height="34px",
            border_radius="9px",
            background=ACCENT,
        ),
        rx.vstack(
            rx.heading("Orders", color=text(), size="5", line_height="1.1"),
            rx.text("Обработка заказов v2.0", color=muted(), font_size="11px"),
            align="start",
            spacing="0",
        ),
        spacing="3",
        align="center",
        width="100%",
    )


def theme_switch_row():
    return rx.hstack(
        rx.icon(tag=rx.cond(State.theme == "light", "sun", "moon"), size=16, color=muted()),
        rx.text("Тёмная тема", color=text(), font_size="13px", font_weight="600"),
        rx.spacer(),
        rx.switch(
            checked=State.theme == "dark",
            on_change=State.set_dark_mode,
            color_scheme="green",
        ),
        width="100%",
        align="center",
        spacing="2",
        padding="12px 14px",
        border=f"1px solid {border()}",
        border_radius="12px",
        background=surface_alt(),
    )


def sidebar():
    return rx.vstack(
        sidebar_logo(),
        rx.vstack(
            muted_text("ГЛАВНОЕ МЕНЮ", size="11px"),
            rx.vstack(
                *[nav_button(label, icon) for label, icon in NAV_ITEMS],
                spacing="2",
                width="100%",
            ),
            align="start",
            spacing="3",
            width="100%",
        ),
        rx.spacer(),
        theme_switch_row(),
        align="start",
        spacing="6",
        width="250px",
        min_width="250px",
        height="100vh",
        padding="28px 14px 18px",
        background=theme_value("#ffffff", "#090d12"),
        border_right=f"1px solid {border()}",
    )


def upload_area():
    return rx.upload(
        rx.hstack(
            rx.box(
                rx.icon(tag="upload", size=18, color=ICON_TINTS["green"][0]),
                display="flex",
                align_items="center",
                justify_content="center",
                width="40px",
                height="40px",
                min_width="40px",
                border_radius="10px",
                background=ICON_TINTS["green"][1],
            ),
            rx.vstack(
                rx.text("1. Выберите Excel-файл", color=text(), font_size="15px", font_weight="800"),
                rx.text("Нажмите на эту область или перетащите сюда файл .xlsx", color=muted(), font_size="12px"),
                rx.vstack(
                    rx.foreach(
                        rx.selected_files(UPLOAD_ID),
                        lambda file: rx.text(file, color=ACCENT, font_size="13px", font_weight="700"),
                    ),
                    align="start",
                    spacing="1",
                    width="100%",
                ),
                rx.text("Загруженный файл: ", State.selected_file, color=muted(), font_size="12px"),
                align="start",
                spacing="2",
                width="100%",
            ),
            spacing="3",
            align="start",
            width="100%",
        ),
        id=UPLOAD_ID,
        accept={
            "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet": [".xlsx"],
        },
        max_files=1,
        border=f"1px dashed {border()}",
        border_radius="10px",
        background=surface_alt(),
        padding="18px",
        width="100%",
        cursor="pointer",
    )


def order_panel():
    return rx.vstack(
        rx.hstack(
            rx.vstack(
                rx.heading("Новый заказ", color=text(), size="5"),
                rx.text("Выберите файл, загрузите его, затем укажите режим обработки.", color=muted(), font_size="13px"),
                align="start",
                spacing="1",
            ),
            rx.spacer(),
            width="100%",
            align="center",
        ),
        upload_area(),
        rx.hstack(
            rx.vstack(
                rx.text("2. Загрузите выбранный файл", color=text(), font_size="14px", font_weight="800"),
                rx.text("После загрузки файл будет доступен для обработки.", color=muted(), font_size="12px"),
                align="start",
                spacing="1",
            ),
            rx.spacer(),
            secondary_button(
                "Загрузить выбранный",
                width="190px",
                on_click=State.handle_upload(rx.upload_files(upload_id=UPLOAD_ID)),
            ),
            width="100%",
            align="center",
            padding="14px 16px",
            border=f"1px solid {border()}",
            border_radius="10px",
            background=surface_alt(),
        ),
        rx.hstack(
            rx.vstack(
                rx.text("3. Режим обработки", color=text(), font_size="14px", font_weight="800"),
                segmented_control(["Город", "Область"], State.mode, State.set_mode),
                rx.cond(
                    State.mode_auto_note != "",
                    rx.text(State.mode_auto_note, color=muted(), font_size="12px"),
                    rx.box(),
                ),
                align="start",
                spacing="2",
            ),
            rx.spacer(),
            primary_button(
                rx.cond(State.is_processing, "Обработка...", "Обработать заказ"),
                on_click=State.process_order,
            ),
            width="100%",
            align="center",
            padding="14px 16px",
            border=f"1px solid {border()}",
            border_radius="10px",
            background=surface_alt(),
        ),
        rx.text(State.status, color=muted(), font_size="13px"),
        rx.cond(State.output_file != "", processing_summary(), rx.box()),
        rx.cond(
            State.error_text != "",
            rx.code_block(
                State.error_text,
                language="python",
                width="100%",
                max_height="260px",
                overflow_y="auto",
            ),
            rx.box(),
        ),
        spacing="5",
        padding="24px",
        border=f"1px solid {border()}",
        border_radius="14px",
        background=surface(),
        box_shadow=theme_value("0 1px 3px rgba(16, 24, 32, 0.06)", "none"),
        width="100%",
    )


def result_metric(label: str, value):
    return rx.vstack(
        rx.text(label, color=muted(), font_size="12px"),
        rx.text(value, color=text(), font_size="22px", font_weight="800"),
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
        rx.text(label, color=text(), font_size="14px", font_weight="700"),
        rx.spacer(),
        rx.text(value, color=text(), font_size="14px", font_weight="800"),
        width="100%",
        padding="11px 12px",
        border_radius="9px",
        background=surface_alt(),
    )


def processing_summary():
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
            route_result("Маршрут №1", State.route_1_total),
            route_result("Маршрут №2", State.route_2_total),
            route_result("Маршрут №3", State.route_3_total),
            route_result("Маршрут №4", State.route_4_total),
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


def history_panel():
    return rx.vstack(
        rx.hstack(
            rx.icon(tag="history", size=17, color=text()),
            rx.heading("Последние обработки", color=text(), size="4"),
            spacing="2",
            align="center",
        ),
        rx.vstack(
            history_row(State.history_1_file, State.history_1_time),
            history_row(State.history_2_file, State.history_2_time),
            history_row(State.history_3_file, State.history_3_time),
            spacing="2",
            width="100%",
        ),
        align="start",
        spacing="4",
        padding="24px",
        border=f"1px solid {border()}",
        border_radius="14px",
        background=surface(),
        box_shadow=theme_value("0 1px 3px rgba(16, 24, 32, 0.06)", "none"),
        width="100%",
    )


def history_row(filename, time):
    return rx.hstack(
        rx.box(
            rx.icon(tag="file_spreadsheet", size=16, color=muted()),
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
            rx.text(filename, color=text(), font_weight="700", font_size="14px"),
            rx.text("Обработка заказа", color=muted(), font_size="12px"),
            align="start",
            spacing="1",
        ),
        rx.spacer(),
        rx.text(time, color=muted(), font_size="13px"),
        spacing="3",
        align="center",
        width="100%",
        padding="12px",
        border_radius="10px",
        background=surface_alt(),
    )


def page_shell(*children):
    return rx.vstack(
        *children,
        align="start",
        spacing="5",
        width="100%",
        min_height="100vh",
        padding="28px",
        background=page_bg(),
    )


def topbar(title: str, subtitle: str, actions=None):
    return rx.hstack(
        rx.vstack(
            rx.heading(title, color=text(), size="7"),
            rx.text(subtitle, color=muted(), font_size="13px"),
            align="start",
            spacing="1",
        ),
        rx.spacer(),
        *(actions or []),
        width="100%",
        align="center",
    )


def overview_page():
    return page_shell(
        topbar(
            "Dashboard",
            "Загрузка заказа, выбор режима и запуск обработки в одном аккуратном рабочем блоке.",
        ),
        rx.grid(
            stat_card(
                "package", "green",
                "Заказы сегодня", State.orders_today_count,
                muted_text("Всего обработано: ", State.orders_total_count),
            ),
            stat_card(
                "store", "blue",
                "Магазинов в базе", State.stores_total_count,
                muted_text("Город + Область"),
            ),
            stat_card(
                "route", "violet",
                "Маршрутов", 4,
                muted_text("готовы к выгрузке"),
            ),
            columns="3",
            spacing="4",
            width="100%",
        ),
        rx.grid(
            order_panel(),
            history_panel(),
            columns="2",
            spacing="4",
            width="100%",
            align_items="start",
        ),
    )


def orders_page():
    return page_shell(
        topbar(
            "Заказы",
            "Загрузите файл заказа, выберите режим обработки и запустите обработку.",
        ),
        order_panel(),
    )


def history_page():
    return page_shell(
        topbar("История", "Последние обработанные файлы."),
        history_panel(),
    )


def store_row(name, on_remove):
    return rx.hstack(
        rx.icon(tag="map_pin", size=13, color=muted()),
        rx.text(name, color=text(), font_size="13px"),
        rx.spacer(),
        rx.button(
            rx.icon(tag="x", size=13),
            on_click=on_remove(name),
            size="1",
            variant="ghost",
            color=muted(),
            cursor="pointer",
        ),
        spacing="2",
        width="100%",
        align="center",
        padding="6px 10px",
        border_radius="7px",
        background=surface_alt(),
    )


def route_edit_card(title, stores, new_value, on_add, on_change, on_remove):
    return rx.vstack(
        rx.hstack(
            rx.icon(tag="route", size=15, color=text()),
            rx.text(title, color=text(), font_size="15px", font_weight="800"),
            spacing="2",
            align="center",
        ),
        rx.vstack(
            rx.foreach(stores, lambda name: store_row(name, on_remove)),
            spacing="1",
            width="100%",
            max_height="220px",
            overflow_y="auto",
        ),
        rx.hstack(
            rx.input(
                placeholder="Название магазина",
                value=new_value,
                on_change=on_change,
                width="100%",
            ),
            rx.button(rx.icon(tag="plus", size=15), "Добавить", on_click=on_add, height="36px"),
            width="100%",
            spacing="2",
        ),
        align="start",
        spacing="3",
        padding="18px",
        border=f"1px solid {border()}",
        border_radius="12px",
        background=surface(),
        box_shadow=theme_value("0 1px 3px rgba(16, 24, 32, 0.06)", "none"),
        width="100%",
    )


def routes_page():
    return page_shell(
        topbar(
            "Маршруты",
            "Списки магазинов по маршрутам для режимов Город/Область.",
            actions=[segmented_control(["Город", "Область"], State.routes_source, State.set_routes_source)],
        ),
        rx.grid(
            route_edit_card(
                "Маршрут №1", State.route_1_stores, State.new_store_1,
                State.add_store_1, State.set_new_store_1, State.remove_store_1,
            ),
            route_edit_card(
                "Маршрут №2", State.route_2_stores, State.new_store_2,
                State.add_store_2, State.set_new_store_2, State.remove_store_2,
            ),
            route_edit_card(
                "Маршрут №3", State.route_3_stores, State.new_store_3,
                State.add_store_3, State.set_new_store_3, State.remove_store_3,
            ),
            route_edit_card(
                "Маршрут №4", State.route_4_stores, State.new_store_4,
                State.add_store_4, State.set_new_store_4, State.remove_store_4,
            ),
            columns="2",
            spacing="4",
            width="100%",
        ),
        rx.hstack(
            primary_button("Сохранить маршруты", on_click=State.save_routes, width="220px"),
            rx.text(State.routes_status, color=muted(), font_size="13px"),
            spacing="4",
            align="center",
        ),
    )


def start_pause_button():
    return rx.cond(
        State.tracking_running,
        secondary_button("Пауза", on_click=State.stop_tracking, width="130px"),
        primary_button("Старт симуляции", on_click=State.start_tracking, width="180px"),
    )


def tracking_controls():
    return rx.hstack(
        segmented_control(["Город", "Область"], State.tracking_source, State.set_tracking_source),
        rx.spacer(),
        start_pause_button(),
        secondary_button("Сброс", on_click=State.reset_tracking, width="110px"),
        spacing="3",
        align="center",
        width="100%",
    )


def tracking_legend_dot(color, label):
    return rx.hstack(
        rx.box(width="10px", height="10px", min_width="10px", border_radius="50%", background=color),
        rx.text(label, color=muted(), font_size="12px"),
        spacing="2",
        align="center",
    )


def tracking_legend():
    return rx.hstack(
        *[tracking_legend_dot(color, label) for label, color in zip(ROUTE_LABELS, ROUTE_COLORS)],
        tracking_legend_dot("#f5a623", "Резкий разгон"),
        tracking_legend_dot("#e5484d", "Резкое торможение"),
        spacing="5",
        wrap="wrap",
        width="100%",
    )


def tracking_map_panel():
    return rx.vstack(
        rx.hstack(
            rx.icon(tag="map", size=17, color=text()),
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
        tracking_legend(),
        align="start",
        spacing="4",
        padding="24px",
        border=f"1px solid {border()}",
        border_radius="14px",
        background=surface(),
        box_shadow=theme_value("0 1px 3px rgba(16, 24, 32, 0.06)", "none"),
        width="100%",
    )


def event_badge(flag):
    return rx.cond(
        flag == "harsh_brake",
        rx.text("Резкое торможение", color="#e5484d", font_size="11px", font_weight="700"),
        rx.cond(
            flag == "harsh_accel",
            rx.text("Резкий разгон", color="#f5a623", font_size="11px", font_weight="700"),
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
            transition="width 400ms ease",
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
            rx.text(v["label"], color=text(), font_size="14px", font_weight="800"),
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
        box_shadow=theme_value("0 1px 3px rgba(16, 24, 32, 0.06)", "none"),
        width="100%",
    )


def rating_row(v):
    return rx.hstack(
        rx.box(width="8px", height="8px", min_width="8px", border_radius="50%", background=v["color"]),
        rx.text(v["label"], color=text(), font_size="13px", font_weight="700"),
        rx.spacer(),
        rx.text(v["harsh_count"], color=muted(), font_size="12px"),
        rx.text(" рывков", color=muted(), font_size="12px"),
        rx.text(v["score"], color=text(), font_size="14px", font_weight="800"),
        spacing="2",
        align="center",
        width="100%",
        padding="10px 12px",
        border_radius="9px",
        background=surface_alt(),
    )


def rating_panel():
    return rx.vstack(
        rx.hstack(
            rx.icon(tag="award", size=17, color=text()),
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
        padding="24px",
        border=f"1px solid {border()}",
        border_radius="14px",
        background=surface(),
        box_shadow=theme_value("0 1px 3px rgba(16, 24, 32, 0.06)", "none"),
        width="100%",
    )


def event_log_panel():
    return rx.vstack(
        rx.hstack(
            rx.icon(tag="list", size=17, color=text()),
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
        padding="24px",
        border=f"1px solid {border()}",
        border_radius="14px",
        background=surface(),
        box_shadow=theme_value("0 1px 3px rgba(16, 24, 32, 0.06)", "none"),
        width="100%",
    )


def tracking_page():
    return page_shell(
        topbar(
            "Трекинг",
            "Симуляция движения машин по маршрутам: резкий газ/тормоз, расход топлива, рейтинг водителей.",
        ),
        tracking_controls(),
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
        tracking_map_panel(),
        rx.grid(
            rx.foreach(State.vehicles, vehicle_card),
            columns="2",
            spacing="4",
            width="100%",
        ),
        rx.grid(
            rating_panel(),
            event_log_panel(),
            columns="2",
            spacing="4",
            width="100%",
            align_items="start",
        ),
    )


def settings_toggle_row(label, hint, value, on_change):
    return rx.hstack(
        rx.vstack(
            rx.text(label, color=text(), font_size="14px", font_weight="700"),
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


def settings_page():
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
    )


def main_content():
    return rx.match(
        State.current_page,
        ("Заказы", orders_page()),
        ("Маршруты", routes_page()),
        ("Трекинг", tracking_page()),
        ("История", history_page()),
        ("Настройки", settings_page()),
        overview_page(),
    )


def dashboard():
    return rx.hstack(
        sidebar(),
        main_content(),
        align="start",
        spacing="0",
        min_height="100vh",
        background=page_bg(),
    )


app = rx.App()
app.add_page(dashboard, route="/", title="Обработка заказов", on_load=State.load_history)
