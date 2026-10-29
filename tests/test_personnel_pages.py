import importlib
from types import SimpleNamespace

import pytest

from modules import attendance, fleet


dashboard = importlib.import_module("orders_dashboard.orders_dashboard")


@pytest.fixture
def personnel(tmp_path, monkeypatch):
    monkeypatch.setattr(fleet, "FLEET_FILE", tmp_path / "fleet.json")
    monkeypatch.setattr(attendance, "ATTENDANCE_FILE", tmp_path / "attendance.json")
    vehicle = fleet.add_vehicle("Машина 1", "А123ВС", 56000, "Описание", "Заметки", True, "tracker-1")
    employee = fleet.add_driver("Иванов Сергей")
    state = SimpleNamespace(
        personnel_date="2026-10-29", assignment_search="", assignment_status="",
        assignment_vehicle_id="", assignment_form_open=False,
    )
    state.load_assignment_page = dashboard.State.load_assignment_page.fn.__get__(state)
    return state, vehicle, employee


def test_assignment_page_loads_existing_roster_and_excludes_absent(personnel):
    state, vehicle, employee = personnel
    attendance.assign_employee(employee["id"], vehicle["id"], state.personnel_date)
    state.load_assignment_page()
    assert state.assignment_columns[0]["count_label"] == "1 / 4"
    assert state.assignment_columns[0]["employees"][0]["name"] == employee["name"]
    attendance.update_record(employee["id"], "absent", value=state.personnel_date)
    state.load_assignment_page()
    assert state.assignment_unassigned == []
    assert state.assignment_columns[0]["employees"] == []


def test_editing_vehicle_preserves_existing_metadata(personnel):
    state, vehicle, employee = personnel
    state.assignment_vehicle_id = vehicle["id"]
    dashboard.State.save_assignment_vehicle.fn(state, {
        "name": "Новое имя", "plate": "А123ВС", "route": "Центр", "departure": "08:30", "capacity": "6",
    })
    updated = fleet.load_fleet()["vehicles"][0]
    assert updated["name"] == "Новое имя"
    assert updated["odometer_km"] == 56000
    assert updated["tracker_id"] == "tracker-1"
    assert updated["description"] == "Описание"
    assert updated["notes"] == "Заметки"
    assert attendance.load_vehicle_settings(state.personnel_date)[vehicle["id"]]["capacity"] == 6


def test_unknown_employee_and_vehicle_are_rejected(personnel):
    state, vehicle, employee = personnel
    dashboard.State.assign_employee.fn(state, "unknown", vehicle["id"])
    assert attendance.load_assignments(state.personnel_date) == {}
    dashboard.State.assign_employee.fn(state, employee["id"], "unknown")
    assert attendance.load_assignments(state.personnel_date) == {}


def test_expeditor_reuses_roster_without_driver_access(personnel):
    employee = fleet.add_driver("Петров Алексей", role="expeditor")
    assert fleet.employee_role(employee) == "expeditor"
    assert employee not in fleet.active_drivers()
    assert employee not in fleet.active_loaders()


def test_assignment_components_compile():
    dashboard._assignment_page()
    dashboard._attendance_page()
    dashboard.main_content()


def test_attendance_counts_real_marks_not_search_results(personnel):
    state, vehicle, employee = personnel
    state.attendance_search = "нет совпадений"
    state.attendance_message = ""
    attendance.update_record(employee["id"], "present", "08:25", "Пробки", state.personnel_date)
    dashboard.State.load_attendance_page.fn(state)
    assert state.attendance_total == 1
    assert state.attendance_present == 0
    assert state.attendance_late == 1
    assert all(group["rows"] == [] for group in state.attendance_groups)
    state.attendance_search = ""
    dashboard.State.load_attendance_page.fn(state)
    row = state.attendance_groups[1]["rows"][0]
    assert row["delay"] == "+25 мин"
    assert row["comment"] == "Пробки"


def test_unmarked_and_historical_inactive_employee(personnel):
    state, vehicle, employee = personnel
    state.attendance_search = ""
    state.attendance_message = ""
    dashboard.State.load_attendance_page.fn(state)
    assert state.attendance_present == 0
    assert state.attendance_groups[3]["count"] == 1
    attendance.update_record(employee["id"], "present", "07:55", value=state.personnel_date, vehicle_name="Архивная машина")
    fleet.update_driver(employee["id"], employee["name"], "", 5, False, "", "", "")
    dashboard.State.load_attendance_page.fn(state)
    assert state.attendance_total == 1
    assert state.attendance_groups[0]["rows"][0]["vehicle"] == "Архивная машина"


def test_mark_absent_preserves_comment_and_frees_assignment(personnel):
    state, vehicle, employee = personnel
    state.attendance_message = ""
    state.load_attendance_page = lambda: None
    state._save_employee_attendance = dashboard.State._save_employee_attendance.__get__(state)
    attendance.assign_employee(employee["id"], vehicle["id"], state.personnel_date)
    attendance.update_record(employee["id"], "present", "07:55", "Больничный", state.personnel_date)
    dashboard.State.mark_attendance.fn(state, employee["id"], "absent")
    record = attendance.load_records(state.personnel_date)[employee["id"]]
    assert record["comment"] == "Больничный"
    assert record["status"] == "absent"
    assert attendance.load_assignments(state.personnel_date) == {}
