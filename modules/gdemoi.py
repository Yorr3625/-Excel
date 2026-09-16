"""Клиент GPS-трекеров ГдеМои (платформа Navixy) и привязка к маршрутам.

Ключ API хранится локально в config/gdemoi.json, который исключён из Git.
Трекер привязывается не к маршруту, а к карточке транспорта в справочнике
«Водители и транспорт» (modules/fleet.py, поле ``tracker_id``): на какой
маршрут в данный день назначена эта машина — берём из последней записи
назначений рейсов (modules/fleet.record_order_route_assignments).
"""

import json
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from modules import paths

GDEMOI_FILE = paths.GDEMOI_FILE
ORDER_ROUTE_ASSIGNMENTS_FILE = paths.ORDER_ROUTE_ASSIGNMENTS_FILE

API_BASE = "https://api.gdemoi.ru/v2"
REQUEST_TIMEOUT_SECONDS = 10

ERROR_MESSAGES = {
    3: "ГдеМои отклонил ключ API",
    4: "Сессия ГдеМои истекла или не существует",
    201: "Трекер с таким ID не найден на аккаунте",
    208: "Трекер заблокирован — проверьте тариф в личном кабинете ГдеМои",
}


class GdemoiError(Exception):
    """Ошибка обращения к API ГдеМои."""


def load_settings() -> dict:
    try:
        data = json.loads(GDEMOI_FILE.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {"api_key": ""}

    if not isinstance(data, dict):
        return {"api_key": ""}

    return {"api_key": str(data.get("api_key") or "")}


def save_settings(api_key: str) -> dict:
    """Пустой ключ при сохранении не стирает уже сохранённый — как пароль почты."""

    current = load_settings()
    settings = {"api_key": api_key.strip() or current["api_key"]}

    GDEMOI_FILE.parent.mkdir(parents=True, exist_ok=True)
    GDEMOI_FILE.write_text(json.dumps(settings, ensure_ascii=False, indent=2), encoding="utf-8")

    return settings


def is_configured(settings: dict | None = None) -> bool:
    settings = settings if settings is not None else load_settings()
    return bool(settings.get("api_key", "").strip())


def _request(path: str, payload: dict, api_key: str) -> dict:
    body = json.dumps(payload).encode("utf-8")
    request = Request(
        f"{API_BASE}{path}",
        data=body,
        headers={
            "Content-Type": "application/json",
            "Authorization": f"NVX {api_key.strip()}",
        },
        method="POST",
    )

    try:
        with urlopen(request, timeout=REQUEST_TIMEOUT_SECONDS) as response:
            data = json.loads(response.read().decode("utf-8"))
    except HTTPError as error:
        try:
            data = json.loads(error.read().decode("utf-8"))
            code = data.get("status", {}).get("code")
        except (ValueError, json.JSONDecodeError, AttributeError):
            code = None
        raise GdemoiError(ERROR_MESSAGES.get(code, f"ГдеМои вернул ошибку {error.code}")) from error
    except (URLError, TimeoutError, OSError) as error:
        raise GdemoiError("Не удалось обратиться к ГдеМои. Проверьте интернет и повторите") from error
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise GdemoiError("ГдеМои вернул некорректный ответ") from error

    if not data.get("success"):
        code = data.get("status", {}).get("code")
        raise GdemoiError(ERROR_MESSAGES.get(code, "ГдеМои сообщил об ошибке"))

    return data


def list_trackers(api_key: str) -> list[dict]:
    """Трекеры на аккаунте: [{"id", "label", "model", "blocked"}, ...]."""

    data = _request("/tracker/list", {}, api_key)
    result = []
    for item in data.get("list", []):
        source = item.get("source") or {}
        result.append({
            "id": item.get("id"),
            "label": item.get("label", ""),
            "model": source.get("model", ""),
            "blocked": bool(source.get("blocked")),
        })

    return result


def get_states(api_key: str, tracker_ids: list[int]) -> dict[int, dict]:
    """Текущее состояние трекеров -> {tracker_id: {"lat","lng","speed","updated","online"}}.

    Заблокированные и несуществующие ID не валят весь запрос — просто не
    попадают в результат.
    """

    if not tracker_ids:
        return {}

    data = _request(
        "/tracker/get_states",
        {"trackers": tracker_ids, "list_blocked": True, "allow_not_exist": True},
        api_key,
    )

    states = {}
    for tracker_id, state in (data.get("states") or {}).items():
        gps = state.get("gps") or {}
        location = gps.get("location") or {}
        if location.get("lat") is None or location.get("lng") is None:
            continue
        states[int(tracker_id)] = {
            "lat": location.get("lat"),
            "lng": location.get("lng"),
            "speed": gps.get("speed"),
            "updated": gps.get("updated"),
            "online": state.get("connection_status") == "active",
        }

    return states


def latest_vehicle_route_map() -> dict[str, str]:
    """vehicle_id -> route_key ("route_1"...) по последней записи назначений рейсов."""

    try:
        data = json.loads(ORDER_ROUTE_ASSIGNMENTS_FILE.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}

    items = data.get("items") if isinstance(data, dict) else None
    if not items:
        return {}

    latest = items[-1]
    return {
        route["vehicle_id"]: route["route"]
        for route in latest.get("routes", [])
        if route.get("vehicle_id") and route.get("route")
    }


def poll_and_record() -> list[str]:
    """Опрашивает трекеры привязанных машин и пишет координаты в driver_data.

    Возвращает список маршрутов (route_key), для которых удалось записать
    свежую позицию. Требует настроенного API-ключа и хотя бы одной карточки
    транспорта с заполненным tracker_id.
    """

    from modules import driver_data, fleet

    settings = load_settings()
    if not is_configured(settings):
        return []

    vehicles = [
        item for item in fleet.load_fleet()["vehicles"]
        if str(item.get("tracker_id") or "").strip()
    ]
    if not vehicles:
        return []

    route_by_vehicle = latest_vehicle_route_map()
    tracker_by_vehicle = {}
    tracker_ids = []
    for vehicle in vehicles:
        route_key = route_by_vehicle.get(vehicle["id"])
        if not route_key:
            continue
        try:
            tracker_id = int(str(vehicle["tracker_id"]).strip())
        except ValueError:
            continue
        tracker_by_vehicle[tracker_id] = route_key
        tracker_ids.append(tracker_id)

    if not tracker_ids:
        return []

    states = get_states(settings["api_key"], tracker_ids)

    updated_routes = []
    for tracker_id, route_key in tracker_by_vehicle.items():
        state = states.get(tracker_id)
        if state is None:
            continue
        driver_data.append_gps(route_key, state["lat"], state["lng"], state["speed"])
        updated_routes.append(route_key)

    return updated_routes
