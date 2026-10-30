import importlib


def test_legacy_fleet_pages_select_internal_tab():
    dashboard = importlib.import_module("orders_dashboard.orders_dashboard")
    state = type("StateProbe", (), {
        "fleet_tab": "Сотрудники",
        "mobile_menu_open": False,
        "routes_editor_open": False,
        "route_editor_baseline": [],
        "route_stores": [],
        "current_page": "Dashboard",
        "set_page": dashboard.State.set_page.fn,
        "load_fleet": lambda self: None,
        "load_assignment_page": lambda self: None,
        "load_attendance_page": lambda self: None,
    })()
    dashboard.State.set_page.fn(state, "Посещаемость")
    assert state.current_page == "Водители и транспорт"
    assert state.fleet_tab == "Посещаемость"


def test_unified_fleet_page_compiles():
    dashboard = importlib.import_module("orders_dashboard.orders_dashboard")
    dashboard.fleet_page()
    dashboard.main_content()
