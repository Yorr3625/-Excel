"""Sidecar orders used by the authenticated driver workspace."""

from __future__ import annotations

import hashlib
import json
import os
import tempfile
import threading
from datetime import datetime
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any

from openpyxl import load_workbook

from modules import paths


SCHEMA_VERSION = 1
MAX_OPERATION_ID_LENGTH = 128
MAX_QUANTITY_DIGITS = 18


class DriverOrderError(ValueError):
    """Invalid driver order data or operation."""


class DriverOrderNotFound(DriverOrderError):
    """The requested sidecar or entity does not exist."""


class DriverOrderConflict(DriverOrderError):
    """The client is working from an obsolete revision."""


_LOCK = threading.RLock()


def _now() -> str:
    return datetime.now().isoformat(timespec="seconds")


def _decimal(value: Any, field: str = "quantity") -> Decimal:
    if isinstance(value, bool) or value is None:
        raise DriverOrderError(f"Некорректное значение {field}")
    try:
        number = Decimal(str(value).strip().replace(",", "."))
    except (InvalidOperation, AttributeError) as error:
        raise DriverOrderError(f"Некорректное значение {field}") from error
    if not number.is_finite() or number < 0:
        raise DriverOrderError(f"{field} не может быть отрицательным")
    if len(number.as_tuple().digits) > MAX_QUANTITY_DIGITS:
        raise DriverOrderError(f"Слишком большое значение {field}")
    return number


def _quantity(value: Any) -> str:
    number = _decimal(value)
    text = format(number, "f")
    if "." in text:
        text = text.rstrip("0").rstrip(".")
    return text or "0"


def _optional_quantity(value: Any) -> str:
    if value in (None, ""):
        return ""
    return _quantity(value)


def _sum(values: list[str]) -> Decimal:
    return sum((_decimal(value) for value in values), Decimal("0"))


def _public_number(value: Decimal) -> int | float:
    if value == value.to_integral_value():
        return int(value)
    return float(value)


def _atomic_write(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = None
    try:
        descriptor, temporary = tempfile.mkstemp(
            prefix=f".{path.name}.", suffix=".tmp", dir=str(path.parent)
        )
        with os.fdopen(descriptor, "w", encoding="utf-8", newline="\n") as stream:
            json.dump(payload, stream, ensure_ascii=False, indent=2)
            stream.write("\n")
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
        temporary = None
    except OSError as error:
        raise DriverOrderError("Не удалось сохранить заказ водителя") from error
    finally:
        if temporary:
            try:
                os.unlink(temporary)
            except OSError:
                pass


def _read(path: Path) -> dict:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as error:
        raise DriverOrderError("Файл заказа водителя повреждён или недоступен") from error
    if not isinstance(payload, dict) or payload.get("schema_version") != SCHEMA_VERSION:
        raise DriverOrderError("Неподдерживаемая версия заказа водителя")
    return payload


def _file_digest(path: Path) -> str:
    digest = hashlib.sha256()
    try:
        with path.open("rb") as stream:
            for chunk in iter(lambda: stream.read(1024 * 1024), b""):
                digest.update(chunk)
    except OSError as error:
        raise DriverOrderError("Результат заказа недоступен") from error
    return digest.hexdigest()


def _stable_id(*parts: str) -> str:
    return hashlib.sha256("\x1f".join(parts).encode("utf-8")).hexdigest()[:24]


def _route_number(route_key: str) -> int:
    try:
        number = int(route_key.removeprefix("route_"))
    except (AttributeError, ValueError) as error:
        raise DriverOrderError("Некорректный маршрут") from error
    if not 1 <= number <= 99:
        raise DriverOrderError("Некорректный маршрут")
    return number


def _sheet_store_columns(sheet) -> list[tuple[int, str]]:
    columns = []
    for column in range(3, sheet.max_column + 1):
        name = str(sheet.cell(1, column).value or "").strip()
        if name and name.casefold() != "сумма":
            columns.append((column, name))
    return columns


def _source_rows(sheet, store_columns: list[tuple[int, str]]) -> list[tuple[int, str]]:
    rows = []
    for row in range(2, sheet.max_row + 1):
        name = str(sheet.cell(row, 1).value or "").strip()
        if not name or name.casefold() == "итого":
            continue
        has_numeric = False
        for column, _store in store_columns:
            value = sheet.cell(row, column).value
            if value not in (None, ""):
                _decimal(value, "плановое количество")
                has_numeric = True
        if has_numeric:
            rows.append((row, name))
    return rows


def build_assignment_snapshot(
    output_file: str | Path,
    mode: str,
    assignment: dict,
    order_id: str | None = None,
) -> dict:
    """Build one driver's route snapshot from a processed route workbook."""
    output_path = Path(output_file)
    route_key = str(assignment.get("route", ""))
    route_number = _route_number(route_key)
    if not output_path.exists():
        raise DriverOrderError("Результат заказа не найден")

    order_id = order_id or _file_digest(output_path)
    assignment_id = _stable_id(
        order_id,
        route_key,
        str(assignment.get("driver_id", "")),
        str(assignment.get("vehicle_id", "")),
    )
    try:
        workbook = load_workbook(output_path, data_only=True, read_only=True)
        sheet = workbook[f"Маршрут №{route_number}"]
    except (OSError, KeyError, ValueError) as error:
        raise DriverOrderError("В результате нет листа назначенного маршрута") from error

    store_columns = _sheet_store_columns(sheet)
    rows = _source_rows(sheet, store_columns)
    stores = []
    for column, store_name in store_columns:
        store_id = _stable_id(order_id, route_key, "store", store_name)
        lines = []
        for row, product_name in rows:
            value = sheet.cell(row, column).value
            planned = _quantity(value) if value not in (None, "") else "0"
            lines.append({
                "line_id": _stable_id(order_id, route_key, store_name, str(row), product_name),
                "name": product_name,
                "unit": "",
                "required_qty": planned,
                "actual_qty": "",
            })
        stores.append({
            "store_id": store_id,
            "name": store_name,
            "status": "pending",
            "completed_at": "",
            "photo": "",
            "lines": lines,
        })

    return {
        "schema_version": SCHEMA_VERSION,
        "order_id": order_id,
        "assignment_id": assignment_id,
        "source_file": str(assignment.get("order_file", "")),
        "output_file": str(output_path),
        "mode": str(mode or ""),
        "route_key": route_key,
        "route_label": str(assignment.get("label", f"Маршрут №{route_number}")),
        "driver_id": str(assignment.get("driver_id", "")),
        "driver_name": str(assignment.get("driver_name", "")),
        "vehicle_id": str(assignment.get("vehicle_id", "")),
        "vehicle_name": str(assignment.get("vehicle_name", "")),
        "vehicle_plate": str(assignment.get("vehicle_plate", "")),
        "created_at": _now(),
        "revision": 0,
        "operations": [],
        "stores": stores,
    }


def sidecar_path(assignment_id: str) -> Path:
    if not assignment_id or any(character not in "0123456789abcdef" for character in assignment_id):
        raise DriverOrderError("Некорректный идентификатор назначения")
    return paths.DRIVER_ORDERS_FOLDER / f"{assignment_id}.json"


def save_snapshot(snapshot: dict) -> Path:
    assignment_id = str(snapshot.get("assignment_id", ""))
    path = sidecar_path(assignment_id)
    with _LOCK:
        _atomic_write(path, snapshot)
    return path


def publish_assignments(
    output_file: str | Path,
    mode: str,
    source_file: str,
    assignments: list[dict],
) -> list[Path]:
    order_id = _file_digest(Path(output_file))
    paths_written = []
    for assignment in assignments:
        enriched = {**assignment, "order_file": source_file}
        snapshot = build_assignment_snapshot(output_file, mode, enriched, order_id)
        paths_written.append(save_snapshot(snapshot))
    return paths_written


def load_snapshot(path_or_id: str | Path) -> dict:
    path = sidecar_path(str(path_or_id)) if not isinstance(path_or_id, Path) else path_or_id
    with _LOCK:
        return _read(path)


def find_assignment_for_driver(driver_id: str) -> dict | None:
    if not driver_id:
        return None
    folder = paths.DRIVER_ORDERS_FOLDER
    if not folder.exists():
        return None
    candidates = []
    for path in folder.glob("*.json"):
        try:
            snapshot = _read(path)
        except DriverOrderError:
            continue
        if snapshot.get("driver_id") == driver_id:
            candidates.append(snapshot)
    return max(candidates, key=lambda item: item.get("created_at", ""), default=None)


def _find_store(snapshot: dict, store_id: str) -> dict:
    for store in snapshot.get("stores", []):
        if store.get("store_id") == store_id:
            return store
    raise DriverOrderNotFound("Магазин не найден в назначенном заказе")


def _summary(snapshot: dict) -> list[dict]:
    summary: dict[str, dict] = {}
    for store in snapshot.get("stores", []):
        completed = store.get("status") == "completed"
        for line in store.get("lines", []):
            item = summary.setdefault(line["name"], {
                "name": line["name"],
                "unit": line.get("unit", ""),
                "planned": Decimal("0"),
                "necessary": Decimal("0"),
                "completed": Decimal("0"),
            })
            planned = _decimal(line.get("required_qty", "0"))
            item["planned"] += planned
            if completed:
                item["completed"] += _decimal(line.get("actual_qty", "0"))
            else:
                item["necessary"] += planned
    return [
        {
            "name": item["name"],
            "unit": item["unit"],
            "planned": _public_number(item["planned"]),
            "necessary": _public_number(item["necessary"]),
            "completed": _public_number(item["completed"]),
        }
        for item in summary.values()
    ]


def public_snapshot(snapshot: dict) -> dict:
    payload = dict(snapshot)
    payload.pop("operations", None)
    payload["summary"] = _summary(snapshot)
    payload["completed_stores"] = sum(
        store.get("status") == "completed" for store in snapshot.get("stores", [])
    )
    payload["store_count"] = len(snapshot.get("stores", []))
    return payload


def complete_store(
    path_or_id: str | Path,
    store_id: str,
    quantities: dict[str, Any],
    operation_id: str,
    base_revision: int,
    photo: str = "",
) -> dict:
    if not isinstance(operation_id, str) or not operation_id or len(operation_id) > MAX_OPERATION_ID_LENGTH:
        raise DriverOrderError("Некорректный идентификатор операции")
    if not isinstance(quantities, dict):
        raise DriverOrderError("Некорректные количества")
    if not isinstance(base_revision, int) or base_revision < 0:
        raise DriverOrderError("Некорректная ревизия")

    path = sidecar_path(str(path_or_id)) if not isinstance(path_or_id, Path) else path_or_id
    with _LOCK:
        snapshot = _read(path)
        for operation in snapshot.get("operations", []):
            if operation.get("operation_id") == operation_id:
                return public_snapshot(snapshot)
        if snapshot.get("revision") != base_revision:
            raise DriverOrderConflict("Заказ уже изменён на другом устройстве")

        store = _find_store(snapshot, store_id)
        if store.get("status") == "completed":
            raise DriverOrderConflict("Магазин уже подтверждён")
        lines = store.get("lines", [])
        expected_ids = {line.get("line_id") for line in lines}
        if set(quantities) != expected_ids:
            raise DriverOrderError("Укажите фактическое количество по каждой строке")
        for line in lines:
            line["actual_qty"] = _quantity(quantities[line["line_id"]])
        store["status"] = "completed"
        store["completed_at"] = _now()
        store["photo"] = str(photo or "")
        snapshot["revision"] = int(snapshot.get("revision", 0)) + 1
        snapshot.setdefault("operations", []).append({
            "operation_id": operation_id,
            "store_id": store_id,
            "revision": snapshot["revision"],
            "created_at": _now(),
        })
        _atomic_write(path, snapshot)
        return public_snapshot(snapshot)
