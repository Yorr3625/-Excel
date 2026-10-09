from pathlib import Path
from types import SimpleNamespace
import shutil
import subprocess
import pytest
import orders_dashboard.orders_dashboard as dashboard


def test_shared_theme_browser_behavior():
    node = shutil.which('node')
    if not node:
        pytest.skip('Node.js is required for shared-theme behavior tests')
    result = subprocess.run([node, '--test', str(Path(__file__).with_name('theme_preference_behavior.cjs')), str(Path(__file__).with_name('workspace_bootstrap_behavior.cjs'))], capture_output=True, text=True, encoding='utf-8', timeout=30)
    assert result.returncode == 0, result.stdout + result.stderr


def test_all_workspace_components_compile():
    dashboard.dashboard_shell()
    dashboard.loading_page()
    dashboard.driver_page()
    dashboard.loader_page()


def test_daily_overview_counts_exact_stages_and_return_scope(monkeypatch):
    seen = []
    monkeypatch.setattr(dashboard, 'list_route_trip_summaries', lambda day, mode: seen.append((day, mode)) or [
        {'stage': stage} for stage in ['Ожидает загрузки', 'Загрузка начата', 'Готов к отгрузке', 'Отгрузка идёт', 'Отгрузка завершена']
    ])
    monkeypatch.setattr(dashboard.goods_returns, 'list_returns', lambda: [{'status':'submitted'}, {'status':'accepted'}])
    state = SimpleNamespace(today_mode='Город', today_error='')
    dashboard.State.load_today_overview.fn(state)
    assert seen[0][1] == 'Город'
    assert (state.today_waiting, state.today_drafts, state.today_ready, state.today_shipping, state.today_completed, state.today_returns) == (1,1,1,1,1,1)
    assert not state.today_error


def test_daily_stage_link_uses_matching_direction_and_filter():
    state=SimpleNamespace(today_mode='Город', set_page=lambda page: page)
    assert dashboard.State.open_today_stage.fn(state, 'Загрузка начата') == 'Маршруты'
    assert state.dispatch_mode == 'Город'
    assert state.dispatch_stage == 'Загрузка начата'


def test_navigation_back_to_operations_preserves_template_guard():
    seen=[]
    state=SimpleNamespace(routes_editor_open=True, mobile_menu_open=True, close_routes_editor=lambda: seen.append('guard'))
    dashboard.State.navigate.fn(state,'Маршруты')
    assert seen == ['guard']
    assert not state.mobile_menu_open


def test_warehouse_measurement_has_one_native_string_input():
    import orders_dashboard.loading_page as loading

    row = dashboard.rx.Var.create({'id': 'line', 'order_id': 'order', 'route_key': 'route_4', 'destination_id': 'store', 'name': 'Яблоки', 'box_count': '2', 'weighing_id': 'portion'})
    control = loading._measurement_control(row, 'box_count', 'Ящики')
    field = control.children[1]
    assert field.tag == 'DebounceInput'
    assert str(field.element) == '"input"'
    assert str(field.debounce_timeout) == '350'
    assert str(field.force_notify_on_blur) == 'true'
    assert str(field.force_notify_by_enter) == 'true'
    for key in ('order_id', 'route_key', 'destination_id', 'id', 'weighing_id'):
        assert f'["{key}"]' in str(field.key)
    assert '"box_count"' in str(field.key)
    assert str(field.custom_attrs['type']) == '"text"'
    assert str(field.custom_attrs['input_mode']) == '"numeric"'
    for name in ('tare_weight_per_box_kg', 'gross_weight_kg'):
        weight = loading._measurement_control(row, name, 'Вес').children[1]
        assert str(weight.custom_attrs['type']) == '"text"'
        assert str(weight.custom_attrs['input_mode']) == '"decimal"'
