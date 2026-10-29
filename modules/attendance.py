"""Посещаемость и распределение сотрудников по датам."""

from __future__ import annotations

import json
import os
import re
import tempfile
from copy import deepcopy
from datetime import date
from pathlib import Path
from threading import RLock

from modules import paths

ATTENDANCE_FILE = paths.ATTENDANCE_FILE
DEFAULT_SHIFT_START = "08:00"
STATUSES = {"unmarked", "present", "late", "absent"}
_LOCK = RLock()


class AttendanceError(ValueError):
    pass


def _empty() -> dict:
    return {"version": 1, "shift_start": DEFAULT_SHIFT_START, "days": {}}


def _time(value: str, label: str) -> str:
    value = str(value).strip()
    if not re.fullmatch(r"\d{1,2}:\d{2}", value):
        raise AttendanceError(f"{label}: укажите время в формате ЧЧ:ММ")
    hour, minute = map(int, value.split(":"))
    if not 0 <= hour <= 23 or not 0 <= minute <= 59:
        raise AttendanceError(f"{label}: время должно быть от 00:00 до 23:59")
    return f"{hour:02d}:{minute:02d}"


def _date_key(value: str | date | None) -> str:
    if value is None:
        return date.today().isoformat()
    if isinstance(value, date):
        return value.isoformat()
    try:
        return date.fromisoformat(value).isoformat()
    except (TypeError, ValueError) as error:
        raise AttendanceError("Укажите корректную дату YYYY-MM-DD") from error


def _load() -> dict:
    try:
        data = json.loads(ATTENDANCE_FILE.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return _empty()
    except (OSError, UnicodeError, json.JSONDecodeError) as error:
        raise AttendanceError("Не удалось прочитать журнал посещаемости") from error
    if not isinstance(data, dict) or data.get("version") != 1 or not isinstance(data.get("days"), dict):
        raise AttendanceError("Повреждён формат журнала посещаемости")
    _time(data.get("shift_start", DEFAULT_SHIFT_START), "Начало смены")
    for day_key, day in data["days"].items():
        _date_key(day_key)
        if not isinstance(day, dict):
            raise AttendanceError("Повреждена запись дня посещаемости")
        for field in ("assignments", "records", "vehicles"):
            if not isinstance(day.get(field), dict):
                raise AttendanceError("Повреждена запись дня посещаемости")
        if not all(isinstance(key, str) and isinstance(value, str) for key, value in day["assignments"].items()):
            raise AttendanceError("Повреждены назначения сотрудников")
        for record in day["records"].values():
            if not isinstance(record, dict) or record.get("status") not in STATUSES:
                raise AttendanceError("Повреждён статус посещаемости")
            if not all(isinstance(record.get(field, ""), str) for field in ("arrived_at", "comment", "vehicle_name")):
                raise AttendanceError("Повреждена запись посещаемости")
            if record.get("arrived_at"):
                _time(record["arrived_at"], "Время прихода")
        if not all(isinstance(settings, dict) for settings in day["vehicles"].values()):
            raise AttendanceError("Повреждены настройки машин")
    return data


def _save(data: dict) -> None:
    path = Path(ATTENDANCE_FILE)
    temporary: str | None = None
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", dir=path.parent, prefix=f".{path.name}.", delete=False) as stream:
            temporary = stream.name
            json.dump(data, stream, ensure_ascii=False, indent=2)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
        temporary = None
    except OSError as error:
        raise AttendanceError("Не удалось сохранить журнал посещаемости") from error
    finally:
        if temporary is not None:
            Path(temporary).unlink(missing_ok=True)


def _day(data: dict, value: str | date | None) -> dict:
    key = _date_key(value)
    return data["days"].setdefault(key, {"assignments": {}, "records": {}, "vehicles": {}})


def load_shift_start() -> str:
    with _LOCK:
        return _time(_load().get("shift_start", DEFAULT_SHIFT_START), "Начало смены")


def save_shift_start(value: str) -> str:
    normalized = _time(value, "Начало смены")
    with _LOCK:
        data = _load()
        data["shift_start"] = normalized
        _save(data)
    return normalized


def load_assignments(value: str | date | None = None) -> dict[str, str]:
    with _LOCK:
        return dict(_day(_load(), value)["assignments"])


def assign_employee(employee_id: str, vehicle_id: str = "", value: str | date | None = None) -> dict[str, str]:
    employee_id = str(employee_id).strip()
    vehicle_id = str(vehicle_id).strip()
    if not employee_id:
        raise AttendanceError("Сотрудник не выбран")
    with _LOCK:
        data = _load()
        day = _day(data, value)
        if vehicle_id and day["records"].get(employee_id, {}).get("status") == "absent":
            raise AttendanceError("Отсутствующего сотрудника нельзя назначить на машину")
        if vehicle_id:
            day["assignments"][employee_id] = vehicle_id
        else:
            day["assignments"].pop(employee_id, None)
        _save(data)
        return dict(day["assignments"])


def clear_vehicle_assignments(vehicle_id: str, value: str | date | None = None) -> dict[str, str]:
    with _LOCK:
        data = _load()
        day = _day(data, value)
        day["assignments"] = {employee: assigned for employee, assigned in day["assignments"].items() if assigned != vehicle_id}
        day["vehicles"].pop(vehicle_id, None)
        _save(data)
        return dict(day["assignments"])


def load_records(value: str | date | None = None) -> dict[str, dict]:
    with _LOCK:
        return deepcopy(_day(_load(), value)["records"])


def update_record(
    employee_id: str,
    status: str,
    arrived_at: str = "",
    comment: str = "",
    value: str | date | None = None,
    vehicle_name: str | None = None,
) -> dict[str, dict]:
    employee_id = str(employee_id).strip()
    if not employee_id:
        raise AttendanceError("Сотрудник не выбран")
    if status not in STATUSES:
        raise AttendanceError("Неизвестный статус посещаемости")
    with _LOCK:
        data = _load()
        day = _day(data, value)
        if status in {"present", "late"}:
            arrived_at = _time(arrived_at, "Время прихода")
            shift_start = _time(data.get("shift_start", DEFAULT_SHIFT_START), "Начало смены")
            status = "late" if arrived_at > shift_start else "present"
        else:
            arrived_at = ""
        previous = day["records"].get(employee_id, {})
        day["records"][employee_id] = {
            "status": status,
            "arrived_at": arrived_at,
            "comment": str(comment).strip(),
            "vehicle_name": str(vehicle_name).strip() if vehicle_name is not None else previous.get("vehicle_name", ""),
            "shift_start": _time(data.get("shift_start", DEFAULT_SHIFT_START), "Начало смены"),
        }
        if status == "absent":
            day["assignments"].pop(employee_id, None)
        _save(data)
        return deepcopy(day["records"])


def load_vehicle_settings(value: str | date | None = None) -> dict[str, dict]:
    with _LOCK:
        return deepcopy(_day(_load(), value)["vehicles"])


def save_vehicle_settings(
    vehicle_id: str,
    route: str = "",
    departure: str = "08:00",
    capacity: int = 4,
    value: str | date | None = None,
) -> dict:
    if not str(vehicle_id).strip():
        raise AttendanceError("Машина не выбрана")
    departure = _time(departure, "Время выезда")
    if isinstance(capacity, bool) or not isinstance(capacity, int) or capacity < 1:
        raise AttendanceError("Количество мест должно быть положительным целым числом")
    settings = {"route": str(route).strip(), "departure": departure, "capacity": capacity}
    with _LOCK:
        data = _load()
        _day(data, value)["vehicles"][str(vehicle_id)] = settings
        _save(data)
    return settings


def remove_employee(employee_id: str, value: str | date | None = None) -> None:
    with _LOCK:
        data = _load()
        day = _day(data, value)
        day["assignments"].pop(str(employee_id), None)
        _save(data)
