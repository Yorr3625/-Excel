from pathlib import Path


DRIVER_APP = Path("assets/driver-app.js")


def test_driver_pwa_migrates_and_flushes_mileage_before_store_operations():
    source = DRIVER_APP.read_text(encoding="utf-8")

    assert 'const DB_VERSION = 4;' in source
    assert 'const MILEAGE_QUEUE_STORE = "mileage_queue";' in source
    assert 'db.createObjectStore(MILEAGE_QUEUE_STORE)' in source
    assert 'tx.objectStore(MILEAGE_QUEUE_STORE).clear();' in source
    assert source.index("await flushMileageQueue()") < source.index("await flushQueue()")


def test_driver_pwa_keeps_required_mileage_in_the_driver_flow():
    source = DRIVER_APP.read_text(encoding="utf-8")

    assert 'else if (mileage?.required) renderMileage();' in source
    assert 'await dbPut(MILEAGE_QUEUE_STORE, mileageQueueKey(payload), {driver_id: driverId, payload});' in source
    assert 'api("/api/driver/mileage"' in source


def test_driver_pwa_collects_weighted_store_shipment_measurements():
    source = DRIVER_APP.read_text(encoding="utf-8")

    assert 'data-field="box_count"' in source
    assert 'data-field="tare_weight_per_box_kg"' in source
    assert 'data-field="gross_weight_kg"' in source
    assert "measurementNet" in source
    assert "measurements, operation_id" in source
    assert "waiting_loading" in source


def test_driver_pwa_return_storage_is_migrated_and_cleared_on_logout():
    source = DRIVER_APP.read_text(encoding="utf-8")

    for store in ("RETURN_CACHE_STORE", "RETURN_DRAFT_STORE", "RETURN_QUEUE_STORE"):
        assert f"db.createObjectStore({store})" in source
        assert f"tx.objectStore({store}).clear();" in source
    assert source.index('else if (view === "returns")') < source.index("else if (mileage?.required)")
    assert source.index("await flushQueue()") < source.index("await flushReturnQueue()")
    assert 'assignment_id: assignment.assignment_id' in source
    assert 'const CACHE_NAME = "logistics-static-v6";' in Path("assets/service-worker.js").read_text(encoding="utf-8")


def test_driver_pwa_javascript_behavior():
    import shutil
    import subprocess

    import pytest

    node = shutil.which("node")
    if node is None:
        pytest.skip("Node.js is required for driver PWA behavior tests")
    result = subprocess.run(
        [node, "--test", str(Path(__file__).with_name("driver_pwa_behavior.cjs")), str(Path(__file__).with_name("service_worker_behavior.cjs"))],
        capture_output=True,
        text=True,
        encoding="utf-8",
        timeout=60,
    )
    assert result.returncode == 0, result.stdout + result.stderr


def test_driver_pwa_uses_shared_theme_without_rerendering_unsaved_fields():
    source = DRIVER_APP.read_text(encoding="utf-8")

    assert 'window.LogisticsTheme?.getPreference?.()' in source
    assert 'data-theme-select' in source
    assert 'value="system"' in source
    assert 'value="light"' in source
    assert 'value="dark"' in source
    assert 'data-theme-toggle' not in source
    assert 'function applyTheme()' not in source
    assert 'data-label="Товар"' in source
    assert 'data-label="Выполнено"' in source
