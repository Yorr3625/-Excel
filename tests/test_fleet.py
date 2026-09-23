import json

import pytest

from modules import fleet, paths


@pytest.fixture(autouse=True)
def isolated_fleet_files(tmp_path, monkeypatch):
    config_dir = tmp_path / "config"
    data_dir = tmp_path / "data"
    fleet_file = config_dir / "fleet.json"
    assignments_file = data_dir / "order_route_assignments.json"
    photos_folder = data_dir / "driver_photos"
    documents_folder = data_dir / "driver_documents"

    monkeypatch.setattr(paths, "DATA_DIR", data_dir)
    monkeypatch.setattr(paths, "FLEET_FILE", fleet_file)
    monkeypatch.setattr(paths, "ORDER_ROUTE_ASSIGNMENTS_FILE", assignments_file)
    monkeypatch.setattr(paths, "DRIVER_PHOTOS_FOLDER", photos_folder)
    monkeypatch.setattr(paths, "DRIVER_DOCUMENTS_FOLDER", documents_folder)
    monkeypatch.setattr(fleet, "FLEET_FILE", fleet_file)
    monkeypatch.setattr(fleet, "ORDER_ROUTE_ASSIGNMENTS_FILE", assignments_file)
    monkeypatch.setattr(fleet, "DRIVER_PHOTOS_FOLDER", photos_folder)
    monkeypatch.setattr(fleet, "DRIVER_DOCUMENTS_FOLDER", documents_folder)


def test_load_fleet_returns_empty_data_when_file_is_missing_or_broken():
    assert fleet.load_fleet() == {"version": 1, "drivers": [], "vehicles": []}

    fleet.FLEET_FILE.parent.mkdir()
    fleet.FLEET_FILE.write_text("{not json", encoding="utf-8")

    assert fleet.load_fleet() == {"version": 1, "drivers": [], "vehicles": []}


def test_add_vehicle_normalizes_plate_and_persists_data():
    vehicle = fleet.add_vehicle(" Газель Next ", " а123 вс 71 ", "145000", "Фургон", "ТО в октябре")

    assert vehicle["name"] == "Газель Next"
    assert vehicle["plate"] == "А123ВС71"
    assert vehicle["odometer_km"] == 145000
    assert fleet.load_fleet()["vehicles"] == [vehicle]


def test_vehicle_plate_must_be_unique_and_odometer_non_negative():
    fleet.add_vehicle("Газель", "А123ВС71")

    with pytest.raises(fleet.FleetError, match="госномером"):
        fleet.add_vehicle("Вторая", "а123 вс71")

    with pytest.raises(fleet.FleetError, match="отрицательным"):
        fleet.add_vehicle("Вторая", "В222ВВ71", -1)


def test_update_vehicle_keeps_its_own_normalized_plate():
    vehicle = fleet.add_vehicle("Газель", "А123ВС71")

    updated = fleet.update_vehicle(vehicle["id"], "Новая Газель", "а123 вс 71", 40, "", "", False)

    assert updated["plate"] == "А123ВС71"
    assert updated["active"] is False
    assert fleet.active_vehicles() == []


def test_driver_can_reference_existing_vehicle_and_preserves_fields_on_update():
    vehicle = fleet.add_vehicle("Газель", "А123ВС71")
    driver = fleet.add_driver("Иван Иванов", "+7 900 000-00-00", 4, True, "2026-09-07", "", vehicle["id"])

    updated = fleet.update_driver(driver["id"], "Иван И.", "+7 900 000-00-01", 5, False, "2026-09-07", "отпуск", vehicle["id"])

    assert updated["name"] == "Иван И."
    assert updated["rating"] == 5
    assert updated["default_vehicle_id"] == vehicle["id"]
    assert fleet.active_drivers() == []


def test_driver_requires_existing_vehicle_and_valid_rating():
    with pytest.raises(fleet.FleetError, match="транспорт не найден"):
        fleet.add_driver("Иван", default_vehicle_id="missing")

    with pytest.raises(fleet.FleetError, match="от 1 до 5"):
        fleet.add_driver("Иван", rating=6)


def test_files_have_safe_relative_paths_and_document_metadata():
    driver = fleet.add_driver("Иван")

    photo_path = fleet.store_driver_photo(driver["id"], "../../photo.JPG", b"image")
    document = fleet.add_driver_document(driver["id"], "Права", "../../licence.pdf", b"pdf")

    assert photo_path.startswith("driver_photos/")
    assert ".." not in photo_path
    assert document["path"].startswith("driver_documents/")
    assert document["name"] == "licence.pdf"
    assert (paths.DATA_DIR / photo_path).read_bytes() == b"image"
    assert (paths.DATA_DIR / document["path"]).read_bytes() == b"pdf"
    saved_driver = fleet.load_fleet()["drivers"][0]
    assert saved_driver["photo"] == photo_path
    assert saved_driver["documents"] == [document]


def test_file_types_are_restricted():
    driver = fleet.add_driver("Иван")

    with pytest.raises(fleet.FleetError, match="Неподдерживаемый"):
        fleet.store_driver_photo(driver["id"], "image.exe", b"bad")

    with pytest.raises(fleet.FleetError, match="Неподдерживаемый"):
        fleet.add_driver_document(driver["id"], "Права", "document.docx", b"bad")


def test_deleting_vehicle_clears_default_driver_vehicle():
    vehicle = fleet.add_vehicle("Газель", "А123ВС71")
    driver = fleet.add_driver("Иван", default_vehicle_id=vehicle["id"])

    fleet.delete_vehicle(vehicle["id"])

    assert fleet.load_fleet()["vehicles"] == []
    assert fleet.load_fleet()["drivers"][0]["id"] == driver["id"]
    assert fleet.load_fleet()["drivers"][0]["default_vehicle_id"] == ""


def test_records_assignment_snapshot():
    fleet.record_order_route_assignments(
        "order.xlsx",
        "Город",
        "result.xlsx",
        [{"route": "route_1", "driver_id": "driver-1", "driver_name": "Иван", "vehicle_id": "vehicle-1"}],
    )

    data = json.loads(fleet.ORDER_ROUTE_ASSIGNMENTS_FILE.read_text(encoding="utf-8"))
    assert data["version"] == 1
    assert data["items"][0]["order_file"] == "order.xlsx"
    assert data["items"][0]["routes"][0]["driver_name"] == "Иван"


def test_driver_pin_is_hashed_and_can_be_verified():
    driver = fleet.add_driver("Иван")

    fleet.set_driver_pin(driver["id"], "1234")

    saved = fleet.load_fleet()["drivers"][0]
    assert saved["pin_hash"] != "1234"
    assert saved["pin_salt"]
    assert fleet.verify_driver_pin(driver["id"], "1234") is True
    assert fleet.verify_driver_pin(driver["id"], "9999") is False


def test_driver_pin_validation_and_update_preserve_credentials():
    driver = fleet.add_driver("Иван")
    fleet.set_driver_pin(driver["id"], "123456")

    with pytest.raises(fleet.FleetError, match="от 4 до 12"):
        fleet.set_driver_pin(driver["id"], "123")

    fleet.update_driver(driver["id"], "Иванов", "", 5, True, "", "", "")
    assert fleet.verify_driver_pin(driver["id"], "123456") is True
