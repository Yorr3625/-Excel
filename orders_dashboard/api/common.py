"""Shared HTTP authentication and assignment helpers."""
from http.cookies import (
    CookieError,
    SimpleCookie,
)
from modules.driver_mileage import DriverMileageError
from modules.excel_io import EXCEL_MIME_TYPES
from starlette.responses import JSONResponse
from modules.order_records import (
    OrderRecordError,
    OrderRecordNotFound,
    load_order_record,
    loading_batch_destinations,
    loading_batches,
    logistics_summary,
    route_loading_ready,
)
from pathlib import Path
from starlette.requests import Request
from modules.fleet import (
    active_vehicles,
    driver_by_id,
    employee_role,
    loader_by_id,
)
from modules import (
    dashboard_sessions,
    driver_mileage,
    driver_orders,
    driver_sessions,
    goods_returns,
    loader_sessions,
    vehicle_trips,
)
import json


def _admin_token(cookie_header: str) -> str | None:
    try:
        cookies = SimpleCookie()
        cookies.load(cookie_header or "")
    except CookieError:
        return None
    cookie = cookies.get(dashboard_sessions.SESSION_COOKIE)
    return cookie.value if cookie else None

def _admin_session_for_router(router) -> bool:
    headers = getattr(router, "headers", None)
    if headers is None and isinstance(router, dict):
        headers = router.get("headers", {})
    if isinstance(headers, dict):
        cookie_header = headers.get("cookie", "")
    else:
        cookie_header = getattr(headers, "cookie", "")
    return dashboard_sessions.valid_session(_admin_token(cookie_header))

def _router_query_param(router, name: str) -> str:
    url = getattr(router, "url", None)
    params = getattr(url, "query_parameters", None)
    if params is None and isinstance(router, dict):
        url = router.get("url", {})
        params = url.get("query_parameters") if isinstance(url, dict) else None
        params = params if params is not None else router.get("params", {})
    if not hasattr(params, "get"):
        return ""
    value = params.get(name, "")
    return str(value[0] if isinstance(value, list) and value else value)

async def _json_payload(request: Request) -> dict | None:
    try:
        payload = await request.json()
    except (ValueError, json.JSONDecodeError):
        return None
    return payload if isinstance(payload, dict) else None

def _session(request: Request, mutate: bool = False):
    if request.url.path.startswith("/api/crew/"):
        session, error = _loader_session(request, mutate=mutate)
        if error:
            return None, error
        vehicle_id = str(session.get("vehicle_id", ""))
        if vehicle_id not in {item["id"] for item in _loader_available_vehicles()}:
            return None, JSONResponse({"ok": False, "error": "Сначала выберите машину в кабинете грузчика"}, status_code=409)
        if request.headers.get("x-driver-cache-key") not in (None, session["loader_id"]):
            return None, JSONResponse({"ok": False, "error": "Недействительный запрос"}, status_code=403)
        return {**session, "kind": "loader", "driver_id": session["loader_id"]}, None
    token = request.cookies.get(driver_sessions.SESSION_COOKIE)
    session = driver_sessions.get_session(token)
    if session is None:
        return None, JSONResponse({"ok": False, "error": "Требуется вход"}, status_code=401)
    driver = driver_by_id(str(session.get("driver_id", "")))
    if driver is None or not driver.get("active") or employee_role(driver) != "driver":
        driver_sessions.destroy_session(token)
        return None, JSONResponse({"ok": False, "error": "Профиль недоступен"}, status_code=401)
    cache_key = request.headers.get("x-driver-cache-key")
    if cache_key and cache_key != session["driver_id"]:
        return None, JSONResponse({"ok": False, "error": "Недействительный запрос"}, status_code=403)
    if mutate and not driver_sessions.valid_csrf(
        session, request.headers.get("x-driver-csrf")
    ):
        return None, JSONResponse({"ok": False, "error": "Недействительный запрос"}, status_code=403)
    return session, None

def _set_driver_cookie(response: JSONResponse, request: Request, token: str) -> None:
    response.set_cookie(
        driver_sessions.SESSION_COOKIE,
        token,
        max_age=driver_sessions.SESSION_TTL_SECONDS,
        httponly=True,
        secure=request.url.scheme == "https",
        samesite="strict",
        path="/",
    )

def _loader_session(request: Request, mutate: bool = False):
    token = request.cookies.get(loader_sessions.SESSION_COOKIE)
    session = loader_sessions.get_session(token)
    if session is None or session.get("role") != "loader":
        return None, JSONResponse({"ok": False, "error": "Требуется вход"}, status_code=401)
    loader = loader_by_id(str(session.get("loader_id", "")))
    if loader is None or not loader.get("active"):
        loader_sessions.destroy_session(token)
        return None, JSONResponse({"ok": False, "error": "Профиль недоступен"}, status_code=401)
    if mutate and not loader_sessions.valid_csrf(session, request.headers.get("x-loader-csrf")):
        return None, JSONResponse({"ok": False, "error": "Недействительный запрос"}, status_code=403)
    return session, None

def _loader_available_vehicles() -> list[dict]:
    active = {str(vehicle.get("id", "")): vehicle for vehicle in active_vehicles()}
    return [
        {
            "id": vehicle_id,
            "name": str(snapshot.get("name") or active[vehicle_id].get("name", "")),
            "plate": str(snapshot.get("plate") or active[vehicle_id].get("plate", "")),
        }
        for snapshot in driver_orders.assigned_vehicles()
        if (vehicle_id := str(snapshot.get("id", ""))) in active
    ]

def _set_loader_cookie(response: JSONResponse, request: Request, token: str) -> None:
    response.set_cookie(
        loader_sessions.SESSION_COOKIE,
        token,
        max_age=loader_sessions.SESSION_TTL_SECONDS,
        httponly=True,
        secure=(
            request.url.scheme == "https"
            or request.headers.get("x-forwarded-proto") == "https"
        ),
        samesite="strict",
        path="/",
    )

def _assignment_for_session(session: dict) -> dict | None:
    if session.get("kind") == "loader":
        trip = vehicle_trips.active_for_vehicle(str(session.get("vehicle_id", "")))
        return vehicle_trips.as_assignment(trip) if trip else None
    driver_id = str(session.get("driver_id", ""))
    trip = vehicle_trips.active_for_driver(driver_id)
    if trip:
        return vehicle_trips.as_assignment(trip)
    selected_vehicle = session.get("vehicle_id", "")
    if selected_vehicle:
        candidates = [item for item in driver_orders.assignments_for_vehicle(selected_vehicle) if item.get("driver_id") == driver_id]
        assignment = max(candidates, key=lambda item: item.get("created_at", ""), default=None)
    else:
        assignment = driver_orders.find_assignment_for_driver(driver_id)
    linked = vehicle_trips.trip_for_assignment(assignment["assignment_id"]) if assignment else None
    if linked:
        return vehicle_trips.as_assignment(linked) if linked["status"] in {"draft", "active", "on_base", "return_pending"} else None
    return assignment

def _public_driver_assignment(assignment: dict | None) -> dict | None:
    if assignment is None:
        return None
    if assignment.get("trip_id"):
        return assignment
    payload = driver_orders.public_snapshot(assignment)
    try:
        payload["return_context"] = goods_returns.return_context(assignment)
    except (goods_returns.GoodsReturnError, OrderRecordError) as error:
        payload["return_context"] = {"eligible": False, "complete": False, "lines": [], "error": str(error)}
    record_id = str(assignment.get("order_record_id", ""))
    if not record_id:
        payload["loading_status"] = "legacy_unlinked"
        payload["shipment_status"] = "legacy_unlinked"
        return payload
    try:
        record = load_order_record(record_id)
        summary = logistics_summary(record)
    except (OrderRecordError, OrderRecordNotFound):
        payload["loading_status"] = "record_unavailable"
        payload["shipment_status"] = "record_unavailable"
        return payload
    route_key = str(assignment.get("route_key", ""))
    batch_id = str(assignment.get("loading_batch_id", ""))
    try:
        if batch_id:
            destinations = loading_batch_destinations(record, route_key, batch_id)
            route_ready = {store.get("order_record_destination_id") for store in assignment["stores"]} == {item["id"] for item in destinations}
            batches = loading_batches(record, route_key)
            released = {identity for batch in batches for identity in batch["destination_ids"]}
            route = next((item for item in record["routes"] if item["route_key"] == route_key), {})
            payload["waiting_store_count"] = sum(item["id"] not in released for item in route.get("destinations", []))
            payload["loading_status"] = "partial" if route_ready else "waiting_loading"
        else:
            route_ready = route_loading_ready(record, route_key) and not loading_batches(record, route_key)
            payload["loading_status"] = "loaded" if route_ready else "waiting_loading"
    except OrderRecordError:
        payload["loading_status"] = "record_unavailable"
    payload["shipment_status"] = summary["shipment_status"]
    return payload

def _mileage_status(session: dict, assignment: dict | None = None) -> dict:
    if session.get("kind") == "loader":
        return {"required": False, "available": False, "reason": "loader"}
    assignment = assignment if assignment is not None else _assignment_for_session(session)
    if assignment is None:
        return {"required": False, "available": False, "reason": "assignment_missing"}

    vehicle_id = str(assignment.get("vehicle_id", "")).strip()
    if not vehicle_id:
        return {
            "required": True,
            "available": False,
            "error": "В активном назначении не указан автомобиль",
        }

    day = driver_mileage.today_key()
    try:
        record = driver_mileage.get_record(str(session.get("driver_id", "")), vehicle_id, day)
    except DriverMileageError as error:
        return {"required": True, "available": False, "error": str(error)}
    return {
        "required": record is None,
        "available": True,
        "date": day,
        "assignment_id": str(assignment.get("assignment_id", "")),
        "vehicle": {
            "id": vehicle_id,
            "name": str(assignment.get("vehicle_name", "")),
            "plate": str(assignment.get("vehicle_plate", "")),
        },
        "record": record,
    }

def _mileage_required_response(session: dict, assignment: dict | None = None) -> JSONResponse | None:
    status = _mileage_status(session, assignment)
    if not status["required"]:
        return None
    return JSONResponse(
        {
            "ok": False,
            "error": status.get("error") or "Перед работой укажите пробег автомобиля",
            "mileage": status,
        },
        status_code=409,
    )

def _dashboard_download_authorized(request: Request) -> bool:
    return dashboard_sessions.valid_session(
        request.cookies.get(dashboard_sessions.SESSION_COOKIE)
    )

def _excel_media_type(path: Path) -> str:
    suffix = path.suffix.casefold()
    return next(
        (
            media_type
            for media_type, suffixes in EXCEL_MIME_TYPES.items()
            if suffix in suffixes
        ),
        "application/octet-stream",
    )
