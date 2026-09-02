import pytest

from modules import ai_settings, help_chat, paths


@pytest.fixture(autouse=True)
def _isolated_ai_settings(tmp_path, monkeypatch):
    """Уводит файл настроек ИИ во временную папку — тесты не ходят в сеть."""

    target = tmp_path / "ai.json"
    monkeypatch.setattr(paths, "AI_SETTINGS_FILE", target)
    monkeypatch.setattr(ai_settings, "AI_SETTINGS_FILE", target)


def _settings(provider, **overrides):
    settings = dict(ai_settings.DEFAULT_SETTINGS)
    settings["provider"] = provider
    settings.update(overrides)
    return settings


class _FakeTextBlock:
    def __init__(self, text):
        self.type = "text"
        self.text = text


class _FakeResponse:
    def __init__(self, text):
        self.content = [_FakeTextBlock(text)]


class _FakeMessages:
    def __init__(self, text=None, error=None):
        self._text = text
        self._error = error
        self.last_kwargs = None

    def create(self, **kwargs):
        self.last_kwargs = kwargs
        if self._error is not None:
            raise self._error
        return _FakeResponse(self._text)


class _FakeClient:
    def __init__(self, text=None, error=None):
        self.messages = _FakeMessages(text, error)


def test_send_chat_message_returns_reply_text():
    client = _FakeClient(text="Здравствуйте! Чем могу помочь?")
    settings = _settings(ai_settings.PROVIDER_CLAUDE_KEY, anthropic_api_key="sk-ant-test")

    reply = help_chat.send_chat_message(
        [{"role": "user", "content": "Привет"}], "claude-sonnet-5", client=client, settings=settings
    )

    assert reply == "Здравствуйте! Чем могу помочь?"
    assert client.messages.last_kwargs["model"] == "claude-sonnet-5"


def test_unknown_model_falls_back_to_default():
    client = _FakeClient(text="ok")
    settings = _settings(ai_settings.PROVIDER_CLAUDE_KEY, anthropic_api_key="sk-ant-test")

    help_chat.send_chat_message([{"role": "user", "content": "hi"}], "gpt-4", client=client, settings=settings)

    assert client.messages.last_kwargs["model"] == help_chat.MODELS[0]


def test_claude_cli_does_not_require_a_key():
    client = _FakeClient(text="ok")
    settings = _settings(ai_settings.PROVIDER_CLAUDE_CLI)  # anthropic_api_key intentionally blank

    reply = help_chat.send_chat_message([{"role": "user", "content": "hi"}], "claude-sonnet-5", client=client, settings=settings)

    assert reply == "ok"


def test_claude_key_without_key_raises():
    settings = _settings(ai_settings.PROVIDER_CLAUDE_KEY, anthropic_api_key="")

    with pytest.raises(help_chat.HelpChatError, match="не настроен"):
        help_chat.send_chat_message([{"role": "user", "content": "hi"}], "claude-sonnet-5", settings=settings)


def test_wraps_client_errors():
    client = _FakeClient(error=RuntimeError("boom"))
    settings = _settings(ai_settings.PROVIDER_CLAUDE_KEY, anthropic_api_key="sk-ant-test")

    with pytest.raises(help_chat.HelpChatError, match="Не удалось получить ответ"):
        help_chat.send_chat_message([{"role": "user", "content": "hi"}], "claude-sonnet-5", client=client, settings=settings)


def test_empty_reply_raises():
    client = _FakeClient(text="")
    settings = _settings(ai_settings.PROVIDER_CLAUDE_KEY, anthropic_api_key="sk-ant-test")

    with pytest.raises(help_chat.HelpChatError, match="Пустой ответ"):
        help_chat.send_chat_message([{"role": "user", "content": "hi"}], "claude-sonnet-5", client=client, settings=settings)
