"""Локальный справочник водителей, транспорта и назначений заказов."""

import json
import re
import uuid
from datetime import datetime
from pathlib import Path

from modules import paths

FLEET_FILE = paths.FLEET_FILE
ORDER_ROUTE_ASSIGNMENTS_FILE = paths.ORDER_ROUTE_ASSIGNMENTS_FILE
DRIVER_PHOTOS_FOLDER = paths.DRIVER_PHOTOS_FOLDER
DRIVER_DOCUMENTS_FOLDER = paths.DRIVER_DOCUMENTS_FOLDER

MAX_FILE_SIZE = 10 * 1024 * 1024
IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".webp"}
DOCUMENT_EXTENSIONS = {".pdf", ".jpg", ".jpeg", ".png"}
DOCUMENT_TYPES = {"Права", "Медсправка", "Другое"}


class FleetError(ValueError):
    """Некорректные данные справочника."""


def _empty_fleet() -> dict:
    return {"version": 1, "drivers": [], "vehicles": []}


def _read_json(path: Path, fallback: dict) -> dict:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return fallback

    return data if isinstance(data, dict) else fallback


def _write_json(path: Path, data: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def load_fleet() -> dict:
    data = _read_json(FLEET_FILE, _empty_fleet())
    drivers = data.get("drivers")
    vehicles = data.get("vehicles")
    if not isinstance(drivers, list) or not isinstance(vehicles, list):
        return _empty_fleet()

    return {"version": 1, "drivers": drivers, "vehicles": vehicles}


def save_fleet(data: dict) -> None:
    drivers = data.get("drivers")
    vehicles = data.get("vehicles")
    if not isinstance(drivers, list) or not isinstance(vehicles, list):
        raise FleetError("Некорректные данные справочника")

    _write_json(FLEET_FILE, {"version": 1, "drivers": drivers, "vehicles": vehicles})


def normalize_plate(value: str) -> str:
    return re.sub(r"\s+", "", value.strip().upper())


def _text(value: str) -> str:
    return str(value or "").strip()


def _vehicle_payload(
    name: str,
    plate: str,
    odometer_km: str | int | float,
    description: str,
    notes: str,
    active: bool,
    tracker_id: str = "",
) -> dict:
    name = _text(name)
    plate = normalize_plate(plate)
    if not name:
        raise FleetError("Укажите название транспорта")
    if not plate:
        raise FleetError("Укажите госномер")

    try:
        odometer = int(float(str(odometer_km or "0").replace(",", ".")))
    except ValueError as error:
        raise FleetError("Пробег должен быть числом") from error
    if odometer < 0:
        raise FleetError("Пробег не может быть отрицательным")

    return {
        "name": name,
        "plate": plate,
        "odometer_km": odometer,
        "description": _text(description),
        "notes": _text(notes),
        "active": bool(active),
        "tracker_id": _text(tracker_id),
    }


def _assert_unique_plate(vehicles: list[dict], plate: str, current_id: str = "") -> None:
    if any(item.get("id") != current_id and normalize_plate(item.get("plate", "")) == plate for item in vehicles):
        raise FleetError("Транспорт с таким госномером уже есть")


def add_vehicle(
    name: str,
    plate: str,
    odometer_km: str | int | float = 0,
    description: str = "",
    notes: str = "",
    active: bool = True,
    tracker_id: str = "",
) -> dict:
    data = load_fleet()
    vehicle = _vehicle_payload(name, plate, odometer_km, description, notes, active, tracker_id)
    _assert_unique_plate(data["vehicles"], vehicle["plate"])
    vehicle["id"] = str(uuid.uuid4())
    data["vehicles"].append(vehicle)
    save_fleet(data)
    return vehicle


def update_vehicle(
    vehicle_id: str,
    name: str,
    plate: str,
    odometer_km: str | int |float,
    description: str,
    notes: str,
    active: bool,
    tracker_id: str = "",
) -> dict:
    data = load_fleet()
    vehicle = _vehicle_payload(name, plate, odometer_km, description, notes, active, tracker_id)
    _assert_unique_plate(data["vehicles"], vehicle["plate"], vehicle_id)

    for index, item in enumerate(data["vehicles"]):
        if item.get("id") == vehicle_id:
            vehicle["id"] = vehicle_id
            data["vehicles"][index] = vehicle
            save_fleet(data)
            return vehicle

    raise FleetError("Транспорт не найден")


def _driver_payload(
    name: str,
    phone: str,
    rating: str | int | float,
    active: bool,
    hired_on: str,
    notes: str,
    default_vehicle_id: str,
    photo: str = "",
    documents: list[dict] | None = None,
) -> dict:
    name = _text(name)
    if not name:
        raise FleetError("Укажите ФИО водителя")

    try:
        rating_number = int(float(str(rating or "0").replace(",", ".")))
    except ValueError as error:
        raise FleetError("Рейтинг должен быть числом от 1 до 5") from error
    if not 1 <= rating_number <= 5:
        raise FleetError("Рейтинг должен быть от 1 до 5")

    return {
        "name": name,
        "phone": _text(phone),
        "rating": rating_number,
        "active": bool(active),
        "hired_on": _text(hired_on),
        "notes": _text(notes),
        "default_vehicle_id": _text(default_vehicle_id),
        "photo": photo,
        "documents": documents or [],
    }


def _assert_vehicle_exists(vehicles: list[dict], vehicle_id: str) -> None:
    if vehicle_id and not any(item.get("id") == vehicle_id for item in vehicles):
        raise FleetError("Выбранный транспорт не найден")


def add_driver(
    name: str,
    phone: str = "",
    rating: str | int | float = 5,
    active: bool = True,
    hired_on: str = "",
    notes: str = "",
    default_vehicle_id: str = "",
) -> dict:
    data = load_fleet()
    _assert_vehicle_exists(data["vehicles"], default_vehicle_id)
    driver = _driver_payload(name, phone, rating, active, hired_on, notes, default_vehicle_id)
    driver["id"] = str(uuid.uuid4())
    data["drivers"].append(driver)
    save_fleet(data)
    return driver


def update_driver(
    driver_id: str,
    name: str,
    phone: str,
    rating: str | int | float,
    active: bool,
    hired_on: str,
    notes: str,
    default_vehicle_id: str,
) -> dict:
    data = load_fleet()
    _assert_vehicle_exists(data["vehicles"], default_vehicle_id)

    for index, item in enumerate(data["drivers"]):
        if item.get("id") == driver_id:
            driver = _driver_payload(
                name,
                phone,
                rating,
                active,
                hired_on,
                notes,
                default_vehicle_id,
                item.get("photo", ""),
                item.get("documents") if isinstance(item.get("documents"), list) else [],
            )
            driver["id"] = driver_id
            data["drivers"][index] = driver
            save_fleet(data)
            return driver

    raise FleetError("Водитель не найден")


def delete_vehicle(vehicle_id: str) -> None:
    data = load_fleet()
    vehicles = [item for item in data["vehicles"] if item.get("id") != vehicle_id]
    if len(vehicles) == len(data["vehicles"]):
        raise FleetError("Транспорт не найден")

    data["vehicles"] = vehicles
    for driver in data["drivers"]:
        if driver.get("default_vehicle_id") == vehicle_id:
            driver["default_vehicle_id"] = ""
    save_fleet(data)


def delete_driver(driver_id: str) -> None:
    data = load_fleet()
    drivers = [item for item in data["drivers"] if item.get("id") != driver_id]
    if len(drivers) == len(data["drivers"]):
        raise FleetError("Водитель не найден")

    data["drivers"] = drivers
    save_fleet(data)
    for folder in (DRIVER_PHOTOS_FOLDER, DRIVER_DOCUMENTS_FOLDER):
        if folder.exists():
            for path in folder.glob(f"{driver_id}_*"):
                path.unlink()


def active_drivers() -> list[dict]:
    return [item for item in load_fleet()["drivers"] if item.get("active")]


def active_vehicles() -> list[dict]:
    return [item for item in load_fleet()["vehicles"] if item.get("active")]


def _safe_extension(filename: str, allowed: set[str]) -> str:
    suffix = Path(filename).suffix.lower()
    if suffix not in allowed:
        raise FleetError("Неподдерживаемый формат файла")
    return suffix


def _store_file(folder: Path, owner_id: str, filename: str, content: bytes, allowed: set[str]) -> str:
    if len(content) > MAX_FILE_SIZE:
        raise FleetError("Размер файла не должен превышать 10 МБ")
    suffix = _safe_extension(filename, allowed)
    folder.mkdir(parents=True, exist_ok=True)
    stored_name = f"{owner_id}_{uuid.uuid4().hex}{suffix}"
    path = folder / stored_name
    path.write_bytes(content)
    try:
        return path.relative_to(paths.DATA_DIR).as_posix()
    except ValueError as error:
        raise FleetError("Папка файлов должна находиться в data") from error


def store_driver_photo(driver_id: str, filename: str, content: bytes) -> str:
    data = load_fleet()
    for driver in data["drivers"]:
        if driver.get("id") == driver_id:
            driver["photo"] = _store_file(
                DRIVER_PHOTOS_FOLDER, driver_id, filename, content, IMAGE_EXTENSIONS
            )
            save_fleet(data)
            return driver["photo"]

    raise FleetError("Водитель не найден")


def add_driver_document(driver_id: str, document_type: str, filename: str, content: bytes) -> dict:
    if document_type not in DOCUMENT_TYPES:
        raise FleetError("Неизвестный тип документа")

    data = load_fleet()
    for driver in data["drivers"]:
        if driver.get("id") != driver_id:
            continue
        path = _store_file(DRIVER_DOCUMENTS_FOLDER, driver_id, filename, content, DOCUMENT_EXTENSIONS)
        document = {
            "id": str(uuid.uuid4()),
            "type": document_type,
            "name": Path(filename).name,
            "path": path,
            "uploaded_at": datetime.now().isoformat(timespec="seconds"),
        }
        documents = driver.get("documents") if isinstance(driver.get("documents"), list) else []
        driver["documents"] = documents + [document]
        save_fleet(data)
        return document

    raise FleetError("Водитель не найден")


def remove_driver_document(driver_id: str, document_id: str) -> None:
    data = load_fleet()
    for driver in data["drivers"]:
        if driver.get("id") != driver_id:
            continue
        documents = driver.get("documents") if isinstance(driver.get("documents"), list) else []
        removed = next((item for item in documents if item.get("id") == document_id), None)
        if removed is None:
            raise FleetError("Документ не найден")
        driver["documents"] = [item for item in documents if item.get("id") != document_id]
        save_fleet(data)
        path = paths.DATA_DIR / str(removed.get("path", ""))
        if path.parent == DRIVER_DOCUMENTS_FOLDER and path.exists():
            path.unlink()
        return

    raise FleetError("Водитель не найден")


def record_order_route_assignments(
    order_file: str,
    mode: str,
    output_file: str,
    assignments: list[dict],
) -> None:
    data = _read_json(ORDER_ROUTE_ASSIGNMENTS_FILE, {"version": 1, "items": []})
    items = data.get("items") if isinstance(data.get("items"), list) else []
    items.append({
        "order_file": _text(order_file),
        "mode": _text(mode),
        "output_file": _text(output_file),
        "created_at": datetime.now().isoformat(timespec="seconds"),
        "routes": assignments,
    })
    _write_json(ORDER_ROUTE_ASSIGNMENTS_FILE, {"version": 1, "items": items})
