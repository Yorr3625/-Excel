from modules import dashboard_sessions


def test_session_token_is_opaque_and_can_be_revoked():
    dashboard_sessions.reset_sessions()

    token = dashboard_sessions.create_session()

    assert dashboard_sessions.valid_session(token)
    assert not dashboard_sessions.valid_session("unknown-token")
    assert token not in dashboard_sessions._SESSIONS
    dashboard_sessions.destroy_session(token)
    assert not dashboard_sessions.valid_session(token)


def test_expired_session_is_rejected(monkeypatch):
    dashboard_sessions.reset_sessions()
    now = [1_000.0]
    monkeypatch.setattr(dashboard_sessions.time, "time", lambda: now[0])
    token = dashboard_sessions.create_session()

    now[0] += dashboard_sessions.SESSION_TTL_SECONDS

    assert not dashboard_sessions.valid_session(token)
