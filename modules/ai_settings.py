"""Настройки подключений ИИ для чата и OCR накладных.

Ключи сохраняются локально в config/ai.json, который исключён из Git.

Поддерживаемые подключения чата:
  - claude_key — ключ Anthropic API;
  - claude_cli — учётные данные, сохранённые через Claude Code CLI;
  - openai_key — ключ OpenAI API.

Для OCR накладных используется отдельный ключ Yandex Vision и ID каталога.
"""

import json

from modules.paths import AI_SETTINGS_FILE

PROVIDER_CLAUDE_KEY = "claude_key"
PROVIDER_CLAUDE_CLI = "claude_cli"
PROVIDER_OPENAI_KEY = "openai_key"
PROVIDERS = (PROVIDER_CLAUDE_KEY, PROVIDER_CLAUDE_CLI, PROVIDER_OPENAI_KEY)

DEFAULT_SETTINGS = {
    "provider": PROVIDER_CLAUDE_KEY,
    "anthropic_api_key": "",
    "openai_api_key": "",
    "openai_model": "",
    "yandex_vision_api_key": "",
    "yandex_vision_folder_id": "",
}


def load_ai_settings() -> dict:
    """Настройки ИИ; при отсутствии/повреждении файла — значения по умолчанию."""

    settings = dict(DEFAULT_SETTINGS)

    try:
        data = json.loads(AI_SETTINGS_FILE.read_text(encoding="utf-8"))
        for key in DEFAULT_SETTINGS:
            if key in data:
                settings[key] = str(data[key])
    except (OSError, json.JSONDecodeError):
        pass

    if settings["provider"] not in PROVIDERS:
        settings["provider"] = PROVIDER_CLAUDE_KEY

    return settings


def save_ai_settings(
    provider: str,
    anthropic_api_key: str = "",
    openai_api_key: str = "",
    openai_model: str = "",
    yandex_vision_api_key: str = "",
    yandex_vision_folder_id: str = "",
) -> dict:
    """Сохраняет настройки ИИ и возвращает то, что в итоге сохранено.

    Пустое значение ключа оставляет уже сохранённый ключ нетронутым — как
    поле пароля приложения в настройках почты, чтобы форму можно было
    пересохранить, не вставляя секрет заново.
    """

    current = load_ai_settings()

    if provider not in PROVIDERS:
        provider = PROVIDER_CLAUDE_KEY

    settings = {
        "provider": provider,
        "anthropic_api_key": anthropic_api_key.strip() or current["anthropic_api_key"],
        "openai_api_key": openai_api_key.strip() or current["openai_api_key"],
        "openai_model": openai_model.strip() or current["openai_model"],
        "yandex_vision_api_key": yandex_vision_api_key.strip() or current["yandex_vision_api_key"],
        "yandex_vision_folder_id": yandex_vision_folder_id.strip() or current["yandex_vision_folder_id"],
    }

    AI_SETTINGS_FILE.parent.mkdir(parents=True, exist_ok=True)
    AI_SETTINGS_FILE.write_text(
        json.dumps(settings, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    return settings


def is_ai_configured(settings: dict | None = None) -> bool:
    """Хватает ли настроек, чтобы попробовать вызвать ИИ.

    Для claude_cli реальная доступность (выполнен ли `ant auth login`)
    проверяется только при самом вызове — тут просто разрешаем попытку.
    """

    settings = settings if settings is not None else load_ai_settings()
    provider = settings.get("provider", PROVIDER_CLAUDE_KEY)

    if provider == PROVIDER_CLAUDE_CLI:
        return True
    if provider == PROVIDER_OPENAI_KEY:
        return bool(settings.get("openai_api_key"))

    return bool(settings.get("anthropic_api_key"))


def is_yandex_vision_configured(settings: dict | None = None) -> bool:
    """Настроено ли распознавание накладных через Yandex Vision."""

    settings = settings if settings is not None else load_ai_settings()
    return bool(
        settings.get("yandex_vision_api_key", "").strip()
        and settings.get("yandex_vision_folder_id", "").strip()
    )
