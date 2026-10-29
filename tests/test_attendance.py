import json
from concurrent.futures import ThreadPoolExecutor
from datetime import date

import pytest

from modules import attendance


@pytest.fixture(autouse=True)
def isolated_attendance(tmp_path, monkeypatch):
    path = tmp_path / "attendance.json"
    monkeypatch.setattr(attendance, "ATTENDANCE_FILE", path)
    return path


def test_missing_file_does_not_mark_anyone_present(isolated_attendance):
    assert attendance.load_records("2026-10-29") == {}
    assert attendance.load_assignments("2026-10-29") == {}
    assert attendance.load_vehicle_settings("2026-10-29") == {}
    assert attendance.load_shift_start() == "08:00"
    assert not isolated_attendance.exists()


def test_assignments_and_records_are_isolated_by_date():
    attendance.assign_employee("employee-1", "vehicle-1", "2026-10-29")
    attendance.update_record("employee-1", "present", "08:25", "Пробки", date(2026, 10, 29), vehicle_name="Газель · А123ВС")
    attendance.assign_employee("employee-1", "vehicle-2", "2026-10-30")

    assert attendance.load_assignments("2026-10-29") == {"employee-1": "vehicle-1"}
    assert attendance.load_assignments("2026-10-30") == {"employee-1": "vehicle-2"}
    assert attendance.load_records("2026-10-29")["employee-1"] == {
        "status": "late", "arrived_at": "08:25", "comment": "Пробки",
        "vehicle_name": "Газель · А123ВС", "shift_start": "08:00",
    }
    assert attendance.load_records("2026-10-30") == {}


def test_shift_start_is_normalized_and_saved():
    assert attendance.save_shift_start("8:05") == "08:05"
    assert attendance.load_shift_start() == "08:05"


@pytest.mark.parametrize("value", ["25:00", "08:60", "8:5", "tomorrow", "-1:00", ""])
def test_shift_start_validation(value):
    with pytest.raises(attendance.AttendanceError):
        attendance.save_shift_start(value)


@pytest.mark.parametrize("value", ["2026-02-30", "wrong", ""])
def test_date_validation(value):
    with pytest.raises(attendance.AttendanceError):
        attendance.load_records(value)


@pytest.mark.parametrize("arrived_at, expected", [("07:55", "present"), ("08:00", "present"), ("08:01", "late")])
def test_status_is_derived_from_arrival_time(arrived_at, expected):
    attendance.update_record("one", "present", arrived_at, value="2026-10-29")
    assert attendance.load_records("2026-10-29")["one"]["status"] == expected


def test_historical_shift_and_vehicle_are_preserved():
    attendance.update_record("one", "present", "08:10", value="2026-10-29", vehicle_name="Машина 1")
    attendance.save_shift_start("09:00")
    record = attendance.load_records("2026-10-29")["one"]
    assert record["shift_start"] == "08:00"
    assert record["status"] == "late"
    assert record["vehicle_name"] == "Машина 1"


def test_absent_employee_is_unassigned_and_cannot_be_reassigned():
    attendance.assign_employee("one", "vehicle", "2026-10-29")
    attendance.update_record("one", "absent", comment="Больничный", value="2026-10-29")
    assert attendance.load_assignments("2026-10-29") == {}
    with pytest.raises(attendance.AttendanceError):
        attendance.assign_employee("one", "vehicle", "2026-10-29")
    attendance.assign_employee("one", "vehicle", "2026-10-30")
    assert attendance.load_assignments("2026-10-30") == {"one": "vehicle"}


def test_unmarked_record_has_no_arrival():
    attendance.update_record("one", "unmarked", "08:25", value="2026-10-29")
    assert attendance.load_records("2026-10-29")["one"]["arrived_at"] == ""


def test_record_validation():
    with pytest.raises(attendance.AttendanceError):
        attendance.update_record("", "present", "08:00")
    with pytest.raises(attendance.AttendanceError):
        attendance.update_record("one", "unknown")
    with pytest.raises(attendance.AttendanceError):
        attendance.update_record("one", "present", "99:00")
    with pytest.raises(attendance.AttendanceError):
        attendance.assign_employee("", "vehicle")


def test_clear_vehicle_preserves_historical_assignments_and_records():
    for day in ("2026-10-29", "2026-10-30"):
        attendance.assign_employee("one", "vehicle-1", day)
        attendance.assign_employee("two", "vehicle-2", day)
        attendance.save_vehicle_settings("vehicle-1", "Центр", "08:30", 4, day)
    attendance.update_record("one", "present", "08:00", value="2026-10-29", vehicle_name="Газель")
    assert attendance.clear_vehicle_assignments("vehicle-1", "2026-10-30") == {"two": "vehicle-2"}
    assert attendance.load_assignments("2026-10-29")["one"] == "vehicle-1"
    assert attendance.load_records("2026-10-29")["one"]["vehicle_name"] == "Газель"
    assert attendance.load_vehicle_settings("2026-10-30") == {}
    assert attendance.load_vehicle_settings("2026-10-29")["vehicle-1"]["route"] == "Центр"


def test_vehicle_settings_roundtrip_and_validation():
    attendance.save_vehicle_settings("vehicle", " Центр ", "8:30", 6, "2026-10-29")
    assert attendance.load_vehicle_settings("2026-10-29") == {
        "vehicle": {"route": "Центр", "departure": "08:30", "capacity": 6},
    }
    with pytest.raises(attendance.AttendanceError):
        attendance.save_vehicle_settings("vehicle", capacity=0)
    with pytest.raises(attendance.AttendanceError):
        attendance.save_vehicle_settings("vehicle", capacity=1.5)
    with pytest.raises(attendance.AttendanceError):
        attendance.save_vehicle_settings("vehicle", departure="25:00")


@pytest.mark.parametrize("contents", ["broken json", "[]", '{"version": 99, "days": {}}', '{"version": 1, "days": {"2026-10-29": {"assignments": []}}}'])
def test_corrupt_file_is_never_overwritten(isolated_attendance, contents):
    isolated_attendance.write_text(contents, encoding="utf-8")
    with pytest.raises(attendance.AttendanceError):
        attendance.assign_employee("one", "vehicle")
    assert isolated_attendance.read_text(encoding="utf-8") == contents


def test_failed_atomic_replace_keeps_original(isolated_attendance, monkeypatch):
    attendance.assign_employee("one", "vehicle-1")
    before = isolated_attendance.read_bytes()

    def fail_replace(*args):
        raise OSError("disk unavailable")

    monkeypatch.setattr(attendance.os, "replace", fail_replace)
    with pytest.raises(attendance.AttendanceError):
        attendance.assign_employee("two", "vehicle-2")
    assert isolated_attendance.read_bytes() == before
    assert list(isolated_attendance.parent.glob(".attendance.json.*")) == []


def test_concurrent_updates_do_not_lose_assignments():
    with ThreadPoolExecutor(max_workers=8) as executor:
        list(executor.map(lambda number: attendance.assign_employee(str(number), "vehicle", "2026-10-29"), range(30)))
    assert len(attendance.load_assignments("2026-10-29")) == 30


def test_returned_records_and_settings_are_detached():
    attendance.update_record("one", "present", "08:00", value="2026-10-29")
    rows = attendance.load_records("2026-10-29")
    rows["one"]["status"] = "absent"
    assert attendance.load_records("2026-10-29")["one"]["status"] == "present"


def test_remove_employee_does_not_delete_history():
    attendance.assign_employee("one", "vehicle", "2026-10-29")
    attendance.update_record("one", "present", "08:00", value="2026-10-29")
    attendance.remove_employee("one", "2026-10-30")
    assert attendance.load_assignments("2026-10-29") == {"one": "vehicle"}
    assert attendance.load_records("2026-10-29")["one"]["status"] == "present"
