from threading import Event

from modules import mail_worker


def test_interval_minutes_uses_bounds_and_default():
    assert mail_worker._interval_minutes({}) == 10
    assert mail_worker._interval_minutes({"check_interval_minutes": "bad"}) == 10
    assert mail_worker._interval_minutes({"check_interval_minutes": 0}) == 1
    assert mail_worker._interval_minutes({"check_interval_minutes": 2000}) == 1440


def test_run_waits_without_connecting_when_mail_is_not_configured(monkeypatch):
    stop_event = Event()
    checked = []

    monkeypatch.setattr(
        mail_worker,
        "load_mail_config",
        lambda: {"enabled": False, "check_interval_minutes": 1},
    )
    monkeypatch.setattr(mail_worker, "is_configured", lambda _config: False)
    monkeypatch.setattr(
        mail_worker,
        "check_mail_with_retry",
        lambda _config: checked.append(True),
    )
    monkeypatch.setattr(stop_event, "wait", lambda _seconds: stop_event.set())

    assert mail_worker.run(stop_event) == 0
    assert checked == []


def test_run_checks_configured_mail_once(monkeypatch):
    stop_event = Event()
    calls = []
    config = {"enabled": True, "check_interval_minutes": 1}

    monkeypatch.setattr(mail_worker, "load_mail_config", lambda: config)
    monkeypatch.setattr(mail_worker, "is_configured", lambda value: value is config)
    monkeypatch.setattr(
        mail_worker,
        "check_mail_with_retry",
        lambda value: calls.append(value) or {"ok": True, "items": [{"id": 1}]},
    )
    monkeypatch.setattr(stop_event, "wait", lambda _seconds: stop_event.set())

    assert mail_worker.run(stop_event) == 0
    assert calls == [config]
