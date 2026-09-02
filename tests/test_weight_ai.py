import pytest

from modules import ai_settings, paths, weight_ai


@pytest.fixture(autouse=True)
def _isolated_ai_settings(tmp_path, monkeypatch):
    """Уводит файл настроек ИИ во временную папку — тесты не ходят в сеть
    и не читают настоящий config/ai.json."""

    target = tmp_path / "ai.json"
    monkeypatch.setattr(paths, "AI_SETTINGS_FILE", target)
    monkeypatch.setattr(ai_settings, "AI_SETTINGS_FILE", target)


def _settings(provider, **overrides):
    settings = dict(ai_settings.DEFAULT_SETTINGS)
    settings["provider"] = provider
    settings.update(overrides)
    return settings


# --- поддельный клиент Anthropic (client.messages.parse) ---


class _FakeAnthropicResponse:
    def __init__(self, items):
        self.parsed_output = weight_ai._WeightItemsList(
            items=[weight_ai._WeightItem(name=name, box_count=count) for name, count in items]
        )


class _FakeAnthropicMessages:
    def __init__(self, items=None, error=None):
        self._items = items or []
        self._error = error

    def parse(self, **kwargs):
        if self._error is not None:
            raise self._error
        return _FakeAnthropicResponse(self._items)


class _FakeAnthropicClient:
    def __init__(self, items=None, error=None):
        self.messages = _FakeAnthropicMessages(items, error)


# --- поддельный клиент OpenAI (client.chat.completions.parse) ---


class _FakeOpenAIMessage:
    def __init__(self, parsed):
        self.parsed = parsed


class _FakeOpenAIChoice:
    def __init__(self, parsed):
        self.message = _FakeOpenAIMessage(parsed)


class _FakeOpenAICompletion:
    def __init__(self, parsed):
        self.choices = [_FakeOpenAIChoice(parsed)]


class _FakeOpenAICompletions:
    def __init__(self, items=None, error=None, refuse=False):
        self._items = items
        self._error = error
        self._refuse = refuse

    def parse(self, **kwargs):
        if self._error is not None:
            raise self._error
        if self._refuse:
            return _FakeOpenAICompletion(None)
        parsed = weight_ai._WeightItemsList(
            items=[weight_ai._WeightItem(name=name, box_count=count) for name, count in self._items or []]
        )
        return _FakeOpenAICompletion(parsed)


class _FakeOpenAIChat:
    def __init__(self, **kwargs):
        self.completions = _FakeOpenAICompletions(**kwargs)


class _FakeOpenAIClient:
    def __init__(self, **kwargs):
        self.chat = _FakeOpenAIChat(**kwargs)


# --- общие проверки ---


def test_parse_empty_text_raises_before_touching_provider():
    with pytest.raises(weight_ai.WeightParseError, match="Вставьте список"):
        weight_ai.parse_weight_text("   ", client=object())


# --- claude_key ---


def test_claude_key_parses_items():
    client = _FakeAnthropicClient(items=[("Огурец", 15), ("Помидор", 10), ("Киви", 3)])
    settings = _settings(ai_settings.PROVIDER_CLAUDE_KEY, anthropic_api_key="sk-ant-test")

    result = weight_ai.parse_weight_text(
        "Огурец 15 ящ\nПомидор 10 ящ\nкиви 3 ящика", client=client, settings=settings
    )

    assert result == [
        {"name": "Огурец", "box_count": 15},
        {"name": "Помидор", "box_count": 10},
        {"name": "Киви", "box_count": 3},
    ]


def test_claude_key_without_key_raises():
    settings = _settings(ai_settings.PROVIDER_CLAUDE_KEY, anthropic_api_key="")

    with pytest.raises(weight_ai.WeightParseError, match="ключ Anthropic API"):
        weight_ai.parse_weight_text("Огурец 15 ящ", settings=settings)


def test_claude_wraps_client_errors():
    client = _FakeAnthropicClient(error=RuntimeError("boom"))
    settings = _settings(ai_settings.PROVIDER_CLAUDE_KEY, anthropic_api_key="sk-ant-test")

    with pytest.raises(weight_ai.WeightParseError, match="Не удалось обратиться к Claude"):
        weight_ai.parse_weight_text("Огурец 15 ящ", client=client, settings=settings)


def test_claude_no_items_raises():
    client = _FakeAnthropicClient(items=[])
    settings = _settings(ai_settings.PROVIDER_CLAUDE_KEY, anthropic_api_key="sk-ant-test")

    with pytest.raises(weight_ai.WeightParseError, match="Не удалось распознать"):
        weight_ai.parse_weight_text("что-то невнятное", client=client, settings=settings)


# --- claude_cli ---


def test_claude_cli_does_not_require_a_key():
    client = _FakeAnthropicClient(items=[("Огурец", 15)])
    settings = _settings(ai_settings.PROVIDER_CLAUDE_CLI)  # anthropic_api_key intentionally blank

    result = weight_ai.parse_weight_text("Огурец 15 ящ", client=client, settings=settings)

    assert result == [{"name": "Огурец", "box_count": 15}]


# --- openai_key ---


def test_openai_key_parses_items():
    client = _FakeOpenAIClient(items=[("Огурец", 15), ("Помидор", 10)])
    settings = _settings(ai_settings.PROVIDER_OPENAI_KEY, openai_api_key="sk-test")

    result = weight_ai.parse_weight_text("Огурец 15 ящ\nПомидор 10 ящ", client=client, settings=settings)

    assert result == [{"name": "Огурец", "box_count": 15}, {"name": "Помидор", "box_count": 10}]


def test_openai_without_key_raises():
    settings = _settings(ai_settings.PROVIDER_OPENAI_KEY, openai_api_key="")

    with pytest.raises(weight_ai.WeightParseError, match="ключ OpenAI API"):
        weight_ai.parse_weight_text("Огурец 15 ящ", settings=settings)


def test_openai_wraps_client_errors():
    client = _FakeOpenAIClient(error=RuntimeError("boom"))
    settings = _settings(ai_settings.PROVIDER_OPENAI_KEY, openai_api_key="sk-test")

    with pytest.raises(weight_ai.WeightParseError, match="Не удалось обратиться к ChatGPT"):
        weight_ai.parse_weight_text("Огурец 15 ящ", client=client, settings=settings)


def test_openai_refusal_raises():
    client = _FakeOpenAIClient(refuse=True)
    settings = _settings(ai_settings.PROVIDER_OPENAI_KEY, openai_api_key="sk-test")

    with pytest.raises(weight_ai.WeightParseError, match="отказался разобрать"):
        weight_ai.parse_weight_text("Огурец 15 ящ", client=client, settings=settings)


def test_openai_no_items_raises():
    client = _FakeOpenAIClient(items=[])
    settings = _settings(ai_settings.PROVIDER_OPENAI_KEY, openai_api_key="sk-test")

    with pytest.raises(weight_ai.WeightParseError, match="Не удалось распознать"):
        weight_ai.parse_weight_text("что-то невнятное", client=client, settings=settings)
