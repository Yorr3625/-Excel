import json
from pathlib import Path
from types import SimpleNamespace

import orders_dashboard.orders_dashboard as dashboard


def nodes(value):
    if isinstance(value, dict):
        yield value
        for child in value.values():
            yield from nodes(child)
    elif isinstance(value, list):
        for child in value:
            yield from nodes(child)


def classes(component):
    return [prop for node in nodes(component.render()) for prop in node.get("props", []) if prop.startswith("className:")]


def test_redesigned_pages_compile_and_use_scoped_containers():
    for factory in (dashboard.overview_page, dashboard.orders_page, dashboard.mail_page):
        assert str(factory().class_name).startswith('design-page')
    assert "dashboard-design" in str(dashboard.login_page().class_name)
    dashboard.dashboard_shell()


def test_today_has_six_independent_cards_and_one_order_summary():
    values = classes(dashboard.overview_page())
    assert values.count('className:"stage-card"') == 5
    assert values.count('className:"stage-card stage-card-return"') == 1
    assert values.count('className:"summary"') == 1
    assert values.count('className:"workflow"') == 1


def test_order_form_keeps_upload_preview_assignment_and_results():
    rendered = json.dumps(dashboard.orders_page().render(), default=str)
    for handler in ("handle_upload", "preview_order", "open_route_assignment_dialog", "set_order_client_name", "set_mode"):
        assert handler in rendered
    for class_name in ("order-workspace order-form", "order-grid", "confirmation-panel"):
        assert class_name in rendered
    assert dashboard.UPLOAD_ID in rendered


def test_mail_panels_and_real_actions_are_preserved():
    rendered = json.dumps(dashboard.mail_page().render(), default=str)
    for handler in ("check_mail_now", "check_mail_connection_now", "toggle_mail_auto", "clear_mail_errors",
                    "set_mail_kind_filter", "set_mail_source", "take_mail_order", "open_mail_attachment"):
        assert handler in rendered
    for class_name in ("mail-connection", "mail-errors", "mail-filters", "mail-inbox", "mail-card-actions"):
        assert class_name in rendered


def test_login_keeps_direct_authentication_and_accessible_fields():
    rendered = json.dumps(dashboard.login_page().render(), default=str)
    for identity in ("dashboard-login-username", "dashboard-login-password", "dashboard-login-error", "dashboard-login-submit"):
        assert identity in rendered
    assert "current-password" in rendered
    assert "autoComplete" in rendered
    assert 'type:\\"submit\\"' in rendered
    assert "/api/dashboard/login" in dashboard.DASHBOARD_LOGIN_JS
    assert "button?.disabled" in dashboard.DASHBOARD_LOGIN_JS
    assert "finally" in dashboard.DASHBOARD_LOGIN_JS
    assert "window.location.replace('/')" in dashboard.DASHBOARD_LOGIN_JS


def test_sidebar_collapse_does_not_change_mobile_menu_state():
    state = SimpleNamespace(sidebar_collapsed=False, mobile_menu_open=True)
    dashboard.State.toggle_sidebar.fn(state)
    assert state.sidebar_collapsed
    assert state.mobile_menu_open
    dashboard.State.toggle_sidebar.fn(state)
    assert not state.sidebar_collapsed


def test_new_icons_have_real_tabler_components():
    for name in ("arrow_right", "clock", "file_text", "layout_grid", "lock", "log_out", "menu",
                 "panel_left_open", "panel_left_close", "refresh_cw", "undo_2", "user"):
        assert dashboard.design_icon(name).tag != "IconHelpCircle"


def test_mockup_styles_are_scoped_and_do_not_replace_cabinet_palette():
    stylesheet = Path(__file__).parents[1] / "assets" / "dashboard-design.css"
    source = stylesheet.read_text(encoding="utf-8")
    assert 'html[data-theme="dark"] .dashboard-design.app' in source
    assert ".dashboard-design .stage-card" in source
    assert ".dashboard-design .login-main" in source
    assert "prefers-reduced-motion" in source
    assert "..design-page" not in source
    assert "login-.design-page" not in source
    assert ":root" not in source
    assert ".driver-" not in source
    assert ".loader-" not in source
