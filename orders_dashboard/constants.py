"""Shared presentation labels and configuration constants."""
from modules.config import MAX_ROUTES
from modules.ai_settings import (
    PROVIDER_CLAUDE_CLI,
    PROVIDER_CLAUDE_KEY,
    PROVIDER_OPENAI_KEY,
)
from modules.weight_log import STAGES
from reflex.config import get_config
import json
from orders_dashboard import theme as ui


DASHBOARD_API_ORIGIN_JS = f"""
(() => {{
    const apiUrl = new URL({json.dumps(get_config().api_url.rstrip('/'))});
    if (['localhost', '127.0.0.1', '0.0.0.0', '[::1]'].includes(apiUrl.hostname)) {{
        apiUrl.hostname = window.location.hostname;
    }}
    if (window.location.protocol === 'https:' && apiUrl.protocol === 'http:') {{
        apiUrl.protocol = 'https:';
        apiUrl.port = '';
    }}
    return apiUrl.origin;
}})()
"""


ACCENT = ui.PURPLE


MAIL_APP_PASSWORD_URL = "https://myaccount.google.com/apppasswords"


UPLOAD_ID = "order_upload"


INVOICE_OCR_UPLOAD_ID = "invoice_ocr_upload"


VOLUME_CHART_DAYS = 31


VOLUME_ROUTE_LABELS = [f"Маршрут {i}" for i in range(1, MAX_ROUTES + 1)]


SUPPORTED_EXCEL_LABEL = ".xlsx, .xlsm, .xlsb, .xls, .xltx, .xltm"


WEIGHT_NO_BINDING = "— не привязано —"


WEIGHT_ROUTES = ["Маршрут №1", "Маршрут №2", "Маршрут №3", "Маршрут №4"]


WEIGHT_ROUTE_OPTIONS = [WEIGHT_NO_BINDING] + WEIGHT_ROUTES


WEIGHT_FILTER_ALL = "Все"


WEIGHT_FILTER_UNBOUND = "Без привязки"


WEIGHT_ROUTE_FILTER_OPTIONS = [WEIGHT_FILTER_ALL, WEIGHT_FILTER_UNBOUND] + WEIGHT_ROUTES


WEIGHT_STAGE_OPTIONS = list(STAGES)


WEIGHT_STAGE_FILTER_OPTIONS = [WEIGHT_FILTER_ALL] + list(STAGES)


AI_PROVIDER_LABELS = {
    PROVIDER_CLAUDE_KEY: "Claude (ключ Anthropic API)",
    PROVIDER_CLAUDE_CLI: "Claude через Claude Code CLI",
    PROVIDER_OPENAI_KEY: "ChatGPT (ключ OpenAI API)",
}


AI_PROVIDER_OPTIONS = [AI_PROVIDER_LABELS[PROVIDER_CLAUDE_KEY], AI_PROVIDER_LABELS[PROVIDER_CLAUDE_CLI]]


HELP_CHAT_MODEL_SONNET = "claude-sonnet-5"


HELP_CHAT_MODEL_HAIKU = "claude-haiku-4-5"


HELP_CHAT_MODEL_BY_LABEL = {"Sonnet": HELP_CHAT_MODEL_SONNET, "Haiku": HELP_CHAT_MODEL_HAIKU}


HELP_CHAT_MODEL_OPTIONS = list(HELP_CHAT_MODEL_BY_LABEL)


NAV_GROUPS = [
    {'label': 'Сегодня', 'icon': 'layout_dashboard', 'target': 'Dashboard', 'section': 'Работа'},
    {'label': 'Заказы', 'icon': 'package', 'target': 'Заказы', 'section': 'Работа'},
    {'label': 'Рейсы', 'icon': 'route', 'target': 'Маршруты', 'section': 'Работа'},
    {'label': 'Возвраты', 'icon': 'package', 'target': 'Возвраты', 'section': 'Работа'},
    {'label': 'Накладные', 'icon': 'file_spreadsheet', 'target': 'OCR накладных', 'section': 'Работа'},
    {'label': 'Шаблоны маршрутов', 'icon': 'list', 'target': 'Шаблоны маршрутов', 'section': 'Справочники'},
    {'label': 'Водители и транспорт', 'icon': 'truck', 'target': 'Водители и транспорт', 'section': 'Справочники'},
    {'label': 'Учёт веса', 'icon': 'scale', 'target': 'Вес', 'section': 'Дополнительно'},
    {'label': 'Отчёт по отгрузкам', 'icon': 'list', 'target': 'Сданный товар', 'section': 'Дополнительно'},
    {'label': 'Отслеживание', 'icon': 'map', 'target': 'Трекинг', 'section': 'Дополнительно'},
    {'label': 'Настройки', 'icon': 'settings', 'target': 'Настройки', 'section': 'Сервис'},
    {'label': 'Помощь', 'icon': 'info', 'target': 'Помощь', 'section': 'Сервис'},
]


PAGE_GROUPS = {
    "Dashboard": "Сводка",
    "Помощь": "Помощь",
    "Заказы": "Заказы",
    "Почта": "Заказы",
    "История": "Заказы",
    "Маршруты": "Рейсы",
    "Трекинг": "Дополнительно",
    "Водители и транспорт": "Справочники",
    "Сданный товар": "Дополнительно",
    "Возвраты": "Возвраты",
    "OCR накладных": "Накладные",
    "Вес": "Вес",
    "Настройки": "Настройки",
    "Резервные копии": "Настройки",
    "Версия": "Настройки",
}


PAGE_LABELS = {
    "Dashboard": "Сегодня",
    **{page: page for page in PAGE_GROUPS if page != "Dashboard"},
    "Маршруты": "Рейсы", "Вес": "Учёт веса", "Сданный товар": "Отчёт по отгрузкам",
    "Трекинг": "Отслеживание", "OCR накладных": "Накладные", "Помощь": "Помощь",
}


DISPATCH_STAGES = ["Все", "Ожидает загрузки", "Загрузка начата", "Загружен частично", "Готов к отгрузке", "Отгрузка идёт", "Отгрузка завершена"]


SETTINGS_LABELS = {
    "open_file_after_processing": (
        "Открывать файл после обработки",
        "Открыть готовый Excel-файл сразу после обработки.",
    ),
    "open_folder_after_processing": (
        "Открывать папку после обработки",
        "Открыть папку с результатом, если файл не открывается.",
    ),
    "create_logs": (
        "Вести лог обработки",
        "Сохранять текстовый лог каждой обработки в папку logs.",
    ),
    "save_backup": (
        "Сохранять резервную копию",
        "Хранить резервную копию исходного файла перед обработкой.",
    ),
    "show_errors": (
        "Показывать ошибки",
        "Выводить подробный текст ошибки обработки на экран.",
    ),
}


RETURN_STATUS_LABELS = {"submitted": "На проверке", "accepted": "Принят", "rejected": "Отклонён"}


DASHBOARD_LOGIN_JS = """
(async () => {
    const username = document.getElementById('dashboard-login-username');
    const password = document.getElementById('dashboard-login-password');
    const error = document.getElementById('dashboard-login-error');
    const button = document.getElementById('dashboard-login-submit');
    if (!username || !password || !error || button?.disabled) return;
    if (button) button.disabled = true;
    error.textContent = '';
    try {
        const response = await fetch(""" + DASHBOARD_API_ORIGIN_JS + """ + '/api/dashboard/login', {
            method: 'POST',
            headers: {'Content-Type': 'application/json'},
            credentials: 'include',
            body: JSON.stringify({username: username.value, password: password.value}),
        });
        password.value = '';
        const payload = await response.json().catch(() => ({}));
        if (!response.ok || !payload.ok) {
            error.textContent = payload.error || 'Не удалось выполнить вход.';
            return;
        }
        window.location.replace('/');
    } catch (_) {
        password.value = '';
        error.textContent = 'Не удалось подключиться к серверу.';
    } finally {
        if (button) button.disabled = false;
    }
})();
"""
