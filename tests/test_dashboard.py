from types import SimpleNamespace

import orders_dashboard.orders_dashboard as dashboard


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
