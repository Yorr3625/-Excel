"""Настройки ИИ-разбора для вкладки «Вес»: провайдер и ключи API.

Хранится отдельно от modules/weight_log.py — сам учёт веса от этого файла
не зависит и работает полностью вручную, даже если ИИ не настроен.

Три способа получить ответ (см. modules/weight_ai.py):
  - claude_key — ключ Anthropic API, вставленный в настройках;
  - claude_cli — без ключа: библиотека сама берёт учётные данные,
    сохранённые `ant auth login` (Claude Code) на этой машине;
  - openai_key — ключ OpenAI API.
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
