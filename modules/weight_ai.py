"""Разбор свободного текста в строки вкладки «Вес» через ИИ.

Удобство ввода: приводит вставленный список («Огурец 15 ящ», «Помидор 10
ящ») к парам наименование/количество ящиков — черновик, который
пользователь смотрит и подтверждает перед сохранением. Сам учёт веса
(modules/weight_log.py) от этого модуля не зависит и полностью работает
вручную, если ИИ не настроен или недоступен: в таком случае просто
поднимается WeightParseError с понятной причиной, ничего не записывая.

Поддерживаются три способа получить ответ (modules/ai_settings.py):
  - PROVIDER_CLAUDE_KEY — ключ Anthropic API, вставленный в настройках;
  - PROVIDER_CLAUDE_CLI — без ключа: библиотека сама берёт учётные
    данные, сохранённые `ant auth login` (Claude Code) на этой машине;
  - PROVIDER_OPENAI_KEY — ключ OpenAI API.
"""

from typing import List, Optional

from pydantic import BaseModel

from modules.ai_settings import (
    PROVIDER_CLAUDE_CLI,
    PROVIDER_CLAUDE_KEY,
    PROVIDER_OPENAI_KEY,
    load_ai_settings,
)

CLAUDE_MODEL = "claude-opus-5"
DEFAULT_OPENAI_MODEL = "gpt-4o-mini"

_SYSTEM_PROMPT = (
    "Ты разбираешь список товаров склада на позиции. Пользователь присылает "
    "произвольный текст, обычно по одной позиции на строку, например "
    "«Огурец 15 ящ» или «Помидор - 10 ящиков». Для каждой такой строки "
    "определи наименование товара (в именительном падеже, с заглавной "
    "буквы) и количество ящиков (целое число). Игнорируй пустые строки, "
    "заголовки и всё, что не похоже на товарную позицию с количеством."
)


class _WeightItem(BaseModel):
    name: str
    box_count: int


class _WeightItemsList(BaseModel):
    items: List[_WeightItem]


class WeightParseError(Exception):
    """Не удалось разобрать текст — понятная причина для показа в форме."""


def parse_weight_text(text: str, client=None, settings: Optional[dict] = None) -> list[dict]:
    """Возвращает [{"name": ..., "box_count": ...}, ...] по свободному тексту.

    client — для тестов (уже настроенный клиент нужного провайдера);
    settings — для тестов (иначе читаются из modules.ai_settings).
    """

    text = text.strip()
    if not text:
        raise WeightParseError("Вставьте список позиций")

    settings = settings if settings is not None else load_ai_settings()
    provider = settings.get("provider", PROVIDER_CLAUDE_KEY)

    if provider == PROVIDER_OPENAI_KEY:
        if client is None:
            api_key = settings.get("openai_api_key", "").strip()
            if not api_key:
                raise WeightParseError("Сначала укажите ключ OpenAI API в настройках ИИ")
            try:
                import openai
            except ImportError as error:
                raise WeightParseError("Библиотека openai не установлена") from error
            client = openai.OpenAI(api_key=api_key)

        model = settings.get("openai_model", "").strip() or DEFAULT_OPENAI_MODEL
        return _parse_with_openai(text, client, model)

    if client is None:
        try:
            import anthropic
        except ImportError as error:
            raise WeightParseError("Библиотека anthropic не установлена") from error

        if provider == PROVIDER_CLAUDE_KEY:
            api_key = settings.get("anthropic_api_key", "").strip()
            if not api_key:
                raise WeightParseError("Сначала укажите ключ Anthropic API в настройках ИИ")
            client = anthropic.Anthropic(api_key=api_key)
        else:
            # PROVIDER_CLAUDE_CLI — ключ не нужен: SDK сама берёт
            # ANTHROPIC_API_KEY или профиль, сохранённый `ant auth login`.
            client = anthropic.Anthropic()

    return _parse_with_claude(text, client)


def _parse_with_claude(text: str, client) -> list[dict]:
    try:
        response = client.messages.parse(
            model=CLAUDE_MODEL,
            max_tokens=4096,
            system=_SYSTEM_PROMPT,
            messages=[{"role": "user", "content": text}],
            output_format=_WeightItemsList,
        )
    except Exception as error:
        raise WeightParseError(
            "Не удалось обратиться к Claude — проверьте ключ API или что на "
            f"этой машине выполнен `ant auth login`: {error}"
        ) from error

    return _finalize(response.parsed_output.items)


def _parse_with_openai(text: str, client, model: str) -> list[dict]:
    try:
        completion = client.chat.completions.parse(
            model=model,
            messages=[
                {"role": "system", "content": _SYSTEM_PROMPT},
                {"role": "user", "content": text},
            ],
            response_format=_WeightItemsList,
        )
    except Exception as error:
        raise WeightParseError(f"Не удалось обратиться к ChatGPT: {error}") from error

    message = completion.choices[0].message
    if message.parsed is None:
        raise WeightParseError("ChatGPT отказался разобрать текст")

    return _finalize(message.parsed.items)


def _finalize(items) -> list[dict]:
    if not items:
        raise WeightParseError("Не удалось распознать ни одной позиции")

    return [{"name": item.name, "box_count": item.box_count} for item in items]
