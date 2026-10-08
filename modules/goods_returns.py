"""Goods left over from a completed route, separate from order statistics."""

from __future__ import annotations

from copy import deepcopy
from datetime import datetime
from decimal import Decimal, InvalidOperation, localcontext
import hashlib
import json
import os
import tempfile
import threading
import uuid

from modules import order_records, paths


RETURN_REASONS = (
    "Отказ магазина",
    "Брак или несоответствие качеству",
    "Повреждение при перевозке",
    "Излишек загрузки",
    "Другое",
)
_LOCK = threading.RLock()
_MAX_AMOUNT = Decimal("1000000000")
_MAX_COMMENT = 2000


class GoodsReturnError(ValueError):
    """Invalid return or unavailable ledger."""


class GoodsReturnConflict(GoodsReturnError):
    """Stale operation, ownership collision, or changed route facts."""


class GoodsReturnNotFound(GoodsReturnError):
    """The requested return does not exist."""


def _now() -> str:
    return datetime.now().astimezone().isoformat(timespec="seconds")


def _read() -> dict:
    try:
        payload = json.loads(paths.GOODS_RETURNS_FILE.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return {"schema_version": 1, "documents": [], "operations": []}
    except (OSError, UnicodeError, json.JSONDecodeError) as error:
        raise GoodsReturnError("Не удалось прочитать журнал возвратов") from error
    if (not isinstance(payload, dict) or payload.get("schema_version") != 1
            or not isinstance(payload.get("documents"), list)
            or not isinstance(payload.get("operations"), list)
            or any(not isinstance(item, dict) for item in payload["documents"] + payload["operations"])):
        raise GoodsReturnError("Некорректный журнал возвратов")
    return payload


def _write(payload: dict) -> None:
    path = paths.GOODS_RETURNS_FILE
    temporary = None
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        fd, temporary = tempfile.mkstemp(prefix=f".{path.name}.", suffix=".tmp", dir=str(path.parent))
        with os.fdopen(fd, "w", encoding="utf-8") as stream:
            json.dump(payload, stream, ensure_ascii=False, indent=2, allow_nan=False)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
        temporary = None
    except OSError as error:
        raise GoodsReturnError("Не удалось сохранить журнал возвратов") from error
    finally:
        if temporary:
            try:
                os.unlink(temporary)
            except OSError:
                pass


def _hash(value: object) -> str:
    try:
        encoded = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False)
    except (TypeError, ValueError) as error:
        raise GoodsReturnError("Некорректные данные возврата") from error
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


def _number(value: object, field: str) -> Decimal:
    if isinstance(value, bool) or value is None or len(str(value)) > 64:
        raise GoodsReturnError(f"Некорректное значение: {field}")
    try:
        number = Decimal(str(value).strip().replace(",", "."))
    except InvalidOperation as error:
        raise GoodsReturnError(f"Некорректное значение: {field}") from error
    if (not number.is_finite() or number < 0 or number > _MAX_AMOUNT
            or len(number.as_tuple().digits) > 18 or abs(number.as_tuple().exponent) > 9):
        raise GoodsReturnError(f"Недопустимое значение: {field}")
    return number


def _render(value: Decimal) -> str:
    rendered = format(value, "f")
    return rendered.rstrip("0").rstrip(".") if "." in rendered else rendered


def _revision(value: object) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise GoodsReturnError("Некорректная ревизия возврата")
    return value


def _actor(actor: object, kind: str, identity: str) -> dict:
    if not isinstance(actor, dict) or actor.get("kind") != kind or actor.get("id") != identity or not identity:
        raise GoodsReturnError("Нет доступа к этому действию с возвратом")
    return {"kind": kind, "id": identity, "name": str(actor.get("name", ""))[:200]}


def _comment(value: object) -> str:
    if not isinstance(value, str) or len(value) > _MAX_COMMENT:
        raise GoodsReturnError("Комментарий должен быть текстом не длиннее 2000 символов")
    return value.strip()


def _route_document(ledger: dict, assignment: dict) -> dict | None:
    return next((doc for doc in ledger["documents"]
                 if doc.get("order_record_id") == assignment.get("order_record_id")
                 and doc.get("route_key") == assignment.get("route_key")), None)


def _owns(document: dict, assignment: dict) -> bool:
    return (document.get("assignment_id") == assignment.get("assignment_id")
            and document.get("driver_id") == assignment.get("driver_id"))


def _snapshot_complete(assignment: dict, balance: dict) -> bool:
    """Require exact ID coverage and both sides of the split shipment save."""
    stores = assignment.get("stores")
    if not isinstance(stores, list) or not stores:
        raise GoodsReturnConflict("Нет надёжной связи магазинов назначения с заказом")
    expected = {item["id"]: item for item in balance["destinations"]}
    seen = set()
    complete = True
    for store in stores:
        if not isinstance(store, dict):
            raise GoodsReturnConflict("Некорректные магазины назначения")
        destination_id = store.get("order_record_destination_id")
        if not isinstance(destination_id, str) or destination_id not in expected or destination_id in seen:
            raise GoodsReturnConflict("Нет надёжной связи магазинов назначения с заказом")
        seen.add(destination_id)
        positions = {item["id"]: item for item in expected[destination_id]["positions"]}
        actual_lines = store.get("lines")
        if not isinstance(actual_lines, list) or len(actual_lines) != len(positions):
            raise GoodsReturnConflict("Состав отгрузки не совпадает с заказом")
        position_ids = set()
        store_complete = store.get("status") == "completed"
        complete = complete and store_complete
        for line in actual_lines:
            if not isinstance(line, dict):
                raise GoodsReturnConflict("Некорректные позиции назначения")
            position_id = line.get("order_record_position_id")
            position = positions.get(position_id) if isinstance(position_id, str) else None
            if (position is None or position_id in position_ids
                    or line.get("loading_line_id") != position["loading_line_id"]):
                raise GoodsReturnConflict("Нет надёжной связи позиций отгрузки с загрузкой")
            position_ids.add(position_id)
            if store_complete != position["completed"]:
                raise GoodsReturnConflict("Дождитесь синхронизации отгрузок маршрута")
            if store_complete and _number(line.get("actual_qty"), "Отгружено") != Decimal(position["net_weight_kg"]):
                raise GoodsReturnConflict("Дождитесь синхронизации веса отгрузок маршрута")
    if seen != set(expected):
        raise GoodsReturnConflict("Состав магазинов не совпадает с заказом")
    return complete and balance["complete"]


def _context(assignment: dict, ledger: dict) -> dict:
    context = {
        "assignment_id": str(assignment.get("assignment_id", "")),
        "order_record_id": str(assignment.get("order_record_id", "")),
        "route_key": str(assignment.get("route_key", "")),
        "route_label": str(assignment.get("route_label", "")),
        "eligible": False, "complete": False, "loading_ready": False,
        "error": "", "facts_token": "", "reasons": list(RETURN_REASONS), "lines": [], "document": None,
    }
    document = _route_document(ledger, assignment)
    other_owner = document is not None and not _owns(document, assignment)
    if document and not other_owner:
        context["document"] = deepcopy(document)
    if not all(context[key] for key in ("assignment_id", "order_record_id", "route_key")) or not assignment.get("driver_id"):
        context["error"] = "У назначения нет надёжной связи с записью заказа"
        return context
    try:
        record = order_records.load_order_record(context["order_record_id"])
        balance = order_records.route_return_balance(record, context["route_key"])
    except (order_records.OrderRecordError, OSError, ValueError, TypeError, KeyError):
        context["error"] = "Нет подтверждённой загрузки с надёжной связью с маршрутом"
        return context
    context["route_label"] = balance["route_label"]
    context["lines"] = balance["lines"]
    context["loading_ready"] = True
    context["facts_token"] = _hash({"order_record_id": context["order_record_id"], **balance})
    try:
        context["complete"] = _snapshot_complete(assignment, balance)
    except GoodsReturnError as error:
        context["error"] = str(error)
        return context
    if other_owner:
        context["error"] = "Возврат маршрута закреплён за другим назначением"
    elif not context["complete"]:
        context["error"] = "Сначала завершите и синхронизируйте все магазины маршрута"
    elif document and document["status"] != "rejected":
        context["error"] = "Возврат уже отправлен на проверку" if document["status"] == "submitted" else "Возврат уже принят"
    else:
        context["eligible"] = True
    return context


def return_context(assignment: dict) -> dict:
    """Allowlisted form facts, with loading cacheable before route completion."""
    if not isinstance(assignment, dict):
        raise GoodsReturnError("Некорректное назначение")
    with _LOCK:
        return _context(assignment, _read())


def _validated_lines(values: object, context: dict) -> tuple[list[dict], str]:
    if not isinstance(values, dict) or not values:
        raise GoodsReturnError("Выберите хотя бы одну позицию возврата")
    available = {line["loading_line_id"]: line for line in context["lines"]}
    if not set(values).issubset(available):
        raise GoodsReturnError("Позиция не относится к загрузке этого маршрута")
    result = []
    with localcontext() as arithmetic:
        arithmetic.prec = 60
        total = Decimal("0")
        for line_id in sorted(values):
            value = values[line_id]
            if not isinstance(value, dict):
                raise GoodsReturnError("Некорректные данные позиции возврата")
            if set(value) - {"box_count", "tare_weight_per_box_kg", "gross_weight_kg", "reason", "comment"}:
                raise GoodsReturnError("Неизвестные поля позиции возврата")
            boxes = _number(value.get("box_count"), "Количество ящиков")
            if boxes != boxes.to_integral_value():
                raise GoodsReturnError("Количество ящиков должно быть целым")
            tare = _number(value.get("tare_weight_per_box_kg"), "Вес тары")
            gross = _number(value.get("gross_weight_kg"), "Грязный вес")
            net = order_records.calculate_net_weight(gross, tare, boxes)
            if net <= 0:
                raise GoodsReturnError("Нетто возврата должно быть положительным и больше веса тары")
            source = available[line_id]
            if net > Decimal(source["available_net_kg"]):
                raise GoodsReturnError(f"Возврат превышает остаток загрузки товара «{source['name']}»")
            reason = value.get("reason")
            if reason not in RETURN_REASONS:
                raise GoodsReturnError("Укажите причину возврата")
            comment = _comment(value.get("comment", ""))
            if reason == "Другое" and not comment:
                raise GoodsReturnError("Для причины «Другое» укажите комментарий")
            result.append({
                "loading_line_id": line_id, "name": source["name"],
                "loaded_net_kg": source["loaded_net_kg"], "shipped_net_kg": source["shipped_net_kg"],
                "measurement": {"box_count": str(int(boxes)), "tare_weight_per_box_kg": _render(tare),
                                "gross_weight_kg": _render(gross), "net_weight_kg": _render(net)},
                "reason": reason, "comment": comment,
            })
            total += net
    return result, _render(total)


def submit_return(assignment: dict, payload: dict, actor: dict) -> dict:
    """Submit/resubmit, replaying immutable operation results before revisions."""
    if not isinstance(assignment, dict) or not isinstance(payload, dict):
        raise GoodsReturnError("Некорректные данные возврата")
    actor = _actor(actor, "driver", str(assignment.get("driver_id", "")))
    if not all(isinstance(assignment.get(key), str) and assignment[key]
               for key in ("assignment_id", "order_record_id", "route_key")):
        raise GoodsReturnError("У назначения нет надёжной связи с заказом")
    operation_id = payload.get("operation_id")
    if not isinstance(operation_id, str) or not operation_id.strip() or len(operation_id) > 128:
        raise GoodsReturnError("Некорректный идентификатор операции")
    payload_hash = _hash(payload)
    with _LOCK, order_records._LOCK:
        ledger = _read()
        document = _route_document(ledger, assignment)
        if document is not None and not _owns(document, assignment):
            raise GoodsReturnConflict("Возврат маршрута закреплён за другим назначением")
        for operation in ledger["operations"]:
            if operation.get("operation_id") != operation_id:
                continue
            if (not _owns(operation, assignment)
                    or operation.get("order_record_id") != assignment["order_record_id"]
                    or operation.get("route_key") != assignment["route_key"]):
                raise GoodsReturnConflict("Идентификатор операции уже использован")
            if operation.get("payload_hash") != payload_hash:
                raise GoodsReturnConflict("Операция уже отправлена с другими данными")
            return deepcopy(operation["result"])
        if set(payload) != {"operation_id", "base_revision", "facts_token", "lines"}:
            raise GoodsReturnError("Некорректные поля возврата")
        base_revision = _revision(payload.get("base_revision"))
        if base_revision != (document["revision"] if document else 0):
            raise GoodsReturnConflict("Возврат уже изменён; обновите данные")
        if document and document["status"] != "rejected":
            raise GoodsReturnConflict("Можно исправить только отклонённый возврат")
        context = _context(assignment, ledger)
        if not context["eligible"]:
            raise GoodsReturnConflict(context["error"])
        if not isinstance(payload.get("facts_token"), str) or payload["facts_token"] != context["facts_token"]:
            raise GoodsReturnConflict("Данные загрузки или отгрузки изменились; проверьте возврат")
        lines, total = _validated_lines(payload.get("lines"), context)
        now = _now()
        if document is None:
            record = order_records.load_order_record(assignment["order_record_id"])
            document = {
                "id": uuid.uuid4().hex, "revision": 0, "version": 0,
                "assignment_id": assignment["assignment_id"], "order_record_id": assignment["order_record_id"],
                "route_key": assignment["route_key"], "route_label": context["route_label"],
                "driver_id": assignment["driver_id"], "driver_name": str(assignment.get("driver_name", "")),
                "vehicle_plate": str(assignment.get("vehicle_plate", "")),
                "order_number": str(record.get("order_number", "")), "history": [],
            }
            ledger["documents"].append(document)
        document.update(revision=document["revision"] + 1, version=document["version"] + 1,
                        status="submitted", submitted_at=now, total_net_kg=total, lines=lines)
        document["history"].append({
            "kind": "submitted", "at": now, "actor": actor, "comment": "", "operation_id": operation_id,
            "revision": document["revision"], "version": document["version"],
            "facts_token": context["facts_token"], "total_net_kg": total, "lines": deepcopy(lines),
        })
        result = deepcopy(document)
        ledger["operations"].append({
            "operation_id": operation_id, "payload_hash": payload_hash,
            "assignment_id": document["assignment_id"], "driver_id": document["driver_id"],
            "order_record_id": document["order_record_id"], "route_key": document["route_key"], "result": result,
        })
        _write(ledger)
        return deepcopy(result)


def decide_return(doc_id: str, revision: int, decision: str, comment: str, actor: dict) -> dict:
    """An administrator decides exactly one submitted revision atomically."""
    actor = _actor(actor, "dashboard", "admin")
    revision = _revision(revision)
    if not isinstance(decision, str) or decision not in {"accepted", "rejected"}:
        raise GoodsReturnError("Некорректное решение по возврату")
    comment = _comment(comment)
    if decision == "rejected" and not comment:
        raise GoodsReturnError("Укажите причину отклонения")
    with _LOCK:
        ledger = _read()
        document = next((doc for doc in ledger["documents"] if doc.get("id") == doc_id), None)
        if document is None:
            raise GoodsReturnNotFound("Возврат не найден")
        if document["revision"] != revision or document["status"] != "submitted":
            raise GoodsReturnConflict("Возврат уже изменён; решение не сохранено")
        document["revision"] += 1
        document["status"] = decision
        document["history"].append({
            "kind": decision, "at": _now(), "actor": actor, "comment": comment,
            "revision": document["revision"], "version": document["version"],
        })
        _write(ledger)
        return deepcopy(document)


def list_returns() -> list[dict]:
    with _LOCK:
        return deepcopy(sorted(_read()["documents"], key=lambda doc: (doc["submitted_at"], doc["id"]), reverse=True))


def accepted_by_loading_line(order_record_id: str) -> dict[str, str]:
    with _LOCK, localcontext() as arithmetic:
        arithmetic.prec = 60
        totals = {}
        for document in _read()["documents"]:
            if document.get("order_record_id") != order_record_id or document.get("status") != "accepted":
                continue
            for line in document["lines"]:
                line_id = line["loading_line_id"]
                totals[line_id] = totals.get(line_id, Decimal("0")) + Decimal(line["measurement"]["net_weight_kg"])
        return {line_id: _render(total) for line_id, total in totals.items()}
