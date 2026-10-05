from types import SimpleNamespace

from modules import dashboard_sessions
from orders_dashboard import loading_page


def _record(status="new"):
    return {
        "id": "record-1",
        "revision": 0,
        "order_number": "42",
        "client_name": "ООО Ромашка",
        "processed_at": "2026-10-05T08:30:00+03:00",
        "mode": "Область",
        "mail_metadata": {"received_display": "05.10.2026 07:00"},
        "loading": {"status": status},
        "routes": [{"route_label": "Маршрут №1", "destinations": [{"name": "ФМ 10"}]}],
        "loading_lines": [
            {"id": "line-1", "name": "Помидоры", "unit": "kg", "planned_amount": "20", "loaded_box_count": ""},
            {"id": "line-2", "name": "Огурцы", "unit": "kg", "planned_amount": "5", "loaded_box_count": ""},
        ],
    }


def _state(router=None):
    state = SimpleNamespace(
        router=router or {},
        is_authorized=False,
        principal={},
        order_options=[],
        order_option_labels=[],
        selected_order_label="",
        selected_order_id="",
        back_target="/",
        selected_record={},
        summary_order_number="",
        summary_client_name="",
        summary_processed_at="",
        summary_mode="",
        summary_routes="",
        summary_received_at="",
        summary_position_count=0,
        total_ordered_kg="0",
        total_loaded_boxes="",
        loading_rows=[],
        draft_box_counts={},
        summary_expanded=True,
        is_read_only=False,
        is_dirty=False,
        pending_order_id="",
        pending_exit=False,
        discard_confirmation_open=False,
        status="",
        order_not_found=False,
        save_completed=False,
    )
    state._refresh_options = loading_page.LoadingState._refresh_options.__get__(state)
    state._apply_record = loading_page.LoadingState._apply_record.__get__(state)
    state.select_order = loading_page.LoadingState.select_order.fn.__get__(state)
    return state


def test_loading_principal_accepts_dashboard_session():
    dashboard_sessions.reset_sessions()
    token = dashboard_sessions.create_session()

    principal = loading_page.loading_principal_for_router({
        "headers": {"cookie": f"{dashboard_sessions.SESSION_COOKIE}={token}"}
    })

    assert principal == {"kind": "dashboard", "id": "admin", "name": "Администратор"}


def test_loading_page_selects_known_query_order(monkeypatch):
    record = _record()
    monkeypatch.setattr(
        loading_page,
        "loading_principal_for_router",
        lambda router: {"kind": "loader", "id": "loader-1", "name": "Иван"},
    )
    monkeypatch.setattr(
        loading_page,
        "list_order_record_summaries",
        lambda: [{"id": "record-1", "order_number": "42", "client_name": "ООО Ромашка", "processed_at": record["processed_at"], "status": "new"}],
    )
    monkeypatch.setattr(loading_page, "load_order_record", lambda order_id: record)
    state = _state(SimpleNamespace(page=SimpleNamespace(params={"order": "record-1"})))

    loading_page.LoadingState.load_loading_page.fn(state)

    assert state.is_authorized is True
    assert state.selected_order_id == "record-1"
    assert state.back_target == "/"
    assert state.order_not_found is False
    assert state.draft_box_counts == {"line-1": "", "line-2": ""}


def test_loading_page_handles_unknown_query_order_without_error(monkeypatch):
    monkeypatch.setattr(
        loading_page,
        "loading_principal_for_router",
        lambda router: {"kind": "dashboard", "id": "admin", "name": "Администратор"},
    )
    monkeypatch.setattr(loading_page, "list_order_record_summaries", lambda: [])
    monkeypatch.setattr(
        loading_page,
        "load_order_record",
        lambda order_id: (_ for _ in ()).throw(loading_page.OrderRecordNotFound("Заказ не найден")),
    )
    state = _state(SimpleNamespace(page=SimpleNamespace(params={"order": "missing"})))

    loading_page.LoadingState.load_loading_page.fn(state)

    assert state.selected_order_id == ""
    assert state.order_not_found is True
    assert state.status == "Заказ не найден"


def test_loading_records_boxes_without_comparing_them_to_ordered_kilograms(monkeypatch):
    record = _record()
    state = _state()
    monkeypatch.setattr(loading_page, "load_order_record", lambda order_id: record)
    assert state._apply_record("record-1") is True

    loading_page.LoadingState.set_loaded_box_count.fn(state, "line-1", "19")
    loading_page.LoadingState.set_loaded_box_count.fn(state, "line-2", "6")

    assert [row["planned_kg"] for row in state.loading_rows] == ["20", "5"]
    assert [row["loaded_box_count"] for row in state.loading_rows] == ["19", "6"]
    assert all("difference" not in row for row in state.loading_rows)
    assert state.total_ordered_kg == "25"
    assert state.total_loaded_boxes == "25"
    assert state.is_dirty is True
    captured = {}
    updated = _record("loaded")
    updated["revision"] = 1
    updated["loading_lines"][0]["loaded_box_count"] = "19"
    updated["loading_lines"][1]["loaded_box_count"] = "6"
    monkeypatch.setattr(
        loading_page,
        "save_loading_update",
        lambda order_id, revision, box_counts, actor: captured.update(
            {"order_id": order_id, "revision": revision, "box_counts": box_counts, "actor": actor}
        ) or updated,
    )
    state.principal = {"kind": "loader", "id": "loader-1", "name": "Иван"}

    loading_page.LoadingState.save_loading.fn(state)

    assert captured["box_counts"] == {"line-1": "19", "line-2": "6"}
    assert state.status == "Загрузка сохранена"
    assert state.save_completed is True
    assert state.is_read_only is True


def test_dirty_order_switch_requires_confirmation(monkeypatch):
    state = _state()
    state.selected_order_id = "record-1"
    state.is_dirty = True

    result = loading_page.LoadingState.request_order.fn(state, "record-2")

    assert result is None
    assert state.pending_order_id == "record-2"
    assert state.discard_confirmation_open is True
