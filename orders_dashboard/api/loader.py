"""Loader authentication and vehicle selection endpoints."""
from starlette.responses import JSONResponse
from starlette.requests import Request
from orders_dashboard.api.common import (
    _json_payload,
    _loader_session,
    _set_loader_cookie,
)
from orders_dashboard.api import common
from modules import (
    driver_orders,
    loader_sessions,
)
from modules.fleet import (
    loader_by_id,
    loader_by_login,
    verify_loader_pin,
)


async def loader_login(request: Request):
    payload = await _json_payload(request)
    if payload is None:
        return JSONResponse({"ok": False, "error": "Некорректный запрос"}, status_code=400)
    login = str(payload.get("loader_id", payload.get("login", ""))).strip()
    pin = str(payload.get("pin", "")).strip()
    loader = loader_by_login(login) or loader_by_id(login)
    loader_id = str(loader.get("id", "")) if loader else ""
    if not loader_id or not verify_loader_pin(loader_id, pin):
        return JSONResponse({"ok": False, "error": "Неверный идентификатор или PIN"}, status_code=401)

    previous = request.cookies.get(loader_sessions.SESSION_COOKIE)
    loader_sessions.destroy_session(previous)
    token, session = loader_sessions.create_session(loader_id)
    response = JSONResponse({
        "ok": True,
        "loader": {"id": loader_id, "name": loader.get("name", "")},
        "csrf_token": session["csrf_token"],
    }, headers={"Cache-Control": "no-store"})
    _set_loader_cookie(response, request, token)
    return response

async def loader_logout(request: Request):
    session, error = _loader_session(request, mutate=True)
    if error:
        if error.status_code == 401:
            error.delete_cookie(loader_sessions.SESSION_COOKIE, path="/")
        return error
    loader_sessions.destroy_session(request.cookies.get(loader_sessions.SESSION_COOKIE))
    response = JSONResponse({"ok": True}, headers={"Cache-Control": "no-store"})
    response.delete_cookie(loader_sessions.SESSION_COOKIE, path="/")
    return response

async def loader_me(request: Request):
    session, error = _loader_session(request)
    if error:
        return error
    loader = loader_by_id(str(session.get("loader_id", "")))
    return JSONResponse({
        "ok": True,
        "loader": {"id": loader.get("id", ""), "name": loader.get("name", "")},
        "csrf_token": session["csrf_token"],
        "vehicle_id": session.get("vehicle_id", ""),
    }, headers={"Cache-Control": "no-store"})

async def loader_vehicles(request: Request):
    _session, error = _loader_session(request)
    if error:
        return error
    return JSONResponse({"ok": True, "vehicles": common._loader_available_vehicles()}, headers={"Cache-Control": "no-store"})

async def loader_select_vehicle(request: Request):
    session, error = _loader_session(request, mutate=True)
    if error:
        return error
    payload = await _json_payload(request)
    if payload is None:
        return JSONResponse({"ok": False, "error": "Некорректный запрос"}, status_code=400)
    vehicle_id = str(payload.get("vehicle_id", "")).strip()
    if vehicle_id not in {vehicle["id"] for vehicle in common._loader_available_vehicles()}:
        return JSONResponse({"ok": False, "error": "Автомобиль недоступен"}, status_code=404)
    loader_sessions.select_vehicle(request.cookies.get(loader_sessions.SESSION_COOKIE), vehicle_id)
    return JSONResponse({"ok": True, "vehicle_id": vehicle_id}, headers={"Cache-Control": "no-store"})

async def loader_orders(request: Request):
    session, error = _loader_session(request)
    if error:
        return error
    vehicle_id = str(session.get("vehicle_id", ""))
    if vehicle_id not in {vehicle["id"] for vehicle in common._loader_available_vehicles()}:
        return JSONResponse({"ok": True, "vehicle_id": "", "assignments": []}, headers={"Cache-Control": "no-store"})
    return JSONResponse({
        "ok": True,
        "vehicle_id": vehicle_id,
        "assignments": driver_orders.public_assignments_for_vehicle(vehicle_id),
    }, headers={"Cache-Control": "no-store"})
