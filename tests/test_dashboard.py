from types import SimpleNamespace
import asyncio

import orders_dashboard.orders_dashboard as dashboard
from modules.config import MAX_ROUTES
from modules.weight_log import STAGE_LOADING, STAGE_STORE_SHIPMENT, STAGE_UNLOADING


def test_refresh_mail_config_is_registered_and_loads_state(monkeypatch):
    reload_calls = []
    config = {
        "email": "orders@example.com",
        "check_interval_minutes": 15,
    }

    monkeypatch.setattr(dashboard, "load_mail_config", lambda: config)
    monkeypatch.setattr(dashboard, "is_configured", lambda value: value is config)
    monkeypatch.setattr(
        dashboard,
        "mail_sources_config",
        lambda value: [{"name": "Основной склад"}],
    )
    monkeypatch.setattr(dashboard, "load_mail_error_log", lambda: ["ошибка"])

    state = SimpleNamespace(
        mail_source="Старый источник",
        mail_credentials_editing=False,
        mail_status="",
        _set_mail_categories=lambda source_configs: None,
        _reload_mail_items=lambda source_configs=None: reload_calls.append(True),
    )

    dashboard.State.refresh_mail_config.fn(state)

    assert state.mail_configured is True
    assert state.mail_email == "orders@example.com"
    assert state.mail_app_password == ""
    assert state.mail_interval == 15
    assert state.mail_sources == ["Все", "Основной склад"]
    assert state.mail_source == "Все"
    assert state.mail_error_log == ["ошибка"]
    assert reload_calls == [True]


def test_take_mail_order_opens_invoice_details(monkeypatch):
    detected_modes = []
    mail_items = [
        {
            "kind": "orders",
            "file": "заказ.xlsx",
            "path": "data/orders/заказ.xlsx",
            "received_at": "2026-11-10T18:30:00+03:00",
            "received_display": "10.11.2026 18:30",
            "verdict": {"ok": True, "mode": "Город"},
        },
        {
            "kind": "invoices",
            "file": "ФМ 40, МДВ 11.11.2026.pdf",
            "path": "data/invoices/ФМ 40, МДВ 11.11.2026.pdf",
            "received_at": "2026-11-11T09:00:00+03:00",
            "received_display": "11.11.2026 09:00",
            "order_file": "",
        },
    ]
    state = SimpleNamespace(
        invoice_search="старый поиск",
        order_detail_status="старый статус",
        order_details_open=False,
        detect_and_set_mode=lambda: detected_modes.append(True),
        _mail_item_for_view=dashboard.State._mail_item_for_view,
    )
    state._filter_invoice_candidates = (
        dashboard.State._filter_invoice_candidates.__get__(state)
    )
    state._refresh_order_invoices = (
        dashboard.State._refresh_order_invoices.__get__(state)
    )
    state._show_order_details = dashboard.State._show_order_details.__get__(state)
    monkeypatch.setattr(dashboard, "load_mail_items", lambda: mail_items)
    monkeypatch.setattr(dashboard, "was_processed", lambda filename: "")

    dashboard.State.take_mail_order.fn(
        state,
        "data/orders/заказ.xlsx",
        "заказ.xlsx",
        "10.11.2026 18:30",
    )

    assert state.selected_file == "заказ.xlsx"
    assert state.uploaded_file_path == "data/orders/заказ.xlsx"
    assert state.output_file == ""
    assert state.log_file == ""
    assert state.error_text == ""
    assert state.status == "Файл из почты: заказ.xlsx"
    assert state.duplicate_note == ""
    assert detected_modes == [True]
    assert state.current_page == "Заказы"
    assert state.selected_order == "заказ.xlsx"
    assert state.selected_order_time == "10.11.2026 18:30"
    assert state.selected_order_time_label == "Получен"
    assert state.order_detail_tab == "Накладные"
    assert state.invoice_search == ""
    assert state.order_detail_status == ""
    assert state.order_details_open is True
    assert state.available_invoices_title == "Подходящие накладные · Город"
    assert [item["file"] for item in state.available_invoices] == [
        "ФМ 40, МДВ 11.11.2026.pdf"
    ]


def test_accountant_category_filter_separates_uncategorized_items(monkeypatch):
    source_configs = [
        {
            "name": "Бухгалтер",
            "email": "zosya-c@mail.ru",
            "kind": "invoices",
            "categories": [
                {"name": "Молоко", "markers": ("фм 40", "мдв")},
                {"name": "Парус", "markers": ("парус",)},
                {"name": "Краймери", "markers": ("краймар", "краймери")},
            ],
        },
    ]
    items = [
        {
            "kind": "invoices",
            "file": "накладная.pdf",
            "subject": "ПАРУС",
            "source_name": "Бухгалтер",
        },
        {
            "kind": "invoices",
            "file": "накладная.pdf",
            "subject": "КРАЙМАР",
            "source_name": "Бухгалтер",
        },
        {
            "kind": "invoices",
            "file": "накладная.pdf",
            "subject": "ФМ 40, МДВ",
            "source_name": "Бухгалтер",
        },
        {
            "kind": "invoices",
            "file": "неизвестная накладная.pdf",
            "source_name": "Бухгалтер",
        },
        {
            "kind": "message",
            "file": "",
            "subject": "Спецификация27.08.26 ПАРУС.xls",
            "source_name": "Бухгалтер",
        },
    ]
    state = SimpleNamespace(
        mail_source="Бухгалтер",
        mail_category="Все",
        mail_kind_filter="Все сообщения",
    )
    state._filter_mail_items = dashboard.State._filter_mail_items.__get__(state)
    state._set_mail_categories = dashboard.State._set_mail_categories.__get__(state)
    state._reload_mail_items = dashboard.State._reload_mail_items.__get__(state)
    state._mail_item_for_view = dashboard.State._mail_item_for_view
    monkeypatch.setattr(dashboard, "mail_sources_config", lambda config=None: source_configs)
    monkeypatch.setattr(dashboard, "load_mail_config", lambda: {})
    monkeypatch.setattr(dashboard, "load_mail_items", lambda: items)

    state._set_mail_categories(source_configs)
    state._reload_mail_items(source_configs)

    assert state.mail_categories == [
        "Все",
        "Молоко",
        "Парус",
        "Краймери",
        "Без категории",
    ]
    assert [item["category"] for item in state.mail_all_items] == [
        "Парус",
        "Краймери",
        "Молоко",
        "",
        "",
    ]

    for category, expected_subject in (
        ("Молоко", "ФМ 40, МДВ"),
        ("Парус", "ПАРУС"),
        ("Краймери", "КРАЙМАР"),
    ):
        dashboard.State.set_mail_category.fn(state, category)
        assert [item["subject"] for item in state.mail_items] == [expected_subject]
        assert all(item["is_invoice"] for item in state.mail_items)

    dashboard.State.set_mail_category.fn(state, "Без категории")

    assert [item["file"] for item in state.mail_items] == [
        "неизвестная накладная.pdf",
        "Без вложения",
    ]


def test_history_order_details_keep_processed_time_label():
    refreshes = []
    state = SimpleNamespace(
        invoice_search="старый поиск",
        order_detail_status="старый статус",
        order_details_open=False,
        _refresh_order_invoices=lambda: refreshes.append(True),
    )
    state._show_order_details = dashboard.State._show_order_details.__get__(state)

    dashboard.State.open_order_details.fn(
        state,
        "заказ.xlsx",
        "10.11.2026 19:00",
    )

    assert state.selected_order == "заказ.xlsx"
    assert state.selected_order_time == "10.11.2026 19:00"
    assert state.selected_order_time_label == "Обработан"
    assert state.order_detail_tab == "Накладные"
    assert state.invoice_search == ""
    assert state.order_detail_status == ""
    assert state.order_details_open is True
    assert refreshes == [True]


def test_load_invoice_ocr_uses_processed_orders_and_journal(monkeypatch):
    state = SimpleNamespace(
        invoice_ocr_order="устаревший.xlsx",
        invoice_ocr_order_options=[],
        invoice_ocr_entries=[],
        invoice_ocr_status="",
    )
    monkeypatch.setattr(
        dashboard,
        "load_processed_files",
        lambda: {"старый.xlsx": "2026-01-01", "новый.xlsx": "2026-02-01"},
    )
    monkeypatch.setattr(
        dashboard,
        "load_invoice_entries",
        lambda: [
            {
                "id": "record",
                "saved_at": "2026-02-01T10:00:00",
                "order_file": "новый.xlsx",
                "route": "Маршрут №1",
                "lines": [{"name": "Банан"}],
                "total": "3500",
            }
        ],
    )

    dashboard.State.load_invoice_ocr.fn(state)

    assert state.invoice_ocr_order_options == ["новый.xlsx", "старый.xlsx"]
    assert state.invoice_ocr_order == ""
    assert state.invoice_ocr_entries[0]["line_count"] == 1


def test_invoice_ocr_line_change_recalculates_total():
    state = SimpleNamespace(
        invoice_ocr_rows=[
            {
                "id": "line",
                "name": "Банан",
                "unit": "кг",
                "quantity": "2",
                "unit_price": "140",
                "line_total": "280",
            }
        ],
        invoice_ocr_status="старый статус",
    )

    dashboard.State.set_invoice_ocr_line_field.fn(state, "line", "quantity", "3")

    assert state.invoice_ocr_rows[0]["quantity"] == "3"
    assert state.invoice_ocr_rows[0]["line_total"] == "420"
    assert state.invoice_ocr_status == ""


def test_add_route_increments_count_and_selects_new_route(monkeypatch):
    saved_counts = []
    monkeypatch.setattr(dashboard, "save_route_count", lambda count: saved_counts.append(count))
    state = SimpleNamespace(
        active_route_count=4,
        selected_route_index=0,
        collapsed_route_indices=[],
        routes_status="",
    )

    dashboard.State.add_route.fn(state)

    assert state.active_route_count == 5
    assert state.selected_route_index == 4
    assert state.route_add_index == 4
    assert saved_counts == [5]
    assert "Маршрут №5" in state.routes_status


def test_add_route_stops_at_max_routes(monkeypatch):
    monkeypatch.setattr(dashboard, "save_route_count", lambda count: (_ for _ in ()).throw(
        AssertionError("не должно сохраняться при достижении предела")
    ))
    state = SimpleNamespace(active_route_count=MAX_ROUTES, selected_route_index=2, routes_status="")

    dashboard.State.add_route.fn(state)

    assert state.active_route_count == MAX_ROUTES
    assert state.selected_route_index == 2
    assert str(MAX_ROUTES) in state.routes_status


def test_select_route_parses_name_and_ignores_out_of_range():
    state = SimpleNamespace(active_route_count=5, selected_route_index=0)

    dashboard.State.select_route.fn(state, "Маршрут №3")
    assert state.selected_route_index == 2

    dashboard.State.select_route.fn(state, "Маршрут №8")
    assert state.selected_route_index == 2

    dashboard.State.select_route.fn(state, "не маршрут")
    assert state.selected_route_index == 2


def test_add_store_and_remove_store_operate_on_selected_route():
    state = SimpleNamespace(
        selected_route_index=1,
        route_stores=[["фм 1"], ["фм 2"]],
        new_store_input="  Новый магазин  ",
    )

    dashboard.State.add_store.fn(state)
    assert state.route_stores == [["фм 1"], ["фм 2", "Новый магазин"]]
    assert state.new_store_input == ""

    dashboard.State.remove_store.fn(state, "фм 2")
    assert state.route_stores == [["фм 1"], ["Новый магазин"]]


def test_route_groups_use_real_driver_statuses_and_filter():
    state = SimpleNamespace(
        active_route_count=2,
        route_stores=[["фм 10", "фм 14"], ["магазин 21"]],
        route_driver_names=["Азер", "----"],
        real_vehicles=[
            {
                "route_index": 0,
                "stops": [
                    {"name": "фм 10", "status": "done"},
                    {"name": "фм 14", "status": "pending"},
                ],
            }
        ],
        search_query="",
        collapsed_route_indices=[1],
        route_add_index=0,
    )

    route_groups = dashboard.State.__dict__["route_groups"].fget
    groups = route_groups(state)

    assert [group["title"] for group in groups] == [
        "Маршрут №1 — Текстильщик",
        "Маршрут №2 — Центр",
    ]
    assert groups[0]["driver_initials"] == "АЗ"
    assert groups[0]["stores"][0]["status"] == "Отгружен"
    assert groups[0]["stores"][1]["status"] == "Ожидает"
    assert groups[0]["adding"] is True
    assert groups[1]["driver"] == "Водитель не назначен"
    assert groups[1]["collapsed"] is True

    state.search_query = "магазин 21"
    filtered = route_groups(state)
    assert len(filtered) == 1
    assert filtered[0]["index"] == 1
    assert [store["name"] for store in filtered[0]["stores"]] == ["магазин 21"]


def test_route_group_ui_state_and_indexed_removal():
    state = SimpleNamespace(
        active_route_count=2,
        selected_route_index=0,
        collapsed_route_indices=[],
        route_add_index=-1,
        new_store_input="старое",
        route_stores=[["фм 1"], ["фм 2", "фм 3"]],
    )
    state.remove_store = dashboard.State.remove_store.fn.__get__(state)

    dashboard.State.toggle_route_group.fn(state, 1)
    assert state.collapsed_route_indices == [1]
    dashboard.State.toggle_route_group.fn(state, 1)
    assert state.collapsed_route_indices == []

    dashboard.State.start_route_store_add.fn(state, 1)
    assert state.selected_route_index == 1
    assert state.route_add_index == 1
    assert state.new_store_input == ""

    dashboard.State.remove_route_store.fn(state, 1, "фм 2")
    assert state.route_stores == [["фм 1"], ["фм 3"]]

    dashboard.State.cancel_route_store_add.fn(state)
    assert state.route_add_index == -1


def test_save_invoice_ocr_draft_saves_then_clears(monkeypatch):
    saved = []
    state = SimpleNamespace(
        invoice_ocr_busy=False,
        invoice_ocr_order="заказ.xlsx",
        invoice_ocr_order_options=["заказ.xlsx"],
        invoice_ocr_route="Маршрут №1",
        invoice_ocr_draft_id="a" * 32,
        invoice_ocr_photo_refs=["invoice_ocr_photos/a/photo-01.jpg"],
        invoice_ocr_rows=[
            {
                "id": "line",
                "name": "Банан",
                "unit": "кг",
                "quantity": "25",
                "unit_price": "140",
                "line_total": "3500",
            }
        ],
        invoice_ocr_entries=[],
        invoice_ocr_photo_names=["photo.jpg"],
        invoice_ocr_raw_text="Банан кг 25 140",
        invoice_ocr_status="",
    )
    state._reset_invoice_ocr_draft = dashboard.State._reset_invoice_ocr_draft.__get__(state)
    monkeypatch.setattr(
        dashboard,
        "append_invoice_entry",
        lambda *args: saved.append(args) or {
            "id": "a" * 32,
            "saved_at": "2026-02-01T10:00:00",
            "order_file": "заказ.xlsx",
            "route": "Маршрут №1",
            "lines": [{"name": "Банан"}],
            "total": "3500",
        },
    )

    dashboard.State.save_invoice_ocr_draft.fn(state)

    assert len(saved) == 1
    assert state.invoice_ocr_status == "Накладная сохранена в журнале"
    assert state.invoice_ocr_draft_id == ""
    assert state.invoice_ocr_entries[0]["total"] == "3500"


def _weight_row(stage, total, order_file="заказ.xlsx", route="Маршрут №1"):
    return {
        "order_file": order_file,
        "route": route,
        "stage": stage,
        "total": total,
    }


def test_weight_reconciliation_rows_filters_by_order_and_route():
    rows = [
        _weight_row(STAGE_LOADING, 500, order_file="заказ.xlsx", route="Маршрут №1"),
        _weight_row(STAGE_LOADING, 300, order_file="другой.xlsx", route="Маршрут №2"),
        _weight_row(STAGE_LOADING, 100, order_file="", route=""),
    ]
    state = SimpleNamespace(
        weight_rows=rows,
        weight_filter_order=dashboard.WEIGHT_FILTER_ALL,
        weight_filter_route=dashboard.WEIGHT_FILTER_ALL,
    )
    reconciliation_rows = dashboard.State.__dict__["weight_reconciliation_rows"].fget
    assert reconciliation_rows(state) == rows

    state.weight_filter_order = "заказ.xlsx"
    assert reconciliation_rows(state) == [rows[0]]

    state.weight_filter_order = dashboard.WEIGHT_FILTER_ALL
    state.weight_filter_route = dashboard.WEIGHT_FILTER_UNBOUND
    assert reconciliation_rows(state) == [rows[2]]


def test_weight_reconciliation_flags_mismatch_between_stages():
    state = SimpleNamespace(
        weight_reconciliation_rows=[
            _weight_row(STAGE_LOADING, 500),
            _weight_row(STAGE_UNLOADING, 10),
            _weight_row(STAGE_STORE_SHIPMENT, 480),
        ]
    )

    result = dashboard.State.__dict__["weight_reconciliation"].fget(state)

    assert result == {
        "loaded": "500",
        "shipped": "480",
        "unloaded": "10",
        "difference": "10",
        "has_difference": "1",
    }


def test_weight_reconciliation_matches_when_stages_balance():
    state = SimpleNamespace(
        weight_reconciliation_rows=[
            _weight_row(STAGE_LOADING, 500),
            _weight_row(STAGE_UNLOADING, 10),
            _weight_row(STAGE_STORE_SHIPMENT, 490),
        ]
    )

    result = dashboard.State.__dict__["weight_reconciliation"].fget(state)

    assert result["difference"] == "0"
    assert result["has_difference"] == ""


def test_route_assignment_dialog_uses_only_active_fleet_entries(monkeypatch):
    state = SimpleNamespace(
        preview_ready=True,
        preview_source="upload.xlsx",
        uploaded_file_path="upload.xlsx",
        preview_mode="Город",
        mode="Город",
        active_route_count=2,
        route_driver_names=["Иван", "Старое имя"],
        route_assignments=[],
        route_assignment_open=False,
        status="",
    )
    monkeypatch.setattr(
        dashboard,
        "active_drivers",
        lambda: [
            {"id": "driver-1", "name": "Иван", "default_vehicle_id": "vehicle-1"},
        ],
    )
    monkeypatch.setattr(
        dashboard,
        "active_vehicles",
        lambda: [{"id": "vehicle-1", "name": "Газель", "plate": "А123ВС71"}],
    )

    dashboard.State.open_route_assignment_dialog.fn(state)

    assert state.route_assignment_open is True
    assert state.route_assignments == [
        {
            "route": "route_1",
            "label": "Маршрут №1",
            "driver_id": "driver-1",
            "driver_name": "Иван",
            "vehicle_id": "vehicle-1",
            "vehicle_name": "Газель",
            "vehicle_plate": "А123ВС71",
        },
        {
            "route": "route_2",
            "label": "Маршрут №2",
            "driver_id": "",
            "driver_name": "Старое имя",
            "vehicle_id": "",
            "vehicle_name": "",
            "vehicle_plate": "",
        },
    ]


def test_cancel_route_assignments_does_not_process_or_persist():
    state = SimpleNamespace(route_assignment_open=True, route_assignments=[{"route": "route_1"}])

    dashboard.State.cancel_route_assignments.fn(state)

    assert state.route_assignment_open is False
    assert state.route_assignments == []


def test_confirm_route_assignments_rejects_stale_preview():
    state = SimpleNamespace(
        preview_ready=False,
        preview_source="old.xlsx",
        uploaded_file_path="upload.xlsx",
        preview_mode="Город",
        mode="Город",
        route_assignment_open=True,
        route_assignments=[{"route": "route_1"}],
        status="",
    )
    state.cancel_route_assignments = dashboard.State.cancel_route_assignments.fn.__get__(state)

    dashboard.State.confirm_route_assignments.fn(state)

    assert state.route_assignment_open is False
    assert state.route_assignments == []
    assert "устарел" in state.status


def test_confirm_route_assignments_starts_processing_for_current_preview():
    calls = []
    state = SimpleNamespace(
        preview_ready=True,
        preview_source="upload.xlsx",
        uploaded_file_path="upload.xlsx",
        preview_mode="Город",
        mode="Город",
        route_assignment_open=True,
        route_assignments=[{"route": "route_1"}],
        process_order=lambda: calls.append(True),
    )

    dashboard.State.confirm_route_assignments.fn(state)

    assert state.route_assignment_open is False
    assert calls == [True]


def test_web_order_processing_does_not_open_file_on_server(monkeypatch):
    settings = {"open_file_after_processing": True, "open_folder_after_processing": True}
    passed_settings = []
    published = []
    monkeypatch.setattr(dashboard, "load_settings", lambda: settings)
    monkeypatch.setattr(dashboard, "load_stores", lambda path: {})
    monkeypatch.setattr(dashboard, "run_pipeline", lambda source, options, *args: (
        passed_settings.append(options) or ("result.xlsx", "order.log", {"route_totals": {}})
    ))
    monkeypatch.setattr(dashboard, "record_order_route_assignments", lambda *args: None)
    monkeypatch.setattr(
        dashboard.driver_orders, "publish_assignments",
        lambda *args: published.append(args),
    )
    monkeypatch.setattr(dashboard, "record_processing", lambda *args: None)
    monkeypatch.setattr(dashboard, "was_processed", lambda filename: "сегодня")
    state = SimpleNamespace(
        uploaded_file_path="upload.xlsx",
        preview_ready=True,
        preview_source="upload.xlsx",
        preview_mode="Город",
        mode="Город",
        active_route_count=1,
        route_assignments=[{"route": "route_1", "driver_id": "driver-1", "driver_name": "Иван"}],
        selected_file="upload.xlsx",
        load_history=lambda: None,
        _reset_preview=lambda: None,
    )

    dashboard.State.process_order.fn(state)

    assert state.status == "Обработка завершена"
    assert state.output_file == "result.xlsx"
    assert passed_settings == [{
        "open_file_after_processing": False,
        "open_folder_after_processing": False,
    }]
    assert settings["open_file_after_processing"] is True
    assert len(published) == 1


def test_login_authenticates_and_clears_credentials(monkeypatch):
    state = SimpleNamespace(
        login_username="admin",
        login_password="admin",
        login_error="старое сообщение",
        is_authenticated=False,
    )
    monkeypatch.setattr(dashboard, "verify_credentials", lambda username, password: True)

    redirect = dashboard.State.login.fn(state)

    assert state.is_authenticated is True
    assert state.login_username == ""
    assert state.login_password == ""
    assert state.login_error == ""
    assert redirect is not None


def test_login_rejects_invalid_credentials_and_clears_password(monkeypatch):
    state = SimpleNamespace(
        login_username="admin",
        login_password="wrong",
        login_error="",
        is_authenticated=False,
    )
    monkeypatch.setattr(dashboard, "verify_credentials", lambda username, password: False)

    result = dashboard.State.login.fn(state)

    assert result is None
    assert state.is_authenticated is False
    assert state.login_username == "admin"
    assert state.login_password == ""
    assert state.login_error == "Неверное имя пользователя или пароль."


def test_login_hides_auth_configuration_errors(monkeypatch):
    state = SimpleNamespace(
        login_username="admin",
        login_password="admin",
        login_error="",
        is_authenticated=False,
    )

    def unavailable(username, password):
        raise dashboard.AuthConfigurationError("повреждено")

    monkeypatch.setattr(dashboard, "verify_credentials", unavailable)

    dashboard.State.login.fn(state)

    assert state.is_authenticated is False
    assert state.login_password == ""
    assert state.login_error == "Вход временно недоступен."


def test_load_dashboard_redirects_anonymous_user_before_loading_history():
    state = SimpleNamespace(is_authenticated=False)

    redirect = dashboard.State.load_dashboard.fn(state)

    assert redirect is not None


def test_load_dashboard_loads_history_for_authenticated_user():
    calls = []
    state = SimpleNamespace(is_authenticated=True, load_history=lambda: calls.append(True))

    result = dashboard.State.load_dashboard.fn(state)

    assert result is None
    assert calls == [True]


def test_logout_stops_background_controls_and_resets_state():
    resets = []
    state = SimpleNamespace(
        mail_auto=True,
        tracking_running=True,
        real_watching=True,
        reset=lambda: resets.append(True),
    )

    redirect = dashboard.State.logout.fn(state)

    assert state.mail_auto is False
    assert state.tracking_running is False
    assert state.real_watching is False
    assert resets == [True]
    assert redirect is not None


def test_auth_middleware_allows_only_public_events_when_anonymous():
    class StateStore:
        async def get_state(self, state_class):
            assert state_class is dashboard.State
            return SimpleNamespace(is_authenticated=False)

    middleware = dashboard.DashboardAuthMiddleware()
    prefix = f"{dashboard.State.get_full_name()}."
    public_event = SimpleNamespace(name=f"{prefix}login", router_data={})
    protected_event = SimpleNamespace(name=f"{prefix}set_page", router_data={})

    assert asyncio.run(middleware.preprocess(None, StateStore(), public_event)) is None
    update = asyncio.run(middleware.preprocess(None, StateStore(), protected_event))

    assert update is not None
    assert len(update.events) == 1
    assert update.events[0].name == "_redirect"


def test_auth_middleware_allows_authenticated_and_driver_events():
    class StateStore:
        async def get_state(self, state_class):
            assert state_class is dashboard.State
            return SimpleNamespace(is_authenticated=True)

    middleware = dashboard.DashboardAuthMiddleware()
    dashboard_event = SimpleNamespace(
        name=f"{dashboard.State.get_full_name()}.set_page",
        router_data={},
    )
    driver_event = SimpleNamespace(name="DriverState.load_active_routes", router_data={})

    assert asyncio.run(middleware.preprocess(None, StateStore(), dashboard_event)) is None
    assert asyncio.run(middleware.preprocess(None, StateStore(), driver_event)) is None
