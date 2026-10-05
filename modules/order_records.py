"""Durable order snapshots used by the warehouse loading workspace."""

from __future__ import annotations

from copy import deepcopy
from datetime import datetime
from decimal import Decimal, InvalidOperation
import json
import os
from pathlib import Path
import tempfile
import threading
import uuid

from openpyxl import load_workbook

from modules import paths
from modules.route_drivers import ROUTE_AREAS


SCHEMA_VERSION = 1
MAX_AMOUNT_DIGITS = 18
_LOCK = threading.RLock()


class OrderRecordError(ValueError):
    """Order record data is invalid or unavailable."""


class OrderRecordNotFound(OrderRecordError):
    """The requested order record does not exist."""


class OrderRecordConflict(OrderRecordError):
    """The loading form was saved from an obsolete revision."""


def _now() -> str:
    return datetime.now().astimezone().isoformat(timespec="seconds")


def _decimal(value, field: str) -> Decimal:
    if isinstance(value, bool) or value is None:
        raise OrderRecordError(f"Некорректное значение: {field}")
    try:
        number = Decimal(str(value).strip().replace(",", "."))
    except (AttributeError, InvalidOperation) as error:
        raise OrderRecordError(f"Некорректное значение: {field}") from error
    if not number.is_finite() or number < 0:
        raise OrderRecordError(f"{field} не может быть отрицательным")
    if len(number.as_tuple().digits) > MAX_AMOUNT_DIGITS:
        raise OrderRecordError(f"Слишком большое значение: {field}")
    return number


def _quantity(value, field: str) -> str:
    number = _decimal(value, field)
    rendered = format(number, "f")
    return rendered.rstrip("0").rstrip(".") if "." in rendered else rendered


def _integer_quantity(value, field: str) -> str:
    number = _decimal(value, field)
    if number != number.to_integral_value():
        raise OrderRecordError(f"{field} должен быть целым числом")
    return str(int(number))


def calculate_net_weight(gross_weight, tare_weight, box_count) -> Decimal:
    """Return gross weight minus tare weight for every loaded box."""

    return _decimal(gross_weight, "Вес брутто") - (
        _decimal(tare_weight, "Вес тары") * _decimal(box_count, "Количество ящиков")
    )


def _atomic_write(payload: dict) -> None:
    path = paths.ORDER_RECORDS_FILE
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
        raise OrderRecordError("Не удалось сохранить реестр заказов") from error
    finally:
        if temporary:
            try:
                os.unlink(temporary)
            except OSError:
                pass


def _empty_payload() -> dict:
    return {"schema_version": SCHEMA_VERSION, "records": []}


def _normalize_legacy_record(record: dict) -> None:
    for route in record.get("routes", []):
        for destination in route.get("destinations", []):
            for position in destination.get("positions", []):
                if position.get("unit") in {"", "box"}:
                    position["unit"] = "kg"
    for line in record.get("loading_lines", []):
        if line.get("unit") in {"", "box"}:
            line["unit"] = "kg"
        if "loaded_box_count" not in line:
            legacy_amount = line.pop("loading_amount", "")
            try:
                line["loaded_box_count"] = _integer_quantity(
                    legacy_amount, "Загружено"
                ) if legacy_amount != "" else ""
            except OrderRecordError:
                line["loaded_box_count"] = ""


def _read_payload() -> dict:
    path = paths.ORDER_RECORDS_FILE
    if not path.exists():
        return _empty_payload()
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as error:
        raise OrderRecordError("Реестр заказов повреждён или недоступен") from error
    if (
        not isinstance(payload, dict)
        or payload.get("schema_version") != SCHEMA_VERSION
        or not isinstance(payload.get("records"), list)
    ):
        raise OrderRecordError("Неподдерживаемая версия реестра заказов")
    for record in payload["records"]:
        if not isinstance(record, dict):
            raise OrderRecordError("Реестр заказов повреждён")
        _normalize_legacy_record(record)
    return payload


def _validated_relative_output_path(output_file: str | Path) -> str:
    root = Path(paths.PROCESSED_FOLDER).resolve(strict=False)
    output = Path(output_file).resolve(strict=False)
    try:
        relative = output.relative_to(root)
    except ValueError as error:
        raise OrderRecordError("Результат заказа находится вне каталога обработки") from error
    if len(relative.parts) != 2 or output.suffix.casefold() != ".xlsx" or not output.is_file():
        raise OrderRecordError("Результат заказа недоступен")
    return relative.as_posix()


def _route_sheet_number(title: str) -> int | None:
    prefix = "Маршрут №"
    if not title.startswith(prefix):
        return None
    try:
        number = int(title.removeprefix(prefix))
    except ValueError:
        return None
    return number if 1 <= number <= 99 else None


def _store_columns(sheet) -> list[tuple[int, str]]:
    columns = []
    for column in range(3, sheet.max_column + 1):
        name = str(sheet.cell(1, column).value or "").strip()
        if name and name.casefold() != "сумма":
            columns.append((column, name))
    return columns


def _route_snapshot(sheet, route_number: int, aggregate: dict[tuple[str, str], dict]) -> dict:
    stores = _store_columns(sheet)
    destinations = [
        {"id": uuid.uuid4().hex, "name": name, "positions": []}
        for _, name in stores
    ]
    destination_by_column = {
        column: destination for (column, _), destination in zip(stores, destinations)
    }

    for row in range(2, sheet.max_row + 1):
        name = str(sheet.cell(row, 1).value or "").strip()
        if not name or name.casefold() == "итого":
            continue
        for column, _ in stores:
            value = sheet.cell(row, column).value
            if value in (None, ""):
                continue
            planned_amount = _quantity(value, "Заказано")
            position = {
                "id": uuid.uuid4().hex,
                "name": name,
                "unit": "kg",
                "planned_amount": planned_amount,
            }
            destination_by_column[column]["positions"].append(position)
            key = (name.casefold(), "kg")
            line = aggregate.setdefault(
                key,
                {
                    "id": uuid.uuid4().hex,
                    "name": name,
                    "unit": "kg",
                    "planned_amount": Decimal("0"),
                },
            )
            line["planned_amount"] += _decimal(planned_amount, "Заказано")

    return {
        "route_key": f"route_{route_number}",
        "route_label": f"Маршрут №{route_number}",
        "area": ROUTE_AREAS[route_number - 1] if route_number <= len(ROUTE_AREAS) else "",
        "destinations": [destination for destination in destinations if destination["positions"]],
    }
def _workbook_snapshot(output_file: Path) -> tuple[list[dict], list[dict]]:
    try:
        workbook = load_workbook(output_file, data_only=True, read_only=True)
    except (OSError, ValueError) as error:
        raise OrderRecordError("Не удалось прочитать обработанный заказ") from error

    aggregate: dict[tuple[str, str], dict] = {}
    routes = []
    try:
        sheets = sorted(
            (
                (number, sheet)
                for sheet in workbook.worksheets
                if (number := _route_sheet_number(sheet.title)) is not None
            ),
            key=lambda item: item[0],
        )
        for number, sheet in sheets:
            route = _route_snapshot(sheet, number, aggregate)
            if route["destinations"]:
                routes.append(route)
    finally:
        workbook.close()

    lines = []
    for line in aggregate.values():
        lines.append(
            {
                "id": line["id"],
                "name": line["name"],
                "unit": line["unit"],
                "planned_amount": _quantity(line["planned_amount"], "Заказано"),
                "loaded_box_count": "",
                "tare_weight": "",
                "gross_weight": "",
                "net_weight": "",
            }
        )
    lines.sort(key=lambda item: (item["name"].casefold(), item["unit"]))
    if not routes or not lines:
        raise OrderRecordError("В обработанном заказе не найдены позиции маршрутов")
    return routes, lines


def _mail_metadata(metadata: dict | None) -> dict | None:
    if metadata is None:
        return None
    return {
        key: str(metadata.get(key, ""))
        for key in (
            "message_id",
            "sender",
            "subject",
            "received_at",
            "received_display",
            "source_name",
            "source_email",
            "source_person",
        )
    }


def create_processed_order_record(
    output_file: str | Path,
    source_filename: str,
    client_name: str,
    mode: str,
    mail_metadata: dict | None = None,
) -> dict:
    source_filename = Path(str(source_filename)).name
    client_name = str(client_name).strip()
    if not source_filename or not client_name:
        raise OrderRecordError("Укажите номер заказа и клиента")
    if mode not in {"Город", "Область"}:
        raise OrderRecordError("Не указан режим заказа")

    relative_output_path = _validated_relative_output_path(output_file)
    routes, loading_lines = _workbook_snapshot(Path(output_file))
    record = {
        "id": uuid.uuid4().hex,
        "schema_version": SCHEMA_VERSION,
        "revision": 0,
        "source_filename": source_filename,
        "order_number": Path(source_filename).stem,
        "client_name": client_name,
        "mail_metadata": _mail_metadata(mail_metadata),
        "processed_at": _now(),
        "output_relative_path": relative_output_path,
        "mode": mode,
        "loading": {
            "status": "new",
            "last_saved_at": "",
            "last_saved_by": {"kind": "", "id": "", "name": ""},
        },
        "routes": routes,
        "loading_lines": loading_lines,
    }
    with _LOCK:
        payload = _read_payload()
        payload["records"].append(record)
        _atomic_write(payload)
    return deepcopy(record)


def list_order_record_summaries() -> list[dict]:
    with _LOCK:
        records = _read_payload()["records"]
    summaries = [
        {
            "id": str(record.get("id", "")),
            "order_number": str(record.get("order_number", "")),
            "client_name": str(record.get("client_name", "")),
            "processed_at": str(record.get("processed_at", "")),
            "status": str((record.get("loading") or {}).get("status", "new")),
        }
        for record in records
    ]
    return sorted(summaries, key=lambda item: item["processed_at"], reverse=True)


def latest_record_ids_by_source_filename() -> dict[str, str]:
    with _LOCK:
        records = _read_payload()["records"]
    latest = {}
    for record in sorted(records, key=lambda item: str(item.get("processed_at", ""))):
        filename = str(record.get("source_filename", ""))
        record_id = str(record.get("id", ""))
        if filename and record_id:
            latest[filename] = record_id
    return latest


def load_order_record(order_record_id: str) -> dict:
    with _LOCK:
        for record in _read_payload()["records"]:
            if record.get("id") == order_record_id:
                return deepcopy(record)
    raise OrderRecordNotFound("Заказ не найден")


def save_loading_update(
    order_record_id: str,
    revision: int,
    box_counts: dict[str, object],
    actor: dict,
) -> dict:
    if not isinstance(revision, int) or isinstance(revision, bool) or revision < 0:
        raise OrderRecordError("Некорректная версия заказа")
    if not isinstance(box_counts, dict):
        raise OrderRecordError("Некорректные данные загрузки")

    with _LOCK:
        payload = _read_payload()
        record = next(
            (item for item in payload["records"] if item.get("id") == order_record_id),
            None,
        )
        if record is None:
            raise OrderRecordNotFound("Заказ не найден")
        if record.get("revision") != revision:
            raise OrderRecordConflict("Данные загрузки уже изменены другим пользователем")

        lines = record.get("loading_lines")
        if not isinstance(lines, list):
            raise OrderRecordError("В заказе отсутствуют позиции загрузки")
        line_ids = {str(line.get("id", "")) for line in lines}
        if not line_ids or set(box_counts) != line_ids:
            raise OrderRecordError("Заполните загрузку для каждой позиции")

        for line in lines:
            line["loaded_box_count"] = _integer_quantity(
                box_counts[str(line["id"])], "Загружено"
            )

        record["revision"] += 1
        record["loading"] = {
            "status": "loaded",
            "last_saved_at": _now(),
            "last_saved_by": {
                "kind": str(actor.get("kind", "")),
                "id": str(actor.get("id", "")),
                "name": str(actor.get("name", "")),
            },
        }
        _atomic_write(payload)
        return deepcopy(record)
