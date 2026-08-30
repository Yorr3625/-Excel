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
        _reload_mail_items=lambda: reload_calls.append(True),
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
