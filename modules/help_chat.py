"""Плавающий чат-помощник для посетителей сайта.

Обычный диалог с Claude (Sonnet или Haiku) — без доступа к данным
дашборда: не может ничего добавить, изменить или удалить в заказах,
весе или настройках, только отвечает на вопросы. Работает, только если
на странице «Настройки» задан ключ Anthropic API либо на этом
компьютере выполнен `ant auth login` (см. modules/ai_settings.py).

Виджет открыт для любого, кто открыл сайт — в том числе по временной
ссылке share_dashboard.bat, — поэтому запросы намеренно ограничены
(max_tokens, эффорт «low») и не имеют инструментов и доступа к файлам.
"""

from typing import Optional

from modules.ai_settings import PROVIDER_CLAUDE_CLI, load_ai_settings

MODELS = ("claude-sonnet-5", "claude-haiku-4-5")

_SYSTEM_PROMPT = (
    "Ты — вспомогательный чат на сайте программы «Обработка заказов» "
    "(обработка Excel-заказов по маршрутам доставки, учёт веса, "
    "водители). Помогай посетителям сайта общими вопросами о работе "
    "приложения и другими простыми вопросами. У тебя нет доступа к "
    "данным этого дашборда (заказам, весу, настройкам, файлам) и нет "
    "возможности что-либо изменить — только обычный разговор. Если не "
    "знаешь ответа, честно скажи об этом. Отвечай кратко и по делу."
)


class HelpChatError(Exception):
    """Не удалось получить ответ — понятная причина для показа в чате."""


def send_chat_message(
    history: list[dict],
    model: str,
    client=None,
    settings: Optional[dict] = None,
) -> str:
    """Отправляет всю историю диалога и возвращает текст ответа Claude.

    history — [{"role": "user"|"assistant", "content": "..."}, ...].
    client/settings — для тестов (иначе settings читаются из modules.ai_settings).
    """

    if model not in MODELS:
        model = MODELS[0]

    settings = settings if settings is not None else load_ai_settings()

    if client is None:
        try:
            import anthropic
        except ImportError as error:
            raise HelpChatError("Библиотека anthropic не установлена") from error

        if settings.get("provider") == PROVIDER_CLAUDE_CLI:
            # Ключ не нужен: SDK сама берёт ANTHROPIC_API_KEY или профиль,
            # сохранённый `ant auth login`.
            client = anthropic.Anthropic()
        else:
            api_key = settings.get("anthropic_api_key", "").strip()
            if not api_key:
                raise HelpChatError("Чат не настроен — задайте ключ Anthropic API на странице «Настройки»")
            client = anthropic.Anthropic(api_key=api_key)

    try:
        response = client.messages.create(
            model=model,
            max_tokens=1024,
            system=_SYSTEM_PROMPT,
            output_config={"effort": "low"},
            messages=[{"role": item["role"], "content": item["content"]} for item in history],
        )
    except Exception as error:
        raise HelpChatError(f"Не удалось получить ответ: {error}") from error

    text = next((block.text for block in response.content if block.type == "text"), "")
    if not text:
        raise HelpChatError("Пустой ответ от Claude")

    return text
