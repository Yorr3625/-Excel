from pathlib import Path


LOADER_APP = Path("assets/loader-app.js")


def test_loader_pwa_uses_its_own_authenticated_read_only_api():
    source = LOADER_APP.read_text(encoding="utf-8")

    assert '"/api/loader/login"' in source
    assert '"/api/loader/vehicles"' in source
    assert '"/api/loader/vehicle"' in source
    assert '"/api/loader/orders"' in source
    assert 'credentials: "include"' in source
    assert '"X-Loader-CSRF"' in source
    assert "/api/driver/" not in source


def test_loader_pwa_does_not_offer_driver_mutations_or_render_unescaped_data():
    source = LOADER_APP.read_text(encoding="utf-8")

    assert "navigator.geolocation" not in source
    assert "/complete" not in source
    assert "mileage" not in source
    assert 'function esc(value)' in source
    assert "esc(line.name)" in source
    assert "esc(store.name)" in source
