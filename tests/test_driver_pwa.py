from pathlib import Path


DRIVER_APP = Path("assets/driver-app.js")


def test_driver_pwa_migrates_and_flushes_mileage_before_store_operations():
    source = DRIVER_APP.read_text(encoding="utf-8")

    assert 'const DB_VERSION = 3;' in source
    assert 'const MILEAGE_QUEUE_STORE = "mileage_queue";' in source
    assert 'db.createObjectStore(MILEAGE_QUEUE_STORE)' in source
    assert 'tx.objectStore(MILEAGE_QUEUE_STORE).clear();' in source
    assert source.index("await flushMileageQueue()") < source.index("await flushQueue()")


def test_driver_pwa_keeps_required_mileage_in_the_driver_flow():
    source = DRIVER_APP.read_text(encoding="utf-8")

    assert 'else if (mileage?.required) renderMileage();' in source
    assert 'await dbPut(MILEAGE_QUEUE_STORE, mileageQueueKey(payload), {driver_id: driverId, payload});' in source
    assert 'api("/api/driver/mileage"' in source
