import json
from datetime import datetime
from pathlib import Path

from modules.config import load_stores
from modules.paths import TRACKING_FOLDER as DATA_DIR

TRAIL_LIMIT = 100

# Машина = маршрут; других ключей быть не может. Список нужен как белый
# список: vehicle_key приходит в том числе из тела HTTP-запроса
# (/api/gps-ping), а дальше подставляется в имя файла — без проверки
# значение вида "../../config/stores_city" уводило запись за пределы
# папки с данными.
ALLOWED_VEHICLE_KEYS = ("route_1", "route_2", "route_3", "route_4")


def is_valid_vehicle(vehicle_key: str) -> bool:
    return vehicle_key in ALLOWED_VEHICLE_KEYS


def today_key() -> str:
    return datetime.now().strftime("%Y-%m-%d")


def _file_path(vehicle_key: str, day: str | None = None) -> Path:
    if not is_valid_vehicle(vehicle_key):
        raise ValueError(f"Неизвестная машина: {vehicle_key!r}")

    return DATA_DIR / f"{day or today_key()}_{vehicle_key}.json"


def _read(path: Path) -> dict | None:
    if not path.exists():
        return None

    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None


def _write(path: Path, data: dict) -> None:
    DATA_DIR.mkdir(exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def load_or_init_day(vehicle_key: str, stores_file: str) -> dict:
    path = _file_path(vehicle_key)
    data = _read(path)

    if data is not None:
        return data

    try:
        stores = load_stores(stores_file)
    except (OSError, json.JSONDecodeError):
        stores = {}

    stop_names = stores.get(vehicle_key, [])
    data = {
        "vehicle_key": vehicle_key,
        "day": today_key(),
        "stops": [
            {"name": name, "status": "pending", "photo": "", "done_at": ""}
            for name in stop_names
        ],
        "last_position": None,
        "trail": [],
    }
    _write(path, data)

    return data


def save_day(vehicle_key: str, data: dict) -> None:
    _write(_file_path(vehicle_key), data)


def mark_stop_done(vehicle_key: str, stores_file: str, stop_name: str, photo_rel_path: str) -> dict:
    data = load_or_init_day(vehicle_key, stores_file)

    for stop in data["stops"]:
        if stop["name"] == stop_name:
            stop["status"] = "done"
            stop["photo"] = photo_rel_path
            stop["done_at"] = datetime.now().strftime("%H:%M:%S")
            break

    save_day(vehicle_key, data)

    return data


def append_gps(vehicle_key: str, lat, lon, speed) -> None:
    if not is_valid_vehicle(vehicle_key) or lat is None or lon is None:
        return

    path = _file_path(vehicle_key)
    data = _read(path) or {
        "vehicle_key": vehicle_key,
        "day": today_key(),
        "stops": [],
        "last_position": None,
        "trail": [],
    }

    point = {
        "lat": lat,
        "lon": lon,
        "speed": speed,
        "ts": datetime.now().strftime("%H:%M:%S"),
    }

    data["last_position"] = point
    data["trail"] = (data.get("trail") or [])[-(TRAIL_LIMIT - 1):] + [point]

    _write(path, data)


def load_today(vehicle_key: str) -> dict | None:
    return _read(_file_path(vehicle_key))
