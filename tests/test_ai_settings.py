import pytest

from modules import ai_settings, paths


@pytest.fixture(autouse=True)
def _isolated_ai_settings(tmp_path, monkeypatch):
    """Уводит файл настроек ИИ во временную папку, чтобы тесты не трогали config/."""

    target = tmp_path / "ai.json"
    monkeypatch.setattr(paths, "AI_SETTINGS_FILE", target)
    monkeypatch.setattr(ai_settings, "AI_SETTINGS_FILE", target)


def test_load_returns_defaults_when_file_is_missing():
    settings = ai_settings.load_ai_settings()

    assert settings["provider"] == ai_settings.PROVIDER_CLAUDE_KEY
    assert settings["anthropic_api_key"] == ""
    assert settings["openai_api_key"] == ""
    assert ai_settings.is_ai_configured(settings) is False


def test_load_survives_broken_json():
    ai_settings.AI_SETTINGS_FILE.write_text("{не json", encoding="utf-8")

    assert ai_settings.load_ai_settings()["provider"] == ai_settings.PROVIDER_CLAUDE_KEY


def test_save_and_load_roundtrip_claude_key():
    ai_settings.save_ai_settings(ai_settings.PROVIDER_CLAUDE_KEY, anthropic_api_key="sk-ant-test")

    settings = ai_settings.load_ai_settings()
    assert settings["provider"] == ai_settings.PROVIDER_CLAUDE_KEY
    assert settings["anthropic_api_key"] == "sk-ant-test"
    assert ai_settings.is_ai_configured(settings) is True


def test_claude_key_provider_not_configured_without_key():
    ai_settings.save_ai_settings(ai_settings.PROVIDER_CLAUDE_KEY)

    assert ai_settings.is_ai_configured() is False


def test_claude_cli_provider_is_always_configured():
    ai_settings.save_ai_settings(ai_settings.PROVIDER_CLAUDE_CLI)

    assert ai_settings.is_ai_configured() is True


def test_openai_provider_needs_key():
    ai_settings.save_ai_settings(ai_settings.PROVIDER_OPENAI_KEY)
    assert ai_settings.is_ai_configured() is False

    ai_settings.save_ai_settings(ai_settings.PROVIDER_OPENAI_KEY, openai_api_key="sk-test")
    assert ai_settings.is_ai_configured() is True


def test_save_empty_key_keeps_existing_key():
    ai_settings.save_ai_settings(ai_settings.PROVIDER_CLAUDE_KEY, anthropic_api_key="sk-ant-original")

    result = ai_settings.save_ai_settings(ai_settings.PROVIDER_CLAUDE_KEY, anthropic_api_key="  ")

    assert result["anthropic_api_key"] == "sk-ant-original"


def test_save_unknown_provider_falls_back_to_claude_key():
    result = ai_settings.save_ai_settings("не-провайдер")

    assert result["provider"] == ai_settings.PROVIDER_CLAUDE_KEY


def test_save_creates_parent_directory(tmp_path, monkeypatch):
    target = tmp_path / "нет-такой-папки" / "ai.json"
    monkeypatch.setattr(ai_settings, "AI_SETTINGS_FILE", target)

    ai_settings.save_ai_settings(ai_settings.PROVIDER_CLAUDE_KEY, anthropic_api_key="sk-ant-test")

    assert target.exists()


def test_yandex_vision_needs_key_and_folder_id():
    ai_settings.save_ai_settings(ai_settings.PROVIDER_CLAUDE_KEY, yandex_vision_api_key="yandex-test")
    assert ai_settings.is_yandex_vision_configured() is False

    ai_settings.save_ai_settings(
        ai_settings.PROVIDER_CLAUDE_KEY,
        yandex_vision_folder_id="b1g-folder",
    )
    assert ai_settings.is_yandex_vision_configured() is True


def test_empty_yandex_key_keeps_saved_value():
    ai_settings.save_ai_settings(
        ai_settings.PROVIDER_CLAUDE_KEY,
        yandex_vision_api_key="yandex-original",
        yandex_vision_folder_id="b1g-folder",
    )

    settings = ai_settings.save_ai_settings(ai_settings.PROVIDER_CLAUDE_KEY, yandex_vision_api_key=" ")

    assert settings["yandex_vision_api_key"] == "yandex-original"
    assert settings["yandex_vision_folder_id"] == "b1g-folder"
