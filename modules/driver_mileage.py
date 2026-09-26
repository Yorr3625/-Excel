"""Daily driver odometer records tied to an active vehicle assignment."""

from __future__ import annotations

import json
import os
import tempfile
import threading
from datetime import date, datetime, timezone
from zoneinfo import ZoneInfo

from modules import paths


SCHEMA_VERSION = 1
MOSCOW_TIMEZONE = ZoneInfo("Europe/Moscow")
MILEAGE_FILE = paths.DRIVER_MILEAGE_FILE

_LOCK = threading.RLock()


class DriverMileageError(ValueError):
    """The daily mileage entry cannot be accepted."""


class DriverMileageConflict(DriverMileageError):
    """A different mileage value is already recorded for this day."""


def _now() -> datetime:
    return datetime.now(timezone.utc)


def today_key(now: datetime | None = None) -> str:
    current = now or _now()
    if current.tzinfo is None:
        current = current.replace(tzinfo=timezone.utc)
    return current.astimezone(MOSCOW_TIMEZONE).date().isoformat()


def _empty() -> dict:
    return {"schema_version": SCHEMA_VERSION, "records": []}


def _read() -> dict:
    try:
        data = json.loads(MILEAGE_FILE.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return _empty()
    except (OSError, UnicodeError, json.JSONDecodeError) as error:
        raise DriverMileageError("Журнал пробега недоступен") from error
    if not isinstance(data, dict) or data.get("schema_version") != SCHEMA_VERSION:
        raise DriverMileageError("Неподдерживаемая версия журнала пробега")
    records = data.get("records")
    if not isinstance(records, list):
        raise DriverMileageError("Журнал пробега повреждён")
    return {"schema_version": SCHEMA_VERSION, "records": records}


def _write(data: dict) -> None:
    MILEAGE_FILE.parent.mkdir(parents=True, exist_ok=True)
    temporary: str | None = None
    try:
        descriptor, temporary = tempfile.mkstemp(
            prefix=f".{MILEAGE_FILE.name}.", suffix=".tmp", dir=str(MILEAGE_FILE.parent)
        )
        with os.fdopen(descriptor, "w", encoding="utf-8", newline="\n") as stream:
            json.dump(data, stream, ensure_ascii=False, indent=2)
            stream.write("\n")
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, MILEAGE_FILE)
        temporary = None
    except OSError as error:
        raise DriverMileageError("Не удалось сохранить пробег") from error
    finally:
        if temporary:
            try:
                os.unlink(temporary)
            except OSError:
                pass


def _text(value: object) -> str:
    return str(value or "").strip()


def _odometer(value: object) -> int:
    if isinstance(value, bool):
        raise DriverMileageError("Пробег должен быть целым неотрицательным числом")
    text = _text(value)
    if not text or not text.isdigit():
        raise DriverMileageError("Пробег должен быть целым неотрицательным числом")
    try:
        odometer = int(text)
    except ValueError as error:
        raise DriverMileageError("Пробег должен быть целым неотрицательным числом") from error
    if odometer > 9_999_999:
        raise DriverMileageError("Слишком большое значение пробега")
    return odometer


def _record_for(records: list[dict], driver_id: str, vehicle_id: str, day: str) -> dict | None:
    return next(
        (
            record
            for record in records
            if record.get("driver_id") == driver_id
            and record.get("vehicle_id") == vehicle_id
            and record.get("date") == day
        ),
        None,
    )


def get_record(driver_id: str, vehicle_id: str, day: str | None = None) -> dict | None:
    driver_id = _text(driver_id)
    vehicle_id = _text(vehicle_id)
    if not driver_id or not vehicle_id:
        return None
    with _LOCK:
        record = _record_for(_read()["records"], driver_id, vehicle_id, day or today_key())
        return dict(record) if record else None


def record_mileage(
    driver_id: str,
    vehicle_id: str,
    vehicle_name: str,
    vehicle_plate: str,
    odometer_km: object,
    day: str | None = None,
) -> tuple[dict, bool]:
    """Persist one reading and return it with an idempotency flag."""

    driver_id = _text(driver_id)
    vehicle_id = _text(vehicle_id)
    if not driver_id or not vehicle_id:
        raise DriverMileageError("Не найден назначенный автомобиль")
    odometer = _odometer(odometer_km)
    day = day or today_key()
    if not isinstance(day, str):
        raise DriverMileageError("Некорректная дата пробега")
    try:
        date.fromisoformat(day)
    except ValueError as error:
        raise DriverMileageError("Некорректная дата пробега") from error

    with _LOCK:
        data = _read()
        existing = _record_for(data["records"], driver_id, vehicle_id, day)
        if existing:
            if existing.get("odometer_km") == odometer:
                return dict(existing), True
            raise DriverMileageConflict("Пробег за этот день уже зафиксирован")
        record = {
            "driver_id": driver_id,
            "vehicle_id": vehicle_id,
            "vehicle_name": _text(vehicle_name),
            "vehicle_plate": _text(vehicle_plate),
            "date": day,
            "odometer_km": odometer,
            "recorded_at": _now().astimezone(timezone.utc).isoformat(timespec="seconds"),
        }
        data["records"].append(record)
        _write(data)
        return dict(record), False
