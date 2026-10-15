"""Driver and shared vehicle workspace endpoints."""
from modules.driver_mileage import (
    DriverMileageConflict,
    DriverMileageError,
)
from modules.driver_orders import (
    DriverOrderConflict,
    DriverOrderError,
    DriverOrderNotFound,
)
from starlette.responses import JSONResponse
from modules.order_records import (
    OrderRecordConflict,
    OrderRecordError,
    OrderRecordNotFound,
    save_store_shipment,
)
from starlette.requests import Request
from orders_dashboard.api.common import (
    _assignment_for_session,
    _json_payload,
    _loader_available_vehicles,
    _mileage_required_response,
    _mileage_status,
    _public_driver_assignment,
    _session,
    _set_driver_cookie,
)
from modules.fleet import (
    driver_by_id,
    driver_by_login,
    loader_by_id,
    verify_driver_pin,
)
from modules import (
    driver_data,
    driver_mileage,
    driver_orders,
    driver_sessions,
    goods_returns,
    loader_sessions,
    order_records,
    vehicle_trips,
)


def _return_assignment(session: dict, assignment_id: str) -> dict:
    assignment = driver_orders.load_snapshot(assignment_id)
    if assignment.get("driver_id") != session.get("driver_id"):
        raise DriverOrderNotFound("Назначение не найдено")
    return assignment

async def driver_returns(request: Request):
    session, error = _session(request)
    if error:
        return error
    try:
        driver_id = str(session["driver_id"])
        driver_trips = ([item for item in vehicle_trips.list_trips() if item["vehicle_id"] == session["vehicle_id"]]
                        if session.get("kind") == "loader" else vehicle_trips.list_trips(driver_id))
        documents = [] if session.get("kind") == "loader" else [item for item in goods_returns.list_returns() if item["driver_id"] == driver_id]
        documents.extend(doc for trip in driver_trips for doc in trip["returns"])
        trip_assignments = [{"assignment_id": trip["id"], "trip_id": trip["id"], "route_label": "Рейс машины · " + (trip.get("route_label") or ", ".join(item["route_label"] for item in trip["members"])), "order_number": trip["date"], "created_at": trip["created_at"]} for trip in driver_trips]
        assignments = [
            {
                "assignment_id": item["assignment_id"],
                "route_label": str(item.get("route_label", "")),
                "order_number": str(item.get("source_file", "")),
                "created_at": str(item.get("created_at", "")),
            }
            for item in driver_orders.completed_assignments_for_driver(driver_id)
            if not vehicle_trips.trip_for_assignment(item["assignment_id"])
        ] + trip_assignments
    except (goods_returns.GoodsReturnError, DriverOrderError) as invalid:
        return JSONResponse({"ok": False, "error": str(invalid)}, status_code=400)
    return JSONResponse(
        {"ok": True, "returns": documents, "assignments": assignments},
        headers={"Cache-Control": "no-store"},
    )

async def driver_return_detail(request: Request):
    session, error = _session(request, mutate=request.method == "POST")
    if error:
        return error
    try:
        assignment = _return_assignment(session, request.path_params["assignment_id"])
        if request.method == "GET":
            result = {"ok": True, "context": goods_returns.return_context(assignment)}
        else:
            payload = await _json_payload(request)
            if payload is None:
                return JSONResponse({"ok": False, "error": "Некорректный запрос"}, status_code=400)
            document = goods_returns.submit_return(
                assignment, payload,
                {"kind": "driver", "id": str(session["driver_id"]), "name": str(assignment.get("driver_name", ""))},
            )
            result = {"ok": True, "document": document}
    except (DriverOrderNotFound, goods_returns.GoodsReturnNotFound) as missing:
        return JSONResponse({"ok": False, "error": str(missing)}, status_code=404)
    except goods_returns.GoodsReturnConflict as conflict:
        return JSONResponse({"ok": False, "error": str(conflict)}, status_code=409)
    except (DriverOrderError, goods_returns.GoodsReturnError, OrderRecordError) as invalid:
        return JSONResponse({"ok": False, "error": str(invalid)}, status_code=400)
    return JSONResponse(result, headers={"Cache-Control": "no-store"})

async def driver_login(request: Request):
    payload = await _json_payload(request)
    if payload is None:
        return JSONResponse({"ok": False, "error": "Некорректный запрос"}, status_code=400)
    login = str(payload.get("driver_id", payload.get("login", ""))).strip()
    pin = str(payload.get("pin", "")).strip()
    driver = driver_by_login(login) or driver_by_id(login)
    driver_id = str(driver.get("id", "")) if driver else ""
    if not driver_id or not verify_driver_pin(driver_id, pin):
        return JSONResponse({"ok": False, "error": "Неверный идентификатор или PIN"}, status_code=401)

    token, session = driver_sessions.create_session(driver_id)
    response = JSONResponse({
        "ok": True,
        "driver": {"id": driver_id, "name": driver.get("name", "")},
        "csrf_token": session["csrf_token"],
        "mileage": _mileage_status(session),
    })
    _set_driver_cookie(response, request, token)
    return response

async def driver_logout(request: Request):
    session, error = _session(request, mutate=True)
    cookie_name = loader_sessions.SESSION_COOKIE if request.url.path.startswith("/api/crew/") else driver_sessions.SESSION_COOKIE
    if error:
        if error.status_code == 401:
            error.delete_cookie(cookie_name, path="/")
        return error
    token = request.cookies.get(cookie_name)
    if session.get("kind") == "loader":
        loader_sessions.destroy_session(token)
    else:
        driver_sessions.destroy_session(token)
    response = JSONResponse({"ok": True})
    response.delete_cookie(cookie_name, path="/")
    return response

def _driver_available_vehicles(driver_id: str) -> list[dict]:
    current = vehicle_trips.active_for_driver(driver_id)
    sources = [current] if current else [item for item in driver_orders._snapshots(active_only=True) if item.get("driver_id") == driver_id]
    vehicles = {item["vehicle_id"]: {"id": item["vehicle_id"], "name": item.get("vehicle_name", ""), "plate": item.get("vehicle_plate", "")}
                for item in sources if item.get("vehicle_id")}
    return list(vehicles.values())

async def driver_select_vehicle(request: Request):
    session, error = _session(request, mutate=True)
    if error:
        return error
    payload = await _json_payload(request)
    vehicle_id = str((payload or {}).get("vehicle_id", ""))
    if vehicle_id not in {item["id"] for item in _driver_available_vehicles(session["driver_id"])}:
        return JSONResponse({"ok": False, "error": "Машина не назначена этому водителю"}, status_code=404)
    driver_sessions.select_vehicle(request.cookies.get(driver_sessions.SESSION_COOKIE), vehicle_id)
    return JSONResponse({"ok": True, "vehicle_id": vehicle_id})

async def driver_me(request: Request):
    session, error = _session(request)
    if error:
        return error
    driver = loader_by_id(session["driver_id"]) if session.get("kind") == "loader" else driver_by_id(session["driver_id"])
    if driver is None or not driver.get("active"):
        return JSONResponse({"ok": False, "error": "Профиль недоступен"}, status_code=401)
    assignment = _assignment_for_session(session)
    return JSONResponse({
        "ok": True,
        "driver": {"id": driver.get("id", ""), "name": driver.get("name", "")},
        "role": session.get("kind", "driver"),
        "vehicles": _loader_available_vehicles() if session.get("kind") == "loader" else _driver_available_vehicles(session["driver_id"]),
        "vehicle_id": assignment.get("vehicle_id", "") if assignment else session.get("vehicle_id", ""),
        "csrf_token": session["csrf_token"],
        "assignment": _public_driver_assignment(assignment),
        "mileage": _mileage_status(session, assignment),
    })

async def driver_mileage_submit(request: Request):
    session, error = _session(request, mutate=True)
    if error:
        return error
    payload = await _json_payload(request)
    if payload is None:
        return JSONResponse({"ok": False, "error": "Некорректный запрос"}, status_code=400)

    assignment = _assignment_for_session(session)
    status = _mileage_status(session, assignment)
    if assignment is None:
        return JSONResponse(
            {"ok": False, "error": "Активное назначение не найдено", "mileage": status},
            status_code=409,
        )
    if not status["available"]:
        return JSONResponse(
            {"ok": False, "error": status["error"], "mileage": status}, status_code=409
        )

    expected_vehicle_id = status["vehicle"]["id"]
    expected_day = status["date"]
    expected_assignment_id = status["assignment_id"]
    allowed_assignment_ids = {expected_assignment_id}
    if assignment.get("trip_id"):
        allowed_assignment_ids.update(item["assignment_id"] for item in vehicle_trips.load_trip(assignment["trip_id"])["members"])
    if (
        str(payload.get("vehicle_id", "")) != expected_vehicle_id
        or str(payload.get("date", "")) != expected_day
        or str(payload.get("assignment_id", "")) not in allowed_assignment_ids
    ):
        return JSONResponse(
            {
                "ok": False,
                "error": "Назначение или дата изменились. Введите пробег снова.",
                "mileage": status,
            },
            status_code=409,
        )
    try:
        record, idempotent = driver_mileage.record_mileage(
            str(session.get("driver_id", "")),
            expected_vehicle_id,
            status["vehicle"]["name"],
            status["vehicle"]["plate"],
            payload.get("odometer_km"),
            expected_day,
        )
    except DriverMileageConflict as conflict:
        return JSONResponse(
            {"ok": False, "error": str(conflict), "mileage": _mileage_status(session, assignment)},
            status_code=409,
        )
    except DriverMileageError as invalid:
        return JSONResponse({"ok": False, "error": str(invalid)}, status_code=400)
    return JSONResponse({
        "ok": True,
        "record": record,
        "idempotent": idempotent,
        "mileage": _mileage_status(session, assignment),
    })

async def driver_order(request: Request):
    session, error = _session(request)
    if error:
        return error
    assignment = _assignment_for_session(session)
    mileage_error = _mileage_required_response(session, assignment)
    if mileage_error:
        return mileage_error
    if assignment is None:
        return JSONResponse({"ok": True, "assignment": None})
    return JSONResponse({"ok": True, "assignment": _public_driver_assignment(assignment)})

async def driver_complete_store(request: Request):
    session, error = _session(request, mutate=True)
    if error:
        return error
    assignment = _assignment_for_session(session)
    mileage_error = _mileage_required_response(session, assignment)
    if mileage_error:
        return mileage_error
    payload = await _json_payload(request)
    if payload is None:
        return JSONResponse({"ok": False, "error": "Некорректный запрос"}, status_code=400)
    assignment = _assignment_for_session(session)
    if assignment is None:
        return JSONResponse({"ok": False, "error": "Активное назначение не найдено"}, status_code=404)
    requested_id = payload.get("assignment_id", assignment["assignment_id"])
    linked_trip = vehicle_trips.trip_for_assignment(str(requested_id))
    if linked_trip:
        try:
            result = vehicle_trips.complete_legacy_stop(str(requested_id), request.path_params["store_id"], payload, {"kind": "driver", "id": str(session["driver_id"]), "name": str(assignment.get("driver_name", ""))})
            return JSONResponse({"ok": True, "assignment": _public_driver_assignment(result)})
        except vehicle_trips.TripNotFound as missing:
            return JSONResponse({"ok": False, "error": str(missing)}, status_code=404)
        except vehicle_trips.TripConflict as conflict:
            return JSONResponse({"ok": False, "error": str(conflict)}, status_code=409)
        except (vehicle_trips.TripError, OrderRecordError) as invalid:
            return JSONResponse({"ok": False, "error": str(invalid)}, status_code=400)
    if assignment.get("trip_id"):
        return JSONResponse({"ok": False, "error": "Обновите кабинет: отгрузки объединённого рейса отправляются по заданиям"}, status_code=409)
    if requested_id != assignment["assignment_id"]:
        return JSONResponse(
            {"ok": False, "error": "Операция относится к другому рейсу. Данные сохранены на устройстве."},
            status_code=409,
        )
    photo = str(payload.get("photo", ""))
    if ".." in photo or photo.startswith(("/", "\\")):
        return JSONResponse({"ok": False, "error": "Некорректная фотография"}, status_code=400)

    measurements = payload.get("measurements")
    legacy_quantities = not isinstance(measurements, dict)
    if legacy_quantities:
        measurements = payload.get("quantities", {})
    if not isinstance(measurements, dict):
        return JSONResponse({"ok": False, "error": "Некорректные данные отгрузки"}, status_code=400)
    store_id = request.path_params["store_id"]
    store = next(
        (item for item in assignment.get("stores", []) if item.get("store_id") == store_id),
        None,
    )
    if store is None:
        return JSONResponse({"ok": False, "error": "Магазин не найден в назначении"}, status_code=404)
    expected_line_ids = {str(line.get("line_id", "")) for line in store.get("lines", [])}
    if set(measurements) != expected_line_ids:
        return JSONResponse(
            {"ok": False, "error": "Заполните отгрузку для каждой позиции"}, status_code=400
        )
    operation_id = str(payload.get("operation_id", ""))
    known_operation = any(
        operation.get("operation_id") == operation_id
        for operation in assignment.get("operations", [])
    )
    if not known_operation and payload.get("base_revision", -1) != assignment.get("revision"):
        return JSONResponse(
            {"ok": False, "error": "Заказ уже изменён на другом устройстве"}, status_code=409
        )

    record_id = str(assignment.get("order_record_id", ""))
    if record_id:
        record_measurements = {}
        for line in store.get("lines", []):
            position_id = str(line.get("order_record_position_id", ""))
            line_id = str(line.get("line_id", ""))
            if not position_id or line_id not in measurements:
                return JSONResponse(
                    {"ok": False, "error": "Рейс не связан с позициями заказа"}, status_code=409
                )
            record_measurements[position_id] = (
                {"legacy_net_weight_kg": measurements[line_id]} if legacy_quantities else measurements[line_id]
            )
    try:
        with order_records._LOCK, driver_orders._LOCK:
            latest = driver_orders.load_snapshot(assignment["assignment_id"])
            if not any(op.get("operation_id") == operation_id for op in latest.get("operations", [])) and latest["revision"] != payload.get("base_revision", -1):
                return JSONResponse({"ok": False, "error": "Заказ уже изменён на другом устройстве"}, status_code=409)
            if record_id:
                save_store_shipment(
                    record_id,
                    str(assignment.get("route_key", "")),
                    str(store.get("order_record_destination_id", "")),
                    record_measurements,
                    operation_id,
                    {
                        "kind": "driver",
                        "id": str(session.get("driver_id", "")),
                        "name": str(assignment.get("driver_name", "")),
                    },
                    **({"loading_batch_id": assignment["loading_batch_id"]} if assignment.get("loading_batch_id") else {}),
                )
            result = driver_orders.complete_store(
                driver_orders.sidecar_path(assignment["assignment_id"]),
                store_id,
                measurements,
                operation_id,
                payload.get("base_revision", -1),
                photo,
                legacy_quantities=legacy_quantities,
            )
    except (OrderRecordNotFound, DriverOrderNotFound) as not_found:
        return JSONResponse({"ok": False, "error": str(not_found)}, status_code=404)
    except (OrderRecordConflict, DriverOrderConflict) as conflict:
        return JSONResponse({"ok": False, "error": str(conflict)}, status_code=409)
    except (OrderRecordError, DriverOrderError) as invalid:
        return JSONResponse({"ok": False, "error": str(invalid)}, status_code=400)
    return JSONResponse({"ok": True, "assignment": _public_driver_assignment(result)})

def _owned_trip(session: dict, trip_id: str) -> dict:
    trip = vehicle_trips.load_trip(trip_id)
    if session.get("kind") == "loader":
        if trip["vehicle_id"] != str(session.get("vehicle_id", "")):
            raise vehicle_trips.TripNotFound("Рейс не найден")
    elif trip["driver_id"] != str(session["driver_id"]):
        raise vehicle_trips.TripNotFound("Рейс не найден")
    return trip

def _trip_actor(session: dict, trip: dict) -> dict:
    if session.get("kind") == "loader":
        loader = loader_by_id(session["loader_id"])
        return {"kind": "loader", "id": session["loader_id"], "name": loader.get("name", "") if loader else "",
                "vehicle_id": session["vehicle_id"]}
    return {"kind": "driver", "id": session["driver_id"], "name": trip["driver_name"]}

async def driver_trip_detail(request: Request):
    session, error = _session(request)
    if error:
        return error
    try:
        trip = _owned_trip(session, request.path_params["trip_id"])
        return JSONResponse({"ok": True, "assignment": vehicle_trips.as_assignment(trip)})
    except vehicle_trips.TripNotFound as missing:
        return JSONResponse({"ok": False, "error": str(missing)}, status_code=404)

async def driver_trip_complete(request: Request):
    session, error = _session(request, mutate=True)
    if error:
        return error
    try:
        trip = _owned_trip(session, request.path_params["trip_id"])
        mileage_error = _mileage_required_response(session, vehicle_trips.as_assignment(trip))
        if mileage_error:
            return mileage_error
        payload = await _json_payload(request)
        if payload is None or payload.get("trip_id") != trip["id"] or payload.get("assignment_id") != trip["id"]:
            raise vehicle_trips.TripConflict("Операция относится к другому рейсу")
        trip = vehicle_trips.complete_stop(trip["id"], request.path_params["stop_id"], payload, _trip_actor(session, trip))
        return JSONResponse({"ok": True, "assignment": vehicle_trips.as_assignment(trip)})
    except vehicle_trips.TripNotFound as missing:
        return JSONResponse({"ok": False, "error": str(missing)}, status_code=404)
    except vehicle_trips.TripConflict as conflict:
        return JSONResponse({"ok": False, "error": str(conflict)}, status_code=409)
    except (vehicle_trips.TripError, OrderRecordError) as invalid:
        return JSONResponse({"ok": False, "error": str(invalid)}, status_code=400)

async def driver_trip_return(request: Request):
    session, error = _session(request, mutate=request.method == "POST")
    if error:
        return error
    try:
        trip = _owned_trip(session, request.path_params["trip_id"])
        if request.method == "GET":
            result = {"ok": True, "context": vehicle_trips.return_context(trip)}
        else:
            payload = await _json_payload(request)
            if payload is None:
                raise vehicle_trips.TripError("Некорректный запрос")
            document = vehicle_trips.submit_return(trip["id"], payload, _trip_actor(session, trip))
            result = {"ok": True, "document": document}
        return JSONResponse(result, headers={"Cache-Control": "no-store"})
    except vehicle_trips.TripNotFound as missing:
        return JSONResponse({"ok": False, "error": str(missing)}, status_code=404)
    except vehicle_trips.TripConflict as conflict:
        return JSONResponse({"ok": False, "error": str(conflict)}, status_code=409)
    except (vehicle_trips.TripError, goods_returns.GoodsReturnError, OrderRecordError) as invalid:
        return JSONResponse({"ok": False, "error": str(invalid)}, status_code=400)

async def driver_trip_operate(request: Request):
    session, error = _session(request, mutate=True)
    if error:
        return error
    try:
        trip = _owned_trip(session, request.path_params["trip_id"])
        payload = await _json_payload(request)
        if payload is None or payload.get("trip_id") != trip["id"]:
            raise vehicle_trips.TripError("Операция относится к другому рейсу")
        revision = payload.get("revision")
        if type(revision) is not int or revision < 0:
            raise vehicle_trips.TripError("Укажите версию рейса")
        operation_id = payload.get("operation_id")
        actor = _trip_actor(session, trip)
        action = request.path_params["action"]
        if action == "resume":
            mileage_error = _mileage_required_response(session, vehicle_trips.as_assignment(trip))
            if mileage_error:
                return mileage_error
        if action == "arrive":
            trip = vehicle_trips.arrive_at_base(trip["id"], revision, actor, operation_id)
        elif action == "check":
            trip = vehicle_trips.check_before_departure(trip["id"], revision, payload.get("amounts"), actor, operation_id)
        elif action == "resume":
            trip = vehicle_trips.resume_trip(trip["id"], revision, actor, operation_id)
        elif action == "unload-all":
            trip = vehicle_trips.unload_all(trip["id"], revision, payload.get("occurred_at"), payload.get("note", ""), actor, operation_id)
        else:
            return JSONResponse({"ok": False, "error": "Неизвестное действие"}, status_code=404)
        return JSONResponse({"ok": True, "assignment": vehicle_trips.as_assignment(trip)})
    except vehicle_trips.TripNotFound as missing:
        return JSONResponse({"ok": False, "error": str(missing)}, status_code=404)
    except vehicle_trips.TripConflict as conflict:
        return JSONResponse({"ok": False, "error": str(conflict)}, status_code=409)
    except (vehicle_trips.TripError, OrderRecordError) as invalid:
        return JSONResponse({"ok": False, "error": str(invalid)}, status_code=400)

async def driver_sync(request: Request):
    session, error = _session(request, mutate=True)
    if error:
        return error
    assignment = _assignment_for_session(session)
    if assignment and assignment.get("trip_id"):
        vehicle_trips.repair_projections(assignment["trip_id"])
        assignment = vehicle_trips.as_assignment(vehicle_trips.load_trip(assignment["trip_id"]))
        if assignment["projection_error"]:
            return JSONResponse({"ok": False, "error": assignment["projection_error"]}, status_code=409)
    mileage_error = _mileage_required_response(session, assignment)
    if mileage_error:
        return mileage_error
    return JSONResponse({
        "ok": True,
        "assignment": _public_driver_assignment(assignment),
        "mileage": _mileage_status(session, assignment),
    })

async def gps_ping(request: Request):
    session, error = _session(request, mutate=True)
    if error:
        return error
    payload = await _json_payload(request)
    if payload is None:
        return JSONResponse({"ok": False, "error": "Некорректный запрос"}, status_code=400)
    assignment = _assignment_for_session(session)
    vehicle = assignment.get("route_key") if assignment else ""
    if not driver_data.is_valid_vehicle(vehicle):
        return JSONResponse({"ok": False, "error": "Активное назначение не найдено"}, status_code=409)
    try:
        lat = float(payload.get("lat"))
        lon = float(payload.get("lon"))
        speed = payload.get("speed")
        speed = float(speed) if speed is not None else None
    except (TypeError, ValueError):
        return JSONResponse({"ok": False, "error": "Некорректные координаты"}, status_code=400)
    if not -90 <= lat <= 90 or not -180 <= lon <= 180:
        return JSONResponse({"ok": False, "error": "Некорректные координаты"}, status_code=400)
    driver_data.append_gps(vehicle, lat, lon, speed)
    return JSONResponse({"ok": True})
