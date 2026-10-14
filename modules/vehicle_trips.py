"""Physical vehicle trips: one transactional stock ledger across route assignments."""
from __future__ import annotations

from contextlib import contextmanager
from copy import deepcopy
from datetime import datetime, date
from decimal import Decimal, InvalidOperation, localcontext
import hashlib
import json
from pathlib import Path
import sqlite3
import uuid

from modules import paths, order_records, driver_orders

REFUSAL_REASONS = ("Отказ магазина", "Качество товара", "Избыток товара", "Другое")


class TripError(ValueError):
    pass


class TripConflict(TripError):
    pass


class TripNotFound(TripError):
    pass


def _now():
    return datetime.now().astimezone().isoformat()


def _json(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _hash(value):
    return hashlib.sha256(_json(value).encode()).hexdigest()


def _number(value):
    text = str(value).strip().replace(",", ".")
    if not text or len(text) > 64:
        raise TripError("Укажите корректный вес")
    try:
        number = Decimal(text)
    except InvalidOperation as error:
        raise TripError("Некорректный вес") from error
    if not number.is_finite() or number < 0 or number > Decimal("1000000000") or abs(number.as_tuple().exponent) > 9:
        raise TripError("Вес должен быть неотрицательным числом в допустимых пределах")
    return number


def _text(value):
    return order_records._format_number(value)


def _actor(actor, kinds):
    if not isinstance(actor, dict) or actor.get("kind") not in kinds or not actor.get("id"):
        raise TripError("Недостаточно прав для операции с рейсом")
    principal = {key: str(actor.get(key, "")) for key in ("kind", "id", "name")}
    if principal["kind"] == "loader":
        principal["vehicle_id"] = str(actor.get("vehicle_id", ""))
    return principal


@contextmanager
def _db(write=False):
    path = paths.VEHICLE_TRIPS_FILE
    path.parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(path, timeout=30)
    connection.row_factory = sqlite3.Row
    try:
        connection.executescript("""
            CREATE TABLE IF NOT EXISTS trips(id TEXT PRIMARY KEY, driver TEXT NOT NULL, vehicle TEXT NOT NULL,
                status TEXT NOT NULL, payload TEXT NOT NULL);
            CREATE TABLE IF NOT EXISTS members(assignment TEXT PRIMARY KEY, trip TEXT NOT NULL);
            CREATE TABLE IF NOT EXISTS operations(id TEXT PRIMARY KEY, trip TEXT NOT NULL, fingerprint TEXT NOT NULL);
            CREATE TABLE IF NOT EXISTS outbox(id TEXT PRIMARY KEY, trip TEXT NOT NULL, payload TEXT NOT NULL, done INTEGER NOT NULL DEFAULT 0);
        """)
        for name, field in (("active_driver", "driver"), ("active_vehicle", "vehicle")):
            index = connection.execute("SELECT sql FROM sqlite_master WHERE type='index' AND name=?", (name,)).fetchone()
            predicate = "status IN ('draft','active','on_base','return_pending')"
            if index and predicate not in index["sql"]:
                connection.execute(f"DROP INDEX {name}")
            connection.execute(f"CREATE UNIQUE INDEX IF NOT EXISTS {name} ON trips({field}) WHERE {predicate}")
        if write:
            connection.execute("BEGIN IMMEDIATE")
        with localcontext() as arithmetic:
            arithmetic.prec = 60
            yield connection
        connection.commit()
    except sqlite3.IntegrityError as error:
        connection.rollback()
        raise TripConflict("Машина, водитель или назначение уже участвуют в рейсе") from error
    except BaseException:
        connection.rollback()
        raise
    finally:
        connection.close()


def _load(connection, trip_id):
    row = connection.execute("SELECT payload FROM trips WHERE id=?", (trip_id,)).fetchone()
    if row is None:
        raise TripNotFound("Рейс машины не найден")
    return json.loads(row["payload"])


def _save(connection, trip):
    connection.execute("UPDATE trips SET status=?,payload=? WHERE id=?", (trip["status"], _json(trip), trip["id"]))


def load_trip(trip_id):
    if not paths.VEHICLE_TRIPS_FILE.exists():
        raise TripNotFound("Рейс машины не найден")
    with _db() as connection:
        return _load(connection, trip_id)


def list_trips(driver_id=""):
    if not paths.VEHICLE_TRIPS_FILE.exists():
        return []
    with _db() as connection:
        rows = connection.execute("SELECT payload FROM trips" + (" WHERE driver=?" if driver_id else ""), (driver_id,) if driver_id else ()).fetchall()
        return sorted((json.loads(row[0]) for row in rows), key=lambda item: item["created_at"], reverse=True)


def trip_for_assignment(assignment_id):
    if not paths.VEHICLE_TRIPS_FILE.exists():
        return None
    with _db() as connection:
        row = connection.execute("SELECT trip FROM members WHERE assignment=?", (assignment_id,)).fetchone()
        return _load(connection, row[0]) if row else None


def active_for_driver(driver_id):
    return next((item for item in list_trips(driver_id) if item["status"] in {"draft", "active", "on_base", "return_pending"}), None)


def active_for_vehicle(vehicle_id):
    return next((item for item in list_trips() if item["vehicle_id"] == vehicle_id and item["status"] in {"draft", "active", "on_base", "return_pending"}), None)


def _fleet_available(snapshot):
    from modules.fleet import driver_by_id, active_vehicles
    driver = driver_by_id(str(snapshot.get("driver_id", "")))
    return bool(driver and driver.get("active") and snapshot.get("vehicle_id") in {item["id"] for item in active_vehicles()})


def assignment_choices():
    return [snapshot for snapshot in driver_orders._snapshots(active_only=True) if snapshot.get("driver_id") and snapshot.get("vehicle_id") and snapshot.get("order_record_id") and _fleet_available(snapshot) and not trip_for_assignment(snapshot["assignment_id"])]


def preview_members(trip):
    result = []
    for member in trip["members"]:
        row = {**member, "loaded": "—", "shipped": "—", "error": ""}
        try:
            record = order_records.load_order_record(member["order_record_id"])
            balance = order_records.route_return_balance(record, member["route_key"], member.get("loading_batch_id", ""))
            row["loaded"] = _text(sum((_number(line["loaded_net_kg"]) for line in balance["lines"]), Decimal(0)))
            row["shipped"] = _text(sum((_number(line["shipped_net_kg"]) for line in balance["lines"]), Decimal(0)))
        except (ValueError, OSError) as error:
            row["error"] = str(error)
        result.append(row)
    return result


def _member(snapshot):
    member = {key: str(snapshot.get(key, "")) for key in ("assignment_id", "order_record_id", "route_key", "route_label", "driver_id", "vehicle_id")}
    if snapshot.get("loading_batch_id"):
        member["loading_batch_id"] = str(snapshot["loading_batch_id"])
    return member


def create_trip(assignment_ids, day, actor, operation_id):
    actor = _actor(actor, {"dashboard"})
    try:
        date.fromisoformat(day)
    except (ValueError, TypeError) as error:
        raise TripError("Укажите дату рейса") from error
    if not isinstance(assignment_ids, list) or not assignment_ids or any(not isinstance(identity, str) or not identity for identity in assignment_ids) or len(set(assignment_ids)) != len(assignment_ids):
        raise TripError("Выберите уникальные назначения")
    request = {"assignments": assignment_ids, "day": day, "actor": actor["id"]}
    _operation_id(operation_id)
    with _db(True) as connection:
        known = connection.execute("SELECT trip,fingerprint FROM operations WHERE id=?", (operation_id,)).fetchone()
        if known:
            if known["fingerprint"] != _hash(request):
                raise TripConflict("Идентификатор операции использован с другими данными")
            return _load(connection, known["trip"])
        choices = {item["assignment_id"]: item for item in assignment_choices()}
        if any(identity not in choices for identity in assignment_ids):
            raise TripConflict("Назначение уже включено в рейс или неактуально")
        snapshots = [choices[identity] for identity in assignment_ids]
        first = snapshots[0]
        if any(item["driver_id"] != first["driver_id"] or item["vehicle_id"] != first["vehicle_id"] for item in snapshots):
            raise TripError("Все маршруты рейса должны иметь одну машину и одного водителя")
        trip = {"id": uuid.uuid4().hex, "date": day, "status": "draft", "revision": 0, "created_at": _now(),
                "driver_id": first["driver_id"], "driver_name": first.get("driver_name", ""),
                "vehicle_id": first["vehicle_id"], "vehicle_name": first.get("vehicle_name", ""), "vehicle_plate": first.get("vehicle_plate", ""),
                "members": [_member(item) for item in snapshots], "products": [], "stops": [], "topups": [], "returns": [], "unloads": [],
                "history": [{"kind": "created", "at": _now(), "actor": actor}], "projection_error": ""}
        connection.execute("INSERT INTO trips VALUES(?,?,?,?,?)", (trip["id"], trip["driver_id"], trip["vehicle_id"], trip["status"], _json(trip)))
        for member in trip["members"]:
            connection.execute("INSERT INTO members VALUES(?,?)", (member["assignment_id"], trip["id"]))
        connection.execute("INSERT INTO operations VALUES(?,?,?)", (operation_id, trip["id"], _hash(request)))
        return trip


def backlog_choices(trip):
    delivered, planned = {}, {}
    for stop in trip["stops"]:
        if stop["kind"] not in {"planned", "followup"}:
            continue
        for line in stop["lines"]:
            key = (stop.get("order_record_id"), stop.get("destination_id"), line.get("position_id") or line["id"])
            delivered[key] = delivered.get(key, Decimal(0)) + Decimal(line["accepted"])
            planned[key] = max(planned.get(key, Decimal(0)), Decimal(line["planned"]))
    choices, seen = [], set()
    for stop in trip["stops"]:
        if stop["kind"] not in {"planned", "followup"} or stop["status"] not in {"deferred", "completed"} or stop.get("continued_to_trip"):
            continue
        remaining = []
        for line in stop["lines"]:
            key = (stop.get("order_record_id"), stop.get("destination_id"), line.get("position_id") or line["id"])
            if key in seen:
                continue
            seen.add(key)
            needed = planned[key] - delivered[key]
            if needed > 0:
                remaining.append({**line, "needed_kg": _text(needed)})
        if remaining:
            choices.append({"stop_id": stop["id"], "name": stop["name"], "route_label": stop["route_label"],
                            "not_visited": stop["status"] == "deferred", "lines": remaining})
    return choices


def create_continuation(previous_id, stop_ids, day, actor, operation_id):
    actor = _actor(actor, {"dashboard"})
    try:
        date.fromisoformat(day)
    except (TypeError, ValueError) as error:
        raise TripError("Укажите дату следующего рейса") from error
    if not isinstance(stop_ids, list) or not stop_ids or len(set(stop_ids)) != len(stop_ids):
        raise TripError("Выберите недоставленные магазины")
    _operation_id(operation_id)
    request = {"previous": previous_id, "stops": stop_ids, "day": day, "actor": actor["id"]}
    with _db(True) as connection:
        known = connection.execute("SELECT trip,fingerprint FROM operations WHERE id=?", (operation_id,)).fetchone()
        if known:
            if known["fingerprint"] != _hash(request):
                raise TripConflict("Идентификатор операции использован с другими данными")
            return _load(connection, known["trip"])
        previous = _load(connection, previous_id)
        if previous["status"] not in {"released_pending", "closed"} or previous.get("projection_error"):
            raise TripConflict("Довоз создаётся после полной выгрузки и синхронизации отгрузок")
        choices = {item["stop_id"]: item for item in backlog_choices(previous)}
        if any(identity not in choices for identity in stop_ids):
            raise TripConflict("Список недоставленных магазинов изменился")
        trip = {"id": uuid.uuid4().hex, "date": day, "status": "on_base", "revision": 0, "created_at": _now(),
                "driver_id": previous["driver_id"], "driver_name": previous["driver_name"], "vehicle_id": previous["vehicle_id"],
                "vehicle_name": previous["vehicle_name"], "vehicle_plate": previous["vehicle_plate"],
                "parent_trip_id": previous_id, "route_label": "Довоз · " + (previous.get("route_label") or " + ".join(item["route_label"] for item in previous["members"])),
                "members": [], "products": [], "stops": [], "topups": [], "returns": [], "unloads": [],
                "history": [{"kind": "created_for_delivery", "at": _now(), "actor": actor, "details": {"previous": previous_id, "stops": stop_ids}}],
                "projection_error": "", "source_snapshots": {}}
        for identity in stop_ids:
            source = _stop(previous, identity)
            new_stop = {key: source.get(key, "") for key in ("assignment_id", "source_store_id", "order_record_id", "route_key", "destination_id", "name", "route_label")}
            new_stop.update(id=uuid.uuid4().hex, kind="followup", status="pending", revision=0, lines=[], parent_stop_id=identity,
                            projection_kind="append" if source["status"] == "completed" else "first")
            source["continued_to_trip"] = trip["id"]
            for line in choices[identity]["lines"]:
                amount = Decimal(line["needed_kg"])
                product = _product(previous, line["product_id"])
                linked = _ensure_product(trip, product["name"], product["unit"])
                new_stop["lines"].append({"id": uuid.uuid4().hex, "product_id": linked["id"], "name": linked["name"],
                                          "planned": _text(amount), "allocated": "0", "reserved": "0", "accepted": "0",
                                          "reason": "", "comment": "", "position_id": line.get("position_id", ""),
                                          "loading_line_id": line.get("loading_line_id", "")})
            trip["stops"].append(new_stop)
        connection.execute("INSERT INTO trips VALUES(?,?,?,?,?)", (trip["id"], trip["driver_id"], trip["vehicle_id"], trip["status"], _json(trip)))
        previous["continuation_trip_id"] = trip["id"]
        previous["revision"] += 1
        previous["history"].append({"kind": "continued_in_new_trip", "at": _now(), "actor": actor, "details": {"trip_id": trip["id"]}})
        _save(connection, previous)
        connection.execute("INSERT INTO operations VALUES(?,?,?)", (operation_id, trip["id"], _hash(request)))
        return trip


def schedule_followup(trip_id, revision, stop_id, actor, operation_id):
    def apply(trip, connection):
        if trip["status"] not in {"active", "on_base"}:
            raise TripConflict("Довоз доступен только до полной выгрузки")
        source = _stop(trip, stop_id)
        choice = next((item for item in backlog_choices(trip) if item["stop_id"] == stop_id), None)
        if source["status"] != "completed" or choice is None:
            raise TripConflict("Нет недовезённого товара у этого магазина")
        stop = {key: source.get(key, "") for key in ("assignment_id", "source_store_id", "order_record_id", "route_key", "destination_id", "name", "route_label")}
        stop.update(id=uuid.uuid4().hex, kind="followup", status="pending", revision=0, parent_stop_id=stop_id,
                    projection_kind="append", lines=[])
        for line in choice["lines"]:
            stop["lines"].append({**line, "id": uuid.uuid4().hex, "planned": line["needed_kg"], "accepted": "0",
                                  "reserved": "0", "allocated": "0", "reason": "", "comment": ""})
        trip["stops"].append(stop)
        source["continued_to_trip"] = trip_id
        _allocate_stops(trip, [stop])
    return _mutate(trip_id, revision, operation_id, actor, "followup_scheduled", {"stop_id": stop_id}, apply, {"dashboard"})


def _operation_id(value):
    if not isinstance(value, str) or not value or len(value) > 128:
        raise TripError("Некорректный идентификатор операции")


def _mutate(trip_id, revision, operation_id, actor, kind, request, apply, kinds):
    actor = _actor(actor, kinds)
    _operation_id(operation_id)
    fingerprint = _hash({"kind": kind, "request": request, "actor": [actor["kind"], actor["id"]], "revision": revision})
    with _db(True) as connection:
        trip = _load(connection, trip_id)
        if actor["kind"] == "driver" and actor["id"] != trip["driver_id"]:
            raise TripError("Рейс принадлежит другому водителю")
        if actor["kind"] == "loader" and actor.get("vehicle_id") != trip["vehicle_id"]:
            raise TripError("Рейс принадлежит другой машине")
        known = connection.execute("SELECT trip,fingerprint FROM operations WHERE id=?", (operation_id,)).fetchone()
        if known:
            if known["trip"] != trip_id or known["fingerprint"] != fingerprint:
                raise TripConflict("Идентификатор операции использован с другими данными")
        else:
            if trip["status"] == "closed":
                raise TripConflict("Рейс уже закрыт")
            if revision is not None and (type(revision) is not int or revision != trip["revision"]):
                raise TripConflict("Рейс изменился. Обновите данные")
            apply(trip, connection)
            trip["revision"] += 1
            trip["history"].append({"kind": kind, "at": _now(), "actor": actor, "operation_id": operation_id, "details": deepcopy(request)})
            _assert_balances(trip)
            _save(connection, trip)
            connection.execute("INSERT INTO operations VALUES(?,?,?)", (operation_id, trip_id, fingerprint))
    repair_projections(trip_id)
    return load_trip(trip_id)


def _product(trip, identity):
    product = next((item for item in trip["products"] if item["id"] == identity), None)
    if product is None:
        raise TripError("Товар не найден в рейсе")
    return product


def _ensure_product(trip, name, unit):
    key = order_records._line_key(name, unit)
    if not key[0] or key[1] != "kg":
        raise TripError("Для рейса нужен товар с названием и единицей kg")
    existing = next((item for item in trip["products"] if tuple(item["key"]) == key), None)
    if existing:
        return existing
    product = {"id": uuid.uuid4().hex, "key": list(key), "name": str(name).strip(), "unit": key[1],
               "loaded": "0", "topup": "0", "shipped": "0", "returned": "0", "adjustment": "0", "lots": []}
    trip["products"].append(product)
    return product


def _balance(product):
    return Decimal(product["loaded"]) + Decimal(product["topup"]) + Decimal(product["adjustment"]) - Decimal(product["shipped"]) - Decimal(product["returned"])


def _reserved(trip, product_id):
    stops = sum((Decimal(line["reserved"]) for stop in trip["stops"] if stop["status"] == "pending" for line in stop["lines"] if line["product_id"] == product_id), Decimal(0))
    returns = sum((Decimal(line["declared_net_kg"]) for doc in trip["returns"] if doc["status"] == "submitted" for line in doc["lines"] if line["loading_line_id"] == product_id), Decimal(0))
    return stops + returns


def stock(trip):
    return [{"id": item["id"], "name": item["name"], "unit": item["unit"],
             "loaded_kg": item["loaded"], "topup_kg": item["topup"], "shipped_kg": item["shipped"], "returned_kg": item["returned"], "adjustment_kg": item["adjustment"],
             "remaining_kg": "0" if trip["status"] == "released_pending" else _text(_balance(item)),
             "unreconciled_kg": _text(_balance(item)) if trip["status"] == "released_pending" else "0",
             "reserved_kg": _text(_reserved(trip, item["id"])),
             "available_kg": "0" if trip["status"] == "released_pending" else _text(_balance(item) - _reserved(trip, item["id"])),
             "sources": " · ".join((next((member["route_label"] for member in trip["members"] if lot["source"].startswith(member["assignment_id"] + ":")), "Догрузка" if lot["source"].startswith("topup:") else "Расхождение")) + ": " + lot["initial"] + " → остаток " + lot["remaining"] + " кг" for lot in item["lots"])} for item in trip["products"]]


def _assert_balances(trip):
    for item in trip["products"]:
        remaining = _balance(item)
        if remaining < 0 or _reserved(trip, item["id"]) > remaining:
            raise TripConflict("Недостаточно свободного товара в машине")
        if sum((Decimal(lot["remaining"]) for lot in item["lots"]), Decimal(0)) != remaining:
            raise TripError("Нарушена связь остатка с партиями")


def _add_lot(product, amount, source, field):
    product[field] = _text(Decimal(product[field]) + amount)
    product["lots"].append({"source": source, "initial": _text(amount), "remaining": _text(amount)})


def _take(product, amount, preferred=""):
    if amount > _balance(product):
        raise TripConflict("Отгрузка превышает остаток в машине")
    parts = []
    lots = sorted(product["lots"], key=lambda lot: not (preferred and lot["source"].startswith(preferred)))
    for lot in lots:
        taken = min(amount, Decimal(lot["remaining"]))
        if taken:
            lot["remaining"] = _text(Decimal(lot["remaining"]) - taken)
            parts.append({"source": lot["source"], "net_kg": _text(taken)})
            amount -= taken
        if not amount:
            break
    if amount:
        raise TripConflict("Недостаточно товара в исходных партиях")
    return parts


def _stop(trip, stop_id):
    stop = next((item for item in trip["stops"] if item["id"] == stop_id), None)
    if stop is None:
        raise TripNotFound("Задание магазина не найдено")
    return stop


def _import_member(trip, member, allocate=True):
    from modules import goods_returns
    assignment = driver_orders.load_snapshot(member["assignment_id"])
    active = {item["assignment_id"] for item in driver_orders._snapshots(active_only=True)}
    if assignment["assignment_id"] not in active or _member(assignment) != member or not _fleet_available(assignment):
        raise TripConflict("Назначение рейса изменилось")
    if any(doc["assignment_id"] == assignment["assignment_id"] and doc["status"] != "rejected" for doc in goods_returns.list_returns()):
        raise TripConflict("По маршруту уже оформлен возврат. Сначала сверка администратора")
    record = order_records.load_order_record(member["order_record_id"])
    balance = order_records.route_return_balance(record, member["route_key"], member.get("loading_batch_id", ""))
    goods_returns._snapshot_complete(assignment, balance)
    loaded_by_id = {line["loading_line_id"]: line["loaded_net_kg"] for line in balance["lines"]}
    for line in record["loading_lines"]:
        if line.get("route_key") == member["route_key"] and line["id"] in loaded_by_id:
            product = _ensure_product(trip, line["name"], line.get("unit", "kg"))
            amount = _number(loaded_by_id[line["id"]])
            _add_lot(product, amount, member["assignment_id"] + ":" + line["id"], "loaded")
    first_stop = len(trip["stops"])
    for source in assignment["stores"]:
        stop = {"id": uuid.uuid4().hex, "assignment_id": assignment["assignment_id"], "source_store_id": source["store_id"],
                "order_record_id": assignment["order_record_id"], "route_key": assignment["route_key"], "destination_id": source.get("order_record_destination_id", ""),
                "name": source["name"], "route_label": assignment["route_label"], "kind": "planned", "revision": 0,
                "status": "completed" if source["status"] == "completed" else "pending", "lines": []}
        for line in source["lines"]:
            product = _ensure_product(trip, line["name"], line.get("unit", "kg"))
            accepted = _number(line.get("actual_qty", "0")) if stop["status"] == "completed" else Decimal(0)
            portion = {"id": line["line_id"], "product_id": product["id"], "name": product["name"], "planned": str(line["required_qty"]),
                       "reserved": "0", "allocated": "0", "accepted": _text(accepted), "reason": "", "comment": "",
                       "position_id": line.get("order_record_position_id", ""), "loading_line_id": line.get("loading_line_id", "")}
            if accepted:
                portion["sources"] = _take(product, accepted, assignment["assignment_id"] + ":")
                product["shipped"] = _text(Decimal(product["shipped"]) + accepted)
            stop["lines"].append(portion)
        trip["stops"].append(stop)
    if allocate:
        _allocate_stops(trip, trip["stops"][first_stop:])
    trip.setdefault("source_snapshots", {})[assignment["assignment_id"]] = deepcopy(assignment)


def _allocate_stops(trip, stops):
    for stop in stops:
        if stop["status"] != "pending":
            continue
        for line in stop["lines"]:
            product = _product(trip, line["product_id"])
            allocated = min(max(Decimal(0), _number(line["planned"]) - Decimal(line["allocated"])),
                            _balance(product) - _reserved(trip, product["id"]))
            line["reserved"] = _text(Decimal(line["reserved"]) + allocated)
            line["allocated"] = _text(Decimal(line["allocated"]) + allocated)


def _import(trip):
    trip["products"], trip["stops"], trip["source_snapshots"] = [], [], {}
    for member in trip["members"]:
        _import_member(trip, member, allocate=False)
    _allocate_stops(trip, trip["stops"])


def start_trip(trip_id, revision, actor, operation_id):
    def apply(trip, connection):
        if trip["status"] != "draft":
            raise TripConflict("Рейс уже начат")
        _import(trip)
        trip["status"] = "active"
    return _mutate(trip_id, revision, operation_id, actor, "started", {}, apply, {"dashboard"})


def add_member(trip_id, revision, assignment_id, actor, operation_id):
    def apply(trip, connection):
        if trip["status"] not in {"draft", "active", "on_base"}:
            raise TripConflict("К этому рейсу нельзя добавить магазины")
        assignment = next((item for item in assignment_choices() if item["assignment_id"] == assignment_id), None)
        if assignment is None or assignment["driver_id"] != trip["driver_id"] or assignment["vehicle_id"] != trip["vehicle_id"]:
            raise TripConflict("Назначение недоступно для этой машины и водителя")
        member = _member(assignment)
        if trip["status"] != "draft":
            _import_member(trip, member)
            trip.pop("last_stock_check", None)
        connection.execute("INSERT INTO members VALUES(?,?)", (assignment_id, trip_id))
        trip["members"].append(member)
    return _mutate(trip_id, revision, operation_id, actor, "member_added", {"assignment_id": assignment_id}, apply, {"dashboard"})


def complete_stop(trip_id, stop_id, payload, actor):
    if not isinstance(payload, dict):
        raise TripError("Некорректная приёмка")
    def apply(trip, connection):
        if trip["status"] != "active":
            raise TripConflict("Рейс не открыт для отгрузок")
        stop = _stop(trip, stop_id)
        if stop["status"] != "pending" or type(payload.get("base_revision")) is not int or payload["base_revision"] != stop["revision"]:
            raise TripConflict("Задание изменено или уже завершено")
        measures = payload.get("measurements")
        reasons = payload.get("reasons", {})
        if not isinstance(measures, dict) or set(measures) != {line["id"] for line in stop["lines"]} or not isinstance(reasons, dict):
            raise TripError("Заполните чистый вес каждой позиции")
        for line in stop["lines"]:
            measure = order_records._validated_shipment_measurement(measures[line["id"]])
            accepted = _number(measure["net_weight_kg"])
            if accepted > Decimal(line["reserved"]):
                raise TripConflict("Принятый вес превышает выделенный товар. Нужна дополнительная поставка")
            reason = reasons.get(line["id"], {})
            if not isinstance(reason, dict):
                raise TripError("Некорректная причина отказа")
            comment = str(reason.get("comment", "")).strip()
            if len(comment) > 2000:
                raise TripError("Слишком длинный комментарий")
            if (accepted == 0 or accepted < _number(line["planned"])) and (reason.get("reason") not in REFUSAL_REASONS or (reason.get("reason") == "Другое" and not comment)):
                raise TripError("Укажите причину частичного или полного отказа")
            product = _product(trip, line["product_id"])
            line["sources"] = _take(product, accepted, stop.get("assignment_id", "") + ":")
            product["shipped"] = _text(Decimal(product["shipped"]) + accepted)
            line.update(accepted=_text(accepted), reserved="0", reason=str(reason.get("reason", "")), comment=comment)
        stop.update(status="completed", revision=stop["revision"] + 1, completed_at=_now(), completed_by=_actor(actor, {"driver", "loader"}))
        if stop["kind"] in {"planned", "followup"}:
            projection = {"stop_id": stop_id, "operation_id": payload["operation_id"]}
            connection.execute("INSERT INTO outbox VALUES(?,?,?,0)", (payload["operation_id"], trip_id, _json(projection)))
    return _mutate(trip_id, None, payload.get("operation_id"), actor, "store_accepted", {"stop_id": stop_id, "payload": payload}, apply, {"driver", "loader"})


def store_catalogue():
    from modules.config import load_stores
    stores = set()
    for mode in ("Город", "Область"):
        try:
            groups = load_stores(paths.stores_file_for(mode))
        except FileNotFoundError:
            continue
        if not isinstance(groups, dict) or any(not isinstance(values, list) for values in groups.values()):
            raise TripError("Некорректный список магазинов")
        stores.update(str(name) for values in groups.values() for name in values)
    return stores


def redirect(trip_id, revision, product_id, amount, store_name, actor, operation_id):
    amount = _number(amount)
    name = str(store_name).strip()
    if not amount or not name or len(name) > 200:
        raise TripError("Укажите магазин и положительный вес")
    # The configured store catalogue or an existing stop is the allowed destination.
    def apply(trip, connection):
        if trip["status"] not in {"active", "on_base"}:
            raise TripConflict("Перенаправление доступно только до полной выгрузки")
        allowed = {stop["name"] for stop in trip["stops"]} | store_catalogue()
        if name not in allowed:
            raise TripError("Выберите магазин из списка")
        product = _product(trip, product_id)
        trip["stops"].append({"id": uuid.uuid4().hex, "assignment_id": "", "kind": "transfer", "name": name,
                              "route_label": "Дополнительная поставка", "status": "pending", "revision": 0,
                              "lines": [{"id": uuid.uuid4().hex, "product_id": product_id, "name": product["name"],
                                         "planned": _text(amount), "allocated": _text(amount), "reserved": _text(amount), "accepted": "0", "reason": "", "comment": ""}]})
    return _mutate(trip_id, revision, operation_id, actor, "redirected", {"product_id": product_id, "amount": _text(amount), "store": name}, apply, {"dashboard"})


def edit_redirect(trip_id, revision, stop_id, product_id, amount, store_name, actor, operation_id):
    amount = _number(amount)
    name = str(store_name).strip()
    if not amount or not name:
        raise TripError("Укажите магазин и положительный вес")
    def apply(trip, connection):
        if trip["status"] != "active":
            raise TripConflict("Рейс не активен")
        stop = _stop(trip, stop_id)
        if stop["kind"] != "transfer" or stop["status"] != "pending":
            raise TripConflict("Исполненное задание нельзя изменить")
        if name not in ({item["name"] for item in trip["stops"]} | store_catalogue()):
            raise TripError("Выберите магазин из списка")
        product = _product(trip, product_id)
        line = stop["lines"][0]
        line.update(product_id=product_id, name=product["name"], planned=_text(amount), allocated=_text(amount), reserved=_text(amount))
        stop.update(name=name, revision=stop["revision"] + 1)
    return _mutate(trip_id, revision, operation_id, actor, "redirect_updated", {"stop_id": stop_id, "product_id": product_id, "amount": _text(amount), "store": name}, apply, {"dashboard"})


def cancel_draft(trip_id, revision, comment, actor, operation_id):
    if not str(comment).strip():
        raise TripError("Укажите причину отмены рейса")
    def apply(trip, connection):
        if trip["status"] != "draft":
            raise TripConflict("Начатый рейс нельзя отменить как черновик")
        connection.execute("DELETE FROM members WHERE trip=?", (trip_id,))
        trip.update(status="closed", cancelled_at=_now(), cancellation=str(comment).strip())
    return _mutate(trip_id, revision, operation_id, actor, "draft_cancelled", {"comment": comment}, apply, {"dashboard"})


def cancel_stop(trip_id, revision, stop_id, comment, actor, operation_id):
    if not str(comment).strip():
        raise TripError("Укажите причину отмены задания")
    def apply(trip, connection):
        if trip["status"] != "active":
            raise TripConflict("Рейс не активен")
        stop = _stop(trip, stop_id)
        if stop["status"] != "pending":
            raise TripConflict("Завершённое задание нельзя отменить")
        # Original shops must be completed with a reason, not hidden from order history.
        if stop["kind"] != "transfer":
            raise TripError("Исходный магазин завершает водитель с причиной отказа")
        stop.update(status="cancelled", revision=stop["revision"] + 1, cancellation=str(comment).strip())
        for line in stop["lines"]:
            line["reserved"] = "0"
    return _mutate(trip_id, revision, operation_id, actor, "redirect_cancelled", {"stop_id": stop_id, "comment": comment}, apply, {"dashboard"})


def save_topup(trip_id, revision, product_id, measurement, actor, operation_id, topup_id="", target_stop_id=""):
    if not isinstance(measurement, dict):
        raise TripError("Некорректные измерения догрузки")
    def apply(trip, connection):
        if trip["status"] not in {"active", "on_base"}:
            raise TripConflict("Догрузка доступна только до полной выгрузки")
        _product(trip, product_id)
        order_records.loading_measurement_parts(measurement)
        if target_stop_id:
            stop = _stop(trip, target_stop_id)
            if stop["status"] != "pending" or not any(line["product_id"] == product_id for line in stop["lines"]):
                raise TripConflict("Для догрузки нужен незавершённый магазин с этим товаром")
        target = next((item for item in trip["topups"] if item["id"] == topup_id), None) if topup_id else None
        if topup_id and (target is None or target["status"] != "draft"):
            raise TripConflict("Догрузка не найдена или уже подтверждена")
        if target is None:
            target = {"id": uuid.uuid4().hex, "status": "draft"}
            trip["topups"].append(target)
        target.update(product_id=product_id, measurement=deepcopy(measurement), target_stop_id=target_stop_id)
    return _mutate(trip_id, revision, operation_id, actor, "topup_draft", {"product_id": product_id, "measurement": measurement, "topup_id": topup_id, "target_stop_id": target_stop_id}, apply, {"dashboard", "loader"})


def add_product(trip_id, revision, name, actor, operation_id):
    catalogue = {order_records._line_key(line["name"], line.get("unit", "kg")) for snapshot in driver_orders._snapshots(active_only=True) for store in snapshot["stores"] for line in store["lines"]}
    if order_records._line_key(name, "kg") not in catalogue:
        raise TripError("Выберите товар из текущих заказов")
    def apply(trip, connection):
        if trip["status"] not in {"active", "on_base"}:
            raise TripConflict("Рейс не открыт для догрузки")
        _ensure_product(trip, name, "kg")
    return _mutate(trip_id, revision, operation_id, actor, "product_added", {"name": name}, apply, {"dashboard", "loader"})


def cancel_topup(trip_id, revision, topup_id, actor, operation_id):
    def apply(trip, connection):
        target = next((item for item in trip["topups"] if item["id"] == topup_id), None)
        if target is None or target["status"] != "draft":
            raise TripConflict("Черновик догрузки не найден")
        target["status"] = "cancelled"
    return _mutate(trip_id, revision, operation_id, actor, "topup_cancelled", {"topup_id": topup_id}, apply, {"dashboard", "loader"})


def confirm_topup(trip_id, revision, topup_id, actor, operation_id):
    def apply(trip, connection):
        if trip["status"] not in {"active", "on_base"}:
            raise TripConflict("Рейс не открыт для догрузки")
        target = next((item for item in trip["topups"] if item["id"] == topup_id), None)
        if target is None or target["status"] != "draft":
            raise TripConflict("Догрузка не найдена или подтверждена")
        measure = deepcopy(target["measurement"])
        for part in order_records.loading_measurement_parts(measure):
            for field in ("box_count", "tare_weight_per_box_kg", "gross_weight_kg"):
                _number(part.get(field, ""))
        order_records._refresh_loading_measurement(measure)
        measure = order_records._validated_loading_measurement(measure, require_zero_reason=True)
        amount = _number(measure["net_weight_kg"])
        if not amount:
            raise TripError("Догрузка должна иметь положительный вес")
        product = _product(trip, target["product_id"])
        _add_lot(product, amount, "topup:" + target["id"], "topup")
        if target.get("target_stop_id"):
            stop = _stop(trip, target["target_stop_id"])
            if stop["status"] != "pending":
                raise TripConflict("Магазин уже завершён. Пересохраните догрузку в свободный остаток")
            line = next(line for line in stop["lines"] if line["product_id"] == product["id"])
            allocated = min(amount, max(Decimal(0), _number(line["planned"]) - Decimal(line["allocated"])))
            line["reserved"] = _text(Decimal(line["reserved"]) + allocated)
            line["allocated"] = _text(Decimal(line["allocated"]) + allocated)
        _allocate_stops(trip, trip["stops"])
        target.update(status="confirmed", measurement=measure, confirmed_at=_now())
        trip.pop("last_stock_check", None)
    return _mutate(trip_id, revision, operation_id, actor, "topup_confirmed", {"topup_id": topup_id}, apply, {"dashboard", "loader"})


def _occurred_at(value):
    try:
        moment = datetime.fromisoformat(str(value))
        if moment.tzinfo is None:
            moment = moment.astimezone()
    except (TypeError, ValueError) as error:
        raise TripError("Укажите дату и время фактического события") from error
    if moment > datetime.now().astimezone():
        raise TripError("Дата события не может быть в будущем")
    return moment.isoformat()


def _release_reservations(trip):
    for product in trip["products"]:
        excess = _reserved(trip, product["id"]) - _balance(product)
        if excess <= 0:
            continue
        for stop in reversed(trip["stops"]):
            if stop["status"] != "pending":
                continue
            for line in reversed(stop["lines"]):
                if line["product_id"] != product["id"] or excess <= 0:
                    continue
                released = min(excess, Decimal(line["reserved"]))
                line["reserved"] = _text(Decimal(line["reserved"]) - released)
                line["allocated"] = _text(Decimal(line["allocated"]) - released)
                excess -= released
            if excess <= 0:
                break
        if excess > 0:
            raise TripConflict("Товар уже заявлен в возврате")


def arrive_at_base(trip_id, revision, actor, operation_id):
    def apply(trip, connection):
        if trip["status"] != "active":
            raise TripConflict("Вернуться на базу можно только в активном рейсе")
        trip["status"] = "on_base"
        trip["base_arrived_at"] = _now()
        trip.pop("last_stock_check", None)
    return _mutate(trip_id, revision, operation_id, actor, "arrived_at_base", {}, apply, {"driver", "loader", "dashboard"})


def check_before_departure(trip_id, revision, amounts, actor, operation_id):
    def apply(trip, connection):
        if trip["status"] != "on_base":
            raise TripConflict("Проверка доступна, когда машина находится на базе")
        if not isinstance(amounts, dict) or set(amounts) != {item["id"] for item in trip["products"]}:
            raise TripError("Проверьте каждый товар в машине")
        check = {item["id"]: _text(_number(amounts[item["id"]])) for item in trip["products"]}
        trip["last_stock_check"] = {"at": _now(), "amounts": check, "matches": all(Decimal(check[item["id"]]) == _balance(item) for item in trip["products"])}
    return _mutate(trip_id, revision, operation_id, actor, "stock_checked", {"amounts": amounts}, apply, {"driver", "loader", "dashboard"})


def resume_trip(trip_id, revision, actor, operation_id):
    def apply(trip, connection):
        if trip["status"] != "on_base":
            raise TripConflict("Рейс не ожидает продолжения")
        check = trip.get("last_stock_check")
        if not check or not check["matches"] or any(Decimal(check["amounts"].get(item["id"], "-1")) != _balance(item) for item in trip["products"]):
            raise TripConflict("Сверьте фактический остаток перед выездом")
        trip["status"] = "active"
        trip["departed_at"] = _now()
    return _mutate(trip_id, revision, operation_id, actor, "resumed", {}, apply, {"driver", "loader", "dashboard"})


def _unload_measurement(value):
    if not isinstance(value, dict):
        raise TripError("Укажите чистый вес или вес с тарой")
    try:
        if value.get("kind") == "net":
            return order_records._validated_shipment_measurement(value)
        if value.get("kind") == "gross":
            measure = order_records._validated_measurement({key: value.get(key, "") for key in ("box_count", "tare_weight_per_box_kg", "gross_weight_kg")})
            return {**measure, "kind": "gross"}
    except order_records.OrderRecordError as error:
        raise TripError(str(error)) from error
    raise TripError("Выберите тип веса: чистый или с тарой")


def unload_part(trip_id, revision, measurements, occurred_at, actor, operation_id):
    occurred_at = _occurred_at(occurred_at)
    def apply(trip, connection):
        if trip["status"] != "on_base":
            raise TripConflict("Частичная выгрузка возможна только на базе")
        if not isinstance(measurements, dict) or not measurements:
            raise TripError("Выберите товары для выгрузки")
        lines = []
        for product_id, value in measurements.items():
            product = _product(trip, product_id)
            measure = _unload_measurement(value)
            amount = _number(measure["net_weight_kg"])
            if not amount or amount > _balance(product):
                raise TripError("Вес выгрузки должен быть положительным и не превышать остаток")
            lines.append({"product_id": product_id, "name": product["name"], "measurement": measure})
        if sum((_balance(item) for item in trip["products"]), Decimal(0)) == sum((Decimal(line["measurement"]["net_weight_kg"]) for line in lines), Decimal(0)):
            raise TripError("Для пустой машины оформите полную выгрузку")
        for line in lines:
            product = _product(trip, line["product_id"])
            amount = Decimal(line["measurement"]["net_weight_kg"])
            line["sources"] = _take(product, amount)
            product["returned"] = _text(Decimal(product["returned"]) + amount)
        _release_reservations(trip)
        trip.setdefault("unloads", []).append({"id": uuid.uuid4().hex, "kind": "partial", "status": "accepted", "occurred_at": occurred_at,
                                               "recorded_at": _now(), "lines": lines})
        trip.pop("last_stock_check", None)
        trip.pop("unload_draft", None)
    return _mutate(trip_id, revision, operation_id, actor, "partial_unloaded", {"measurements": measurements, "occurred_at": occurred_at}, apply, {"dashboard", "loader"})


def unload_all(trip_id, revision, occurred_at, note, actor, operation_id):
    occurred_at = _occurred_at(occurred_at)
    def apply(trip, connection):
        if trip["status"] not in {"active", "on_base"} or any(doc["status"] == "submitted" for doc in trip["returns"]):
            raise TripConflict("Машина не готова к полной выгрузке")
        for stop in trip["stops"]:
            if stop["status"] == "pending":
                stop.update(status="deferred", revision=stop["revision"] + 1, deferred_at=occurred_at)
                for line in stop["lines"]:
                    line["reserved"] = line["allocated"] = "0"
        lines = [{"product_id": item["id"], "name": item["name"], "book_net_kg": _text(_balance(item))}
                 for item in trip["products"] if _balance(item)]
        trip.setdefault("unloads", []).append({"id": uuid.uuid4().hex, "kind": "full", "status": "awaiting_weights",
                                               "occurred_at": occurred_at, "recorded_at": _now(), "note": str(note).strip()[:2000], "lines": lines})
        for topup in trip["topups"]:
            if topup["status"] == "draft":
                topup.update(status="cancelled", cancelled_at=_now(), cancellation="Машина полностью выгружена")
        trip.pop("last_stock_check", None)
        trip["status"] = "released_pending"
    return _mutate(trip_id, revision, operation_id, actor, "fully_unloaded", {"occurred_at": occurred_at, "note": note}, apply, {"driver", "loader", "dashboard"})


def save_unload_draft(trip_id, revision, measurements, actor, operation_id):
    def apply(trip, connection):
        if trip["status"] not in {"on_base", "released_pending"}:
            raise TripConflict("Черновик выгрузки недоступен")
        if not isinstance(measurements, dict) or set(measurements) - {item["id"] for item in trip["products"]}:
            raise TripError("Некорректный состав выгрузки")
        for value in measurements.values():
            if not isinstance(value, dict) or value.get("kind") not in {"net", "gross"}:
                raise TripError("Выберите тип веса")
            if set(value) - {"kind", "net_weight_kg", "box_count", "tare_weight_per_box_kg", "gross_weight_kg"}:
                raise TripError("Неизвестные поля веса")
            if any(not isinstance(item, str) or len(item) > 64 for item in value.values()):
                raise TripError("Некорректный черновик веса")
        trip["unload_draft"] = deepcopy(measurements)
    return _mutate(trip_id, revision, operation_id, actor, "unload_draft_saved", {"measurements": measurements}, apply, {"dashboard", "loader"})


def reconcile_unload(trip_id, revision, measurements, comment, actor, operation_id):
    def apply(trip, connection):
        if trip["status"] != "released_pending":
            raise TripConflict("Нет выгрузки, ожидающей внесения веса")
        doc = next((item for item in reversed(trip.get("unloads", [])) if item["status"] == "awaiting_weights"), None)
        if doc is None or not isinstance(measurements, dict) or set(measurements) != {line["product_id"] for line in doc["lines"]}:
            raise TripError("Укажите вес каждого товара из бланка выгрузки")
        lines = []
        for item in doc["lines"]:
            measure = _unload_measurement(measurements[item["product_id"]])
            actual = _number(measure["net_weight_kg"])
            expected = Decimal(item["book_net_kg"])
            if actual != expected and not str(comment).strip():
                raise TripError("При расхождении укажите причину")
            lines.append((item, measure, actual, expected))
        for item, measure, actual, expected in lines:
            product = _product(trip, item["product_id"])
            if actual > expected:
                _add_lot(product, actual - expected, "difference:" + operation_id, "adjustment")
            item.update(measurement=measure, accepted_net_kg=_text(actual), difference_kg=_text(actual - expected))
            item["sources"] = _take(product, actual)
            product["returned"] = _text(Decimal(product["returned"]) + actual)
            if actual < expected:
                _take(product, expected - actual)
                product["adjustment"] = _text(Decimal(product["adjustment"]) - (expected - actual))
        doc.update(status="accepted", accepted_at=_now(), comment=str(comment).strip())
        if trip.get("projection_error"):
            raise TripConflict("Сначала синхронизируйте отгрузки магазинов")
        trip.update(status="closed", closed_at=_now())
    return _mutate(trip_id, revision, operation_id, actor, "unload_reconciled", {"measurements": measurements, "comment": comment}, apply, {"dashboard"})


def return_context(trip):
    from modules.goods_returns import RETURN_REASONS
    pending = any(stop["status"] == "pending" for stop in trip["stops"])
    doc = trip["returns"][-1] if trip["returns"] else None
    lines = [{"loading_line_id": item["id"], "name": item["name"], "planned_kg": "0", "loaded_net_kg": _text(Decimal(item["loaded"]) + Decimal(item["topup"]) + Decimal(item["adjustment"])),
              "shipped_net_kg": item["shipped"], "available_net_kg": _text(_balance(item))} for item in trip["products"]]
    eligible = trip["status"] in {"active", "on_base"} and not pending and not trip.get("projection_error") and (doc is None or doc["status"] == "rejected")
    return {"assignment_id": trip["id"], "trip_id": trip["id"], "route_label": "Рейс машины · " + (trip.get("route_label") or ", ".join(item["route_label"] for item in trip["members"])),
            "driver_id": trip["driver_id"], "vehicle_id": trip["vehicle_id"], "loading_ready": trip["status"] != "draft", "complete": not pending,
            "eligible": eligible, "error": "Завершите все задания и синхронизируйте отгрузки" if pending else trip.get("projection_error", ""),
            "lines": lines, "reasons": list(RETURN_REASONS), "document": deepcopy(doc),
            "facts_token": _hash({"lines": lines, "stops": [(s["id"], s["status"], s["revision"]) for s in trip["stops"]]})}


def submit_return(trip_id, payload, actor):
    from modules import goods_returns
    def apply(trip, connection):
        context = return_context(trip)
        if not context["eligible"] or payload.get("facts_token") != context["facts_token"]:
            raise TripConflict("Остатки изменились или рейс ещё не готов к возврату")
        prior = context["document"]
        if payload.get("base_revision") != (prior["revision"] if prior else 0):
            raise TripConflict("Версия возврата изменилась")
        lines, total = goods_returns._validated_lines(payload.get("lines"), context)
        for line in lines:
            line["declared_net_kg"] = line["measurement"]["net_weight_kg"]
        document = {"id": uuid.uuid4().hex, "assignment_id": trip_id, "trip_id": trip_id, "driver_id": trip["driver_id"],
                    "route_label": context["route_label"], "status": "submitted", "revision": (prior["revision"] if prior else 0) + 1,
                    "version": len(trip["returns"]) + 1, "lines": lines, "total_net_kg": total, "submitted_at": _now(), "history": []}
        trip["returns"].append(document)
        trip["status"] = "return_pending"
    return _mutate(trip_id, None, payload.get("operation_id"), actor, "return_submitted", payload, apply, {"driver", "loader"})["returns"][-1]


def receive_return(trip_id, revision, actual, comment, actor, operation_id, reject=False):
    def apply(trip, connection):
        if trip["status"] != "return_pending" or not trip["returns"]:
            raise TripConflict("Нет возврата на приёмку")
        doc = trip["returns"][-1]
        if reject:
            if not str(comment).strip():
                raise TripError("Укажите причину отклонения")
            doc["status"] = "rejected"
            trip["status"] = "active"
        else:
            if not isinstance(actual, dict) or set(actual) != {line["loading_line_id"] for line in doc["lines"]}:
                raise TripError("Введите фактически принятый вес каждой позиции")
            for line in doc["lines"]:
                amount = _number(actual[line["loading_line_id"]])
                product = _product(trip, line["loading_line_id"])
                line["sources"] = _take(product, amount)
                product["returned"] = _text(Decimal(product["returned"]) + amount)
                line["accepted_net_kg"] = _text(amount)
                line["difference_kg"] = _text(amount - Decimal(line["declared_net_kg"]))
            doc["status"] = "accepted"
        doc["revision"] += 1
        doc["history"].append({"kind": doc["status"], "at": _now(), "actor": actor, "comment": str(comment)})
    return _mutate(trip_id, revision, operation_id, actor, "return_received" if not reject else "return_rejected", {"actual": actual, "comment": comment, "reject": reject}, apply, {"dashboard", "loader"})


def resolve_difference(trip_id, revision, product_id, signed_amount, comment, actor, operation_id):
    text = str(signed_amount).strip().replace(",", ".")
    try:
        signed = Decimal(text)
    except InvalidOperation as error:
        raise TripError("Укажите корректное расхождение") from error
    amount = _number(signed.copy_abs()) * (-1 if signed.is_signed() else 1)
    if not amount or not str(comment).strip():
        raise TripError("Укажите ненулевое расхождение и причину")
    def apply(trip, connection):
        if trip["status"] not in {"active", "on_base", "return_pending"} or (trip["status"] != "on_base" and any(stop["status"] == "pending" for stop in trip["stops"])):
            raise TripConflict("Расхождение оформляется на базе либо после завершения заданий")
        product = _product(trip, product_id)
        if amount < 0:
            if -amount > _balance(product):
                raise TripConflict("Нельзя списать больше остатка в машине")
            _take(product, -amount)
            product["adjustment"] = _text(Decimal(product["adjustment"]) + amount)
            _release_reservations(trip)
        else:
            _add_lot(product, amount, "difference:" + operation_id, "adjustment")
        trip.pop("last_stock_check", None)
    return _mutate(trip_id, revision, operation_id, actor, "difference_resolved", {"product_id": product_id, "amount": text, "comment": comment}, apply, {"dashboard"})


def close_trip(trip_id, revision, actor, operation_id):
    def apply(trip, connection):
        if trip["status"] in {"draft", "released_pending"} or any(stop["status"] == "pending" for stop in trip["stops"]) or any(item["status"] == "submitted" for item in trip["returns"]) or trip["projection_error"]:
            raise TripConflict("Завершите задания, возврат и синхронизацию")
        if any(_balance(item) for item in trip["products"]):
            raise TripConflict("Остаток ненулевой. Примите возврат или оформите расхождение")
        if any(item["status"] == "draft" for item in trip["topups"]):
            raise TripConflict("Есть незавершённая догрузка")
        trip.update(status="closed", closed_at=_now())
    return _mutate(trip_id, revision, operation_id, actor, "closed", {}, apply, {"dashboard"})


def repair_projections(trip_id):
    if not paths.VEHICLE_TRIPS_FILE.exists():
        return
    # Keep the SQLite write barrier while updating JSON. Backups acquire the
    # same barrier, so an acknowledged projection cannot outrun its snapshot.
    with _db(True) as connection:
        trip = _load(connection, trip_id)
        pending = connection.execute("SELECT id,payload FROM outbox WHERE trip=? AND done=0 ORDER BY rowid", (trip_id,)).fetchall()
        for row in pending:
            try:
                stop = _stop(trip, json.loads(row["payload"])["stop_id"])
                actor = stop.get("completed_by") or {"kind": "driver", "id": trip["driver_id"], "name": trip["driver_name"]}
                snapshot = driver_orders.load_snapshot(stop["assignment_id"])
                source = next(store for store in snapshot["stores"] if store["store_id"] == stop["source_store_id"])
                accepted = {line["position_id"]: line["accepted"] for line in stop["lines"]}
                measures = {line["order_record_position_id"]: {"kind": "net", "net_weight_kg": accepted.get(line["order_record_position_id"], "0")}
                            for line in source["lines"]}
                source_measures = {line["line_id"]: measures[line["order_record_position_id"]] for line in source["lines"]}
                if stop["kind"] == "followup" and stop.get("projection_kind") == "append":
                    order_records.append_store_shipment(stop["order_record_id"], stop["route_key"], stop["destination_id"], measures, row["id"], actor)
                    driver_orders.append_store_delivery(stop["assignment_id"], stop["source_store_id"], source_measures, row["id"])
                else:
                    order_records.save_store_shipment(stop["order_record_id"], stop["route_key"], stop["destination_id"], measures, row["id"], actor,
                                                     **({"loading_batch_id": snapshot["loading_batch_id"]} if snapshot.get("loading_batch_id") else {}))
                    driver_orders.complete_store(driver_orders.sidecar_path(stop["assignment_id"]), stop["source_store_id"],
                                                 source_measures, row["id"], snapshot["revision"])
                trip.setdefault("source_snapshots", {})[stop["assignment_id"]] = driver_orders.load_snapshot(stop["assignment_id"])
                connection.execute("UPDATE outbox SET done=1 WHERE id=?", (row["id"],))
            except (ValueError, OSError) as error:
                trip["projection_error"] = "Ожидает сверки проекций: " + str(error)
                _save(connection, trip)
                return
        trip["projection_error"] = ""
        _save(connection, trip)


def complete_legacy_stop(assignment_id, store_id, payload, actor):
    trip = trip_for_assignment(assignment_id)
    if trip is None:
        raise TripNotFound("Назначение не связано с рейсом")
    if actor.get("id") != trip["driver_id"]:
        raise TripNotFound("Рейс не найден")
    snapshot = driver_orders.load_snapshot(assignment_id)
    source = next((store for store in snapshot["stores"] if store["store_id"] == store_id), None)
    if source is None:
        raise TripNotFound("Магазин не найден")
    if type(payload.get("base_revision")) is not int:
        raise TripError("Некорректная версия назначения")
    values = payload.get("measurements")
    if values is None:
        quantities = payload.get("quantities", {})
        if not isinstance(quantities, dict):
            raise TripError("Некорректные количества")
        values = {key: {"kind": "net", "net_weight_kg": value} for key, value in quantities.items()}
    if not isinstance(values, dict) or set(values) != {line["line_id"] for line in source["lines"]}:
        raise TripError("Заполните каждую позицию")
    known = next((item for item in snapshot.get("operations", []) if item.get("operation_id") == payload.get("operation_id")), None)
    if known:
        if known.get("store_id") != store_id or any(order_records._validated_shipment_measurement(values[line["line_id"]])["net_weight_kg"] != line.get("actual_qty") for line in source["lines"]):
            raise TripConflict("Повторная операция содержит другие данные")
        repair_projections(trip["id"])
        return driver_orders.load_snapshot(assignment_id)
    if snapshot["revision"] != payload.get("base_revision"):
        raise TripConflict("Назначение изменилось. Старая операция сохранена на устройстве")
    stop = next((item for item in trip["stops"] if item.get("assignment_id") == assignment_id and item.get("source_store_id") == store_id), None)
    if stop is None:
        raise TripConflict("Сначала начните объединённый рейс")
    translated = {**payload, "measurements": values, "base_revision": stop["revision"], "legacy_base_revision": payload.get("base_revision")}
    complete_stop(trip["id"], stop["id"], translated, actor)
    return driver_orders.load_snapshot(assignment_id)


def restore_source_snapshots(database_path, project_root):
    """Restore trip-owned JSON images from the same SQLite backup epoch."""
    root = Path(project_root)
    folder = root / "data/driver_orders"
    with sqlite3.connect(database_path) as connection:
        connection.execute("PRAGMA trusted_schema=OFF")
        documents = [json.loads(row[0]) for row in connection.execute("SELECT payload FROM trips")]
    snapshots = {}
    for trip in documents:
        for identity, snapshot in trip.get("source_snapshots", {}).items():
            if not isinstance(identity, str) or not identity or any(char not in "0123456789abcdef" for char in identity) or snapshot.get("assignment_id") != identity:
                raise TripError("Некорректная исходная копия назначения")
            if identity not in snapshots or snapshot.get("revision", 0) > snapshots[identity].get("revision", 0):
                snapshots[identity] = snapshot
    for identity, snapshot in snapshots.items():
        driver_orders._atomic_write(folder / (identity + ".json"), snapshot)
    # Trip membership must also remain discoverable after a clean restore.
    if documents:
        index_file = folder / "index.json"
        try:
            index = driver_orders._read(index_file)
        except driver_orders.DriverOrderError:
            index = driver_orders._empty_index()
        try:
            records = json.loads((root / "data/order_records.json").read_text(encoding="utf-8")).get("records", [])
        except (OSError, UnicodeError, ValueError):
            records = []

        def batch_order(snapshot):
            record = next((item for item in records if isinstance(item, dict) and item.get("id") == snapshot.get("order_record_id")), None)
            if record is None:
                return -1
            route_state = ((record.get("loading") or {}).get("route_states") or {}).get(snapshot.get("route_key"), {})
            batches = (route_state or {}).get("batches", [])
            batch_id = snapshot.get("loading_batch_id", "")
            if not batch_id:
                return 0 if not batches else -1
            return next((number for number, batch in enumerate(batches or [], 1) if isinstance(batch, dict) and batch.get("id") == batch_id), -1)

        for trip in documents:
            for identity, snapshot in trip.get("source_snapshots", {}).items():
                logical_id = snapshot.get("logical_assignment_id", identity)
                active_id = index["active"].get(logical_id)
                try:
                    active = driver_orders._read(folder / (active_id + ".json")) if isinstance(active_id, str) else None
                except driver_orders.DriverOrderError:
                    active = None
                if active and active.get("order_record_id") == snapshot.get("order_record_id") and batch_order(active) > batch_order(snapshot):
                    continue
                index["active"][logical_id] = identity
        driver_orders._atomic_write(index_file, index)


def delivery_summary(trip):
    result = []
    for product in trip["products"]:
        groups = {}
        for stop in trip["stops"]:
            if stop["kind"] not in {"planned", "followup"}:
                continue
            for line in stop["lines"]:
                if line["product_id"] != product["id"]:
                    continue
                key = (stop.get("order_record_id"), stop.get("destination_id"), line.get("position_id") or line["id"])
                group = groups.setdefault(key, {"planned": Decimal(0), "accepted": Decimal(0)})
                group["planned"] = max(group["planned"], Decimal(line["planned"]))
                group["accepted"] += Decimal(line["accepted"])
        planned = sum((group["planned"] for group in groups.values()), Decimal(0))
        completed = sum((group["accepted"] for group in groups.values()), Decimal(0))
        necessary = sum((max(Decimal(0), group["planned"] - group["accepted"]) for group in groups.values()), Decimal(0))
        result.append({"name": product["name"], "unit": "kg", "planned": _text(planned), "completed": _text(completed),
                       "necessary": _text(necessary), "shortage_kg": _text(max(Decimal(0), necessary - (Decimal(0) if trip["status"] == "released_pending" else _balance(product)))),
                       "additional_planned": _text(sum((Decimal(line["planned"]) for stop in trip["stops"] if stop["kind"] == "transfer" and stop["status"] != "cancelled" for line in stop["lines"] if line["product_id"] == product["id"]), Decimal(0))),
                       "additional_completed": _text(sum((Decimal(line["accepted"]) for stop in trip["stops"] if stop["kind"] == "transfer" for line in stop["lines"] if line["product_id"] == product["id"]), Decimal(0)))})
    return result


def as_assignment(trip):
    stores = []
    for stop in trip["stops"]:
        if stop["status"] == "cancelled":
            continue
        stores.append({"store_id": stop["id"], "kind": stop["kind"], "name": stop["name"] + " · " + stop["route_label"], "status": stop["status"], "revision": stop["revision"],
                       "lines": [{"line_id": line["id"], "name": line["name"], "unit": "kg", "required_qty": line["planned"], "allocated_qty": line["allocated"],
                                  "actual_qty": line["accepted"] if stop["status"] == "completed" else "", "loading_line_id": line["product_id"],
                                  "shipment_measurement": {"kind": "net", "net_weight_kg": line["accepted"]}, "refusal_reason": line["reason"]} for line in stop["lines"]]})
    return {"assignment_id": trip["id"], "trip_id": trip["id"], "revision": trip["revision"], "route_label": trip.get("route_label") or " + ".join(item["route_label"] for item in trip["members"]),
            "driver_id": trip["driver_id"], "driver_name": trip["driver_name"], "vehicle_id": trip["vehicle_id"], "vehicle_name": trip["vehicle_name"], "vehicle_plate": trip["vehicle_plate"],
            "status": trip["status"], "loading_status": "waiting_loading" if trip["status"] == "draft" else "loaded", "shipment_status": "active", "stores": stores,
            "store_count": len(stores), "completed_stores": sum(s["status"] == "completed" for s in stores), "stock": stock(trip),
            "summary": delivery_summary(trip),
            "return_context": return_context(trip), "refusal_reasons": list(REFUSAL_REASONS), "projection_error": trip["projection_error"],
            "backlog": backlog_choices(trip), "last_stock_check": trip.get("last_stock_check"),
            "unloads": trip.get("unloads", []), "parent_trip_id": trip.get("parent_trip_id", "")}
