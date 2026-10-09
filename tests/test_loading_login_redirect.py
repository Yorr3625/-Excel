import asyncio
from types import SimpleNamespace

import orders_dashboard.loading_page as page


def test_anonymous_loading_uses_full_navigation_to_mount_loader(monkeypatch):
    monkeypatch.setattr(page, 'loading_principal_for_router', lambda router: None)
    event = page.LoadingState.load_loading_page.fn(SimpleNamespace(router={}))
    assert "window.location.replace('/loader/')" in str(event.args)


def test_expired_loading_session_uses_same_full_navigation(monkeypatch):
    monkeypatch.setattr(page, 'loading_principal_for_router', lambda router: None)
    event = SimpleNamespace(name=page.LoadingState.get_full_name() + '.save_loading', router_data={})
    update = asyncio.run(page.LoadingAuthMiddleware().preprocess(None, None, event))
    assert "window.location.replace('/loader/')" in str(update.events)
