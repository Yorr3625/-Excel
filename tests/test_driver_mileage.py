from datetime import datetime, timezone

import pytest

from modules import driver_mileage


@pytest.fixture
def mileage_journal(tmp_path, monkeypatch):
    journal = tmp_path / "driver_mileage.json"
    monkeypatch.setattr(driver_mileage, "MILEAGE_FILE", journal)
    return journal


def test_today_key_uses_moscow_calendar_day():
    assert driver_mileage.today_key(datetime(2026, 9, 25, 20, 59, tzinfo=timezone.utc)) == "2026-09-25"
    assert driver_mileage.today_key(datetime(2026, 9, 25, 21, 0, tzinfo=timezone.utc)) == "2026-09-26"


def test_record_mileage_is_idempotent_for_same_driver_vehicle_and_day(mileage_journal):
    record, idempotent = driver_mileage.record_mileage(
        "driver-1", "vehicle-1", "Газель", "А123ВС71", "12345", "2026-09-25"
    )

    repeated, repeated_idempotent = driver_mileage.record_mileage(
        "driver-1", "vehicle-1", "Газель", "А123ВС71", 12345, "2026-09-25"
    )

    assert mileage_journal.exists()
    assert idempotent is False
    assert repeated_idempotent is True
    assert repeated == record
    assert record["odometer_km"] == 12345
    assert record["date"] == "2026-09-25"


def test_record_mileage_rejects_different_reading_for_existing_record(mileage_journal):
    driver_mileage.record_mileage(
        "driver-1", "vehicle-1", "Газель", "А123ВС71", 12345, "2026-09-25"
    )

    with pytest.raises(driver_mileage.DriverMileageConflict):
        driver_mileage.record_mileage(
            "driver-1", "vehicle-1", "Газель", "А123ВС71", 12346, "2026-09-25"
        )


def test_record_mileage_keeps_records_for_vehicle_change(mileage_journal):
    first, _ = driver_mileage.record_mileage(
        "driver-1", "vehicle-1", "Газель", "А123ВС71", 12345, "2026-09-25"
    )
    second, _ = driver_mileage.record_mileage(
        "driver-1", "vehicle-2", "Фургон", "В456СD71", 54321, "2026-09-25"
    )

    assert first["vehicle_id"] == "vehicle-1"
    assert second["vehicle_id"] == "vehicle-2"
    assert driver_mileage.get_record("driver-1", "vehicle-1", "2026-09-25") == first
    assert driver_mileage.get_record("driver-1", "vehicle-2", "2026-09-25") == second


@pytest.mark.parametrize("value", ["", "12.5", "-1", True, "10000000"])
def test_record_mileage_requires_valid_integer_odometer(mileage_journal, value):
    with pytest.raises(driver_mileage.DriverMileageError):
        driver_mileage.record_mileage(
            "driver-1", "vehicle-1", "Газель", "А123ВС71", value, "2026-09-25"
        )


def test_record_mileage_requires_iso_day(mileage_journal):
    with pytest.raises(driver_mileage.DriverMileageError):
        driver_mileage.record_mileage(
            "driver-1", "vehicle-1", "Газель", "А123ВС71", 12345, "25.09.2026"
        )
