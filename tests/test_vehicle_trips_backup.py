import json
import shutil
import zipfile

from modules import backup, paths, driver_orders, vehicle_trips as trips
from test_vehicle_trips import assignments, record, start, accept


def test_backup_restores_stock_and_trip_owned_source_images(assignments, tmp_path, monkeypatch):
    data = tmp_path / 'data'
    data.mkdir()
    registry = data / 'order_records.json'
    shutil.copyfile(paths.ORDER_RECORDS_FILE, registry)
    sources = data / 'driver_orders'
    shutil.copytree(paths.DRIVER_ORDERS_FOLDER, sources)
    monkeypatch.setattr(paths, 'ORDER_RECORDS_FILE', registry)
    monkeypatch.setattr(paths, 'DRIVER_ORDERS_FOLDER', sources)
    monkeypatch.setattr(paths, 'VEHICLE_TRIPS_FILE', data / 'vehicle_trips.sqlite3')
    trip = start(assignments)
    trip = accept(trip, trip['stops'][0], '1.5')
    archived = backup.create_backup(project_root=tmp_path)
    with zipfile.ZipFile(archived.path) as archive:
        assert archive.read('data/vehicle_trips.sqlite3').startswith(b'SQLite format 3')
    accept(trip, trip['stops'][1], '2')
    assert trips.stock(trips.load_trip(trip['id']))[0]['remaining_kg'] == '116.5'
    backup.restore_backup(archived.path, project_root=tmp_path, safety_backup=False)
    assert trips.load_trip(trip['id']) == trip
    source = driver_orders.load_snapshot(assignments[0]['assignment_id'])
    assert source['stores'][0]['lines'][0]['actual_qty'] == '1.5'
    assert source['stores'][1]['status'] == 'pending'
    assert trips.stock(trips.load_trip(trip['id']))[0]['remaining_kg'] == '118.5'


def test_old_archive_without_sqlite_is_still_readable(tmp_path):
    archive = tmp_path / 'old.zip'
    manifest = {'format_version': backup.BACKUP_FORMAT_VERSION, 'app_version': '1.3.5', 'created_at': '2026-10-10', 'reason': 'old',
                'files': [{'path': path, 'present': False} for path in backup._BACKUP_RELATIVE_FILES if path != 'data/vehicle_trips.sqlite3']}
    with zipfile.ZipFile(archive, 'w') as output:
        output.writestr('manifest.json', json.dumps(manifest))
    assert backup.inspect_backup(archive).file_count == 0
