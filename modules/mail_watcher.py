"""Проверка почты: сохраняет письма и ожидаемые вложения от заданных источников.

Почтовый ящик открывается только для чтения. Excel-заказы складываются в
``data/orders``, PDF-накладные — в ``data/invoices``. Метаданные писем
сохраняются в ``data/mail_items.json``, поэтому список не исчезает после
перезапуска дашборда.
"""

import email
import imaplib
import json
import re
import time
from datetime import date, datetime, timedelta
from email.header import decode_header, make_header
from email.utils import parsedate_to_datetime
from pathlib import Path
from typing import TypedDict

from modules.order_validator import ALLOWED_SUFFIXES, validate_order_file
from modules.paths import CONFIG_DIR, DATA_DIR, INVOICES_FOLDER, ORDERS_FOLDER


MAIL_CONFIG_FILE = CONFIG_DIR / "mail.json"
MAIL_EXAMPLE_CONFIG_FILE = CONFIG_DIR / "mail.example.json"
SEEN_FILE = DATA_DIR / "mail_seen.json"
MAIL_ITEMS_FILE = DATA_DIR / "mail_items.json"
MAIL_UID_CACHE_FILE = DATA_DIR / "mail_uid_cache.json"
MAIL_ERROR_LOG_FILE = DATA_DIR / "mail_errors.json"

SEEN_LIMIT = 500
MAIL_ITEMS_LIMIT = 1000
MAIL_ERROR_LOG_LIMIT = 50
DEFAULT_CACHE_DAYS = 14
DEFAULT_RETRY_ATTEMPTS = 3
DEFAULT_RETRY_DELAY_SECONDS = 5.0
PDF_SUFFIXES = (".pdf",)
KIND_ORDERS = "orders"
KIND_INVOICES = "invoices"
KIND_MESSAGE = "message"
DEFAULT_ORDER_SUBJECT = "Заказ ТС МОЛОКО"
DEFAULT_MILK_ORDER_EMAIL = "fyodorova.ekaterina@moloko.com.ru"

CITY_INVOICE_MODE = "Город"
REGION_INVOICE_MODE = "Область"
INVOICE_CATEGORY_MILK = "Молоко"
INVOICE_CATEGORY_PARUS = "Парус"
INVOICE_CATEGORY_KRAIMERI = "Краймери"
INVOICE_CATEGORY_UNCATEGORIZED = "Без категории"
ACCOUNTANT_INVOICE_CATEGORIES = (
    {
        "name": INVOICE_CATEGORY_MILK,
        "markers": ("фм 40", "фм40", "мдв"),
    },
    {
        "name": INVOICE_CATEGORY_PARUS,
        "markers": ("парус",),
    },
    {
        "name": INVOICE_CATEGORY_KRAIMERI,
        "markers": ("краймер", "краймар"),
    },
)
OLGA_ORDER_SOURCE = {
    "name": "Ольга",
    "email": "o_solenkova@mail.ru",
    "person": "Ольга Соленкова",
    "kind": KIND_ORDERS,
    "subject": DEFAULT_ORDER_SUBJECT,
    "categories": [],
}
REGION_INVOICE_GROUPS = {
    "Кировское / Торез / Шахтерск": ("кировск", "торез", "шахтер"),
    "Горловка": ("горлов",),
    "Макеевка / Харцызск": ("макеев", "харцыз"),
}


class MailErrorEntry(TypedDict):
    timestamp: str
    display_time: str
    operation: str
    error: str


_MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]

DEFAULT_CONFIG = {
    "enabled": False,
    "imap_server": "imap.gmail.com",
    "imap_port": 993,
    "email": "",
    "app_password": "",
    "sources": [],
    "folder": "INBOX",
    "since_days": 14,
    "cache_days": DEFAULT_CACHE_DAYS,
    "check_interval_minutes": 10,
    "retry_attempts": DEFAULT_RETRY_ATTEMPTS,
    "retry_delay_seconds": DEFAULT_RETRY_DELAY_SECONDS,
}


def load_mail_config() -> dict:
    config = dict(DEFAULT_CONFIG)

    try:
        config.update(json.loads(MAIL_CONFIG_FILE.read_text(encoding="utf-8")))
    except (OSError, json.JSONDecodeError):
        pass

    return config


def _normalise_app_password(value: str) -> str:
    """Убирает пробелы из ключа приложения, показанного группами."""

    return re.sub(r"\s+", "", str(value or ""))


def save_mail_credentials(email_addr: str, app_password: str) -> tuple[bool, str]:
    """Сохраняет адрес и пароль приложения, не раскрывая пароль наружу."""

    email_addr = str(email_addr or "").strip()
    config = load_mail_config()
    password = _normalise_app_password(app_password)

    if not email_addr:
        return False, "Введите адрес электронной почты"

    # При редактировании пустое поле означает «оставить текущий ключ».
    if not password:
        password = _normalise_app_password(config.get("app_password"))

    if not password:
        return False, "Введите ключ приложения"

    if not sources(config):
        template = _read_json(MAIL_EXAMPLE_CONFIG_FILE, {})
        template_sources = template.get("sources") or []

        if template_sources:
            config["sources"] = template_sources

    if not sources(config):
        return False, "Не настроены отправители заказов и накладных"

    config.update({
        "enabled": True,
        "email": email_addr,
        "app_password": password,
    })
    _write_json(MAIL_CONFIG_FILE, config)
    return True, "Данные почты сохранены"


def sources(config: dict | None = None) -> list[dict]:
    """Возвращает отправителей в едином виде, включая старый ``senders``."""

    config = config or load_mail_config()
    result = []

    for source in config.get("sources") or []:
        email_addr = (source.get("email") or "").strip()

        if not email_addr:
            continue

        kind = source.get("kind") or KIND_ORDERS
        categories = _normalise_invoice_categories(source.get("categories"))
        if (
            kind == KIND_INVOICES
            and not categories
            and str(source.get("name") or "").strip().casefold() == "бухгалтер"
        ):
            categories = [dict(category) for category in ACCOUNTANT_INVOICE_CATEGORIES]
        result.append({
            "name": source.get("name") or email_addr,
            "email": email_addr,
            "person": source.get("person", ""),
            "kind": kind,
            "subject": source.get("subject") or (
                DEFAULT_ORDER_SUBJECT if kind == KIND_ORDERS else ""
            ),
            "categories": categories,
        })

    for email_addr in config.get("senders") or []:
        email_addr = (email_addr or "").strip()

        if email_addr and not any(item["email"] == email_addr for item in result):
            result.append({
                "name": email_addr,
                "email": email_addr,
                "person": "",
                "kind": KIND_ORDERS,
                "subject": DEFAULT_ORDER_SUBJECT,
                "categories": [],
            })

    has_default_milk_source = any(
        item["email"].casefold() == DEFAULT_MILK_ORDER_EMAIL
        for item in result
    )
    if has_default_milk_source and not any(
        item["email"].casefold() == OLGA_ORDER_SOURCE["email"].casefold()
        for item in result
    ):
        result.append(dict(OLGA_ORDER_SOURCE))

    return result


def is_configured(config: dict | None = None) -> bool:
    config = config or load_mail_config()
    return bool(
        config.get("enabled")
        and config.get("email")
        and config.get("app_password")
        and sources(config)
    )


def _read_json(path: Path, default):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return default


def _write_json(path: Path, data) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def _safe_error_text(error: object, config: dict | None = None) -> str:
    """Убирает учётные данные из текста перед показом и журналированием."""

    text = str(error or "Неизвестная ошибка")
    config = config or {}
    secrets = {
        str(config.get("email", "")).strip(),
        str(config.get("app_password", "")).strip(),
        _normalise_app_password(config.get("app_password", "")),
    }

    for secret in sorted((value for value in secrets if value), key=len, reverse=True):
        text = text.replace(secret, "***")

    return text


def load_mail_error_log() -> list[MailErrorEntry]:
    """Возвращает последние ошибки подключения, новые сверху."""

    entries = _read_json(MAIL_ERROR_LOG_FILE, [])
    if not isinstance(entries, list):
        return []

    result = []
    for entry in entries[:MAIL_ERROR_LOG_LIMIT]:
        if not isinstance(entry, dict):
            continue
        result.append({
            "timestamp": str(entry.get("timestamp", "")),
            "display_time": str(entry.get("display_time", "")),
            "operation": str(entry.get("operation", "Проверка почты")),
            "error": str(entry.get("error", "Неизвестная ошибка")),
        })

    return result


def append_mail_error(
    operation: str,
    error: object,
    config: dict | None = None,
) -> MailErrorEntry:
    """Сохраняет безопасное описание ошибки без адреса и ключа приложения."""

    safe_config = config if config is not None else load_mail_config()
    now = datetime.now().astimezone()
    entry: MailErrorEntry = {
        "timestamp": now.isoformat(),
        "display_time": now.strftime("%d.%m.%Y %H:%M:%S"),
        "operation": str(operation or "Проверка почты"),
        "error": _safe_error_text(error, safe_config),
    }
    _write_json(
        MAIL_ERROR_LOG_FILE,
        [entry, *load_mail_error_log()][:MAIL_ERROR_LOG_LIMIT],
    )
    return entry


def clear_mail_error_log() -> None:
    """Очищает только журнал ошибок, не затрагивая письма и вложения."""

    _write_json(MAIL_ERROR_LOG_FILE, [])


def _imap_error_is_retryable(error: object) -> bool:
    text = str(error).casefold()
    authentication_markers = (
        "authenticationfailed",
        "authentication failed",
        "invalid credentials",
        "login failed",
        "authorization failed",
        "bad credentials",
        "неверн",
        "парол",
    )
    return not any(marker in text for marker in authentication_markers)


def _retry_settings(config: dict) -> tuple[int, float]:
    try:
        attempts = int(config.get("retry_attempts", DEFAULT_RETRY_ATTEMPTS))
    except (TypeError, ValueError):
        attempts = DEFAULT_RETRY_ATTEMPTS

    try:
        delay = float(config.get("retry_delay_seconds", DEFAULT_RETRY_DELAY_SECONDS))
    except (TypeError, ValueError):
        delay = DEFAULT_RETRY_DELAY_SECONDS

    return min(max(attempts, 1), 5), min(max(delay, 0.0), 300.0)


def check_mail_connection(config: dict | None = None) -> dict:
    """Проверяет вход в IMAP, не ищет письма и не скачивает вложения."""

    config = config or load_mail_config()
    result = {"ok": False, "error": "", "retryable": False}

    if not is_configured(config):
        result["error"] = "Почта не настроена — заполните данные подключения"
        append_mail_error("Проверка соединения", result["error"], config)
        return result

    try:
        with imaplib.IMAP4_SSL(config["imap_server"], int(config["imap_port"])) as imap:
            login_status, _login_data = imap.login(
                config["email"], config["app_password"]
            )
            if login_status != "OK":
                raise imaplib.IMAP4.error("Сервер отклонил вход")

            select_status, _select_data = imap.select(
                config.get("folder") or "INBOX",
                readonly=True,
            )
            if select_status != "OK":
                raise imaplib.IMAP4.error("Сервер не открыл папку почты")
    except imaplib.IMAP4.error as error:
        safe_error = _safe_error_text(error, config)
        result["error"] = f"Почтовый сервер отказал: {safe_error}"
        result["retryable"] = _imap_error_is_retryable(error)
        append_mail_error("Проверка соединения", result["error"], config)
        return result
    except (OSError, TimeoutError) as error:
        safe_error = _safe_error_text(error, config)
        result["error"] = f"Не удалось подключиться к почте: {safe_error}"
        result["retryable"] = True
        append_mail_error("Проверка соединения", result["error"], config)
        return result
    except (TypeError, ValueError) as error:
        safe_error = _safe_error_text(error, config)
        result["error"] = f"Некорректные настройки почты: {safe_error}"
        append_mail_error("Проверка соединения", result["error"], config)
        return result

    result["ok"] = True
    return result


def _load_seen() -> list:
    return _read_json(SEEN_FILE, [])


def _save_seen(seen: list) -> None:
    _write_json(SEEN_FILE, seen[-SEEN_LIMIT:])


def _normalise_category_marker(value: str) -> str:
    return " ".join(
        re.findall(r"[0-9a-zа-я]+", str(value or "").casefold().replace("ё", "е"))
    )


def _normalise_invoice_categories(value) -> list[dict]:
    categories = []

    for category in value or []:
        if isinstance(category, str):
            name = category.strip()
            markers = ()
        elif isinstance(category, dict):
            name = str(category.get("name") or "").strip()
            markers = tuple(
                _normalise_category_marker(marker)
                for marker in category.get("markers") or []
                if _normalise_category_marker(marker)
            )
        else:
            continue

        if name and not any(item["name"] == name for item in categories):
            categories.append({"name": name, "markers": markers})

    return categories


def _category_matches(value: str, marker: str) -> bool:
    value = _normalise_category_marker(value)
    marker = _normalise_category_marker(marker)
    return marker in value or marker.replace(" ", "") in value.replace(" ", "")


def invoice_category(
    filename: str,
    categories=None,
    subject: str = "",
    kind: str = KIND_INVOICES,
) -> str:
    """Определяет категорию PDF сначала по теме письма, затем по имени файла."""

    if kind != KIND_INVOICES:
        return ""

    categories = _normalise_invoice_categories(categories)

    for value in (subject, Path(filename).stem):

        if not value:
            continue
        for category in categories:
            if any(
                _category_matches(value, marker)
                for marker in category["markers"]
            ):
                return category["name"]

    return ""


def _normalise_subject(value: str) -> str:
    return " ".join(str(value or "").split()).casefold()


def _subject_rejection(expected_subject: str, verdict: dict | None = None) -> dict:
    result = dict(verdict or {})
    result.update({
        "ok": False,
        "reason": f"Тема письма должна быть «{expected_subject}»",
    })
    result.setdefault("mode", "")
    result.setdefault("matches", 0)
    result.setdefault("scores", {})
    return result


def _enforce_order_subject(item: dict) -> None:
    if item.get("kind") != KIND_ORDERS:
        return

    expected_subject = item.get("expected_subject") or DEFAULT_ORDER_SUBJECT

    if _normalise_subject(item.get("subject", "")) != _normalise_subject(
        expected_subject
    ):
        item["verdict"] = _subject_rejection(
            expected_subject,
            item.get("verdict"),
        )


def load_mail_items() -> list[dict]:
    """Возвращает сохранённые письма и вложения, новые сверху."""

    items = _read_json(MAIL_ITEMS_FILE, [])

    # Старый кеш мог считать заказом любой подходящий Excel. Применяем новое
    # правило темы и к уже сохранённым письмам, не заставляя скачивать их снова.
    for item in items:
        _enforce_order_subject(item)

    return items


def _item_received_date(item: dict) -> date | None:
    """Возвращает календарную дату письма из нового или старого кеша."""

    try:
        return datetime.fromisoformat(str(item.get("received_at", ""))).date()
    except ValueError:
        pass

    try:
        return datetime.strptime(
            str(item.get("received_display", "")),
            "%d.%m.%Y %H:%M",
        ).date()
    except ValueError:
        return None


def _invoice_filename_group(filename: str) -> tuple[str, str]:
    """Определяет тип заказа и группу накладной по приблизительному имени."""

    name = Path(filename).stem.casefold().replace("ё", "е")
    name = " ".join(re.findall(r"[0-9a-zа-я]+", name))

    if re.search(r"\bфм\s*40\b", name) and re.search(r"\bмдв\b", name):
        return CITY_INVOICE_MODE, "ФМ 40 / МДВ"

    for group, markers in REGION_INVOICE_GROUPS.items():
        if any(marker in name for marker in markers):
            return REGION_INVOICE_MODE, group

    return "", ""


def split_invoice_candidates(
    items: list[dict],
    order_file: str,
) -> tuple[date | None, str, list[dict], list[dict]]:
    """Делит свободные накладные на подходящие по дате и типу заказа.

    Подходящими считаются PDF, полученные в календарный день заказа или
    на следующий день. Для города предлагается один файл «ФМ 40, МДВ»,
    для области — по одному файлу на каждую из трёх групп городов.
    """

    order_name = Path(order_file).name.casefold()
    order_item = next(
        (
            item
            for item in items
            if item.get("kind") == KIND_ORDERS
            and Path(str(item.get("file", ""))).name.casefold() == order_name
        ),
        None,
    )
    order_date = _item_received_date(order_item) if order_item else None
    order_mode = str(((order_item or {}).get("verdict") or {}).get("mode", ""))
    available = [
        item
        for item in items
        if item.get("kind") == KIND_INVOICES and not item.get("order_file")
    ]

    if order_date is None:
        return None, order_mode, [], available

    suggested = []
    other = []
    used_groups = set()

    for item in available:
        invoice_date = _item_received_date(item)
        day_offset = (invoice_date - order_date).days if invoice_date else None
        invoice_mode, invoice_group = _invoice_filename_group(
            str(item.get("file", ""))
        )
        mode_matches = not order_mode or invoice_mode == order_mode
        group_is_free = not order_mode or invoice_group not in used_groups

        if day_offset in (0, 1) and mode_matches and group_is_free:
            candidate = dict(item)
            candidate["date_relation"] = (
                "В день заказа" if day_offset == 0 else "На следующий день"
            )
            suggested.append(candidate)

            if order_mode:
                used_groups.add(invoice_group)
        else:
            other.append(item)

    suggested.sort(
        key=lambda item: (
            0 if item["date_relation"] == "В день заказа" else 1,
            str(item.get("received_at", "")),
        )
    )
    return order_date, order_mode, suggested, other


def _save_mail_items(items: list[dict]) -> None:
    _write_json(MAIL_ITEMS_FILE, items[:MAIL_ITEMS_LIMIT])


def _prune_mail_items(items: list[dict], days: int) -> list[dict]:
    """Удаляет устаревший почтовый кеш, сохраняя привязанные накладные."""

    cutoff = datetime.now().astimezone() - timedelta(days=max(days, 1))
    kept = []

    for item in items:
        if item.get("order_file"):
            kept.append(item)
            continue

        try:
            received = datetime.fromisoformat(item.get("received_at", ""))
            if received.tzinfo is None:
                received = received.astimezone()
        except (TypeError, ValueError):
            # Старые записи без машиночитаемой даты не удаляем автоматически.
            kept.append(item)
            continue

        if received >= cutoff:
            kept.append(item)

    return kept


def _mailbox_cache_key(config: dict, uidvalidity: str) -> str:
    return "|".join([
        str(config.get("imap_server", "")),
        str(config.get("email", "")),
        str(config.get("folder") or "INBOX"),
        uidvalidity,
    ])


def _load_uid_cache(cache_key: str) -> set[str]:
    cache = _read_json(MAIL_UID_CACHE_FILE, {})

    if cache.get("mailbox") != cache_key:
        return set()

    return {str(value) for value in cache.get("uids", [])}


def _save_uid_cache(cache_key: str, uids: set[str]) -> None:
    _write_json(MAIL_UID_CACHE_FILE, {
        "mailbox": cache_key,
        "uids": sorted(uids),
        "updated_at": datetime.now().astimezone().isoformat(),
    })


def _uidvalidity(imap) -> str:
    try:
        _name, values = imap.response("UIDVALIDITY")
        if values and values[0]:
            value = values[0]
            return value.decode() if isinstance(value, bytes) else str(value)
    except (AttributeError, imaplib.IMAP4.error):
        pass

    return "unknown"


def _search_uids(imap, since: str, email_addr: str):
    """Ищет стабильные UID; старые тестовые IMAP-адаптеры поддерживаются."""

    if hasattr(imap, "uid"):
        return imap.uid("SEARCH", None, "SINCE", since, "FROM", f'"{email_addr}"')

    return imap.search(None, "SINCE", since, "FROM", f'"{email_addr}"')


def _fetch_message(imap, uid):
    if hasattr(imap, "uid"):
        return imap.uid("FETCH", uid, "(RFC822)")

    return imap.fetch(uid, "(RFC822)")


def _message_bytes(data) -> bytes | None:
    for part in data or []:
        if isinstance(part, tuple) and len(part) > 1 and isinstance(part[1], bytes):
            return part[1]

    return None


def link_invoice(path: str, order_file: str) -> bool:
    """Привязывает PDF-накладную к заказу по имени обработанного файла."""

    items = load_mail_items()

    for item in items:
        if item.get("path") == path and item.get("kind") == KIND_INVOICES:
            item["order_file"] = order_file
            _save_mail_items(items)
            return True

    return False


def unlink_invoice(path: str) -> bool:
    items = load_mail_items()

    for item in items:
        if item.get("path") == path and item.get("kind") == KIND_INVOICES:
            item["order_file"] = ""
            _save_mail_items(items)
            return True

    return False


def _decode(value: str) -> str:
    if not value:
        return ""

    try:
        return str(make_header(decode_header(value)))
    except (UnicodeDecodeError, LookupError, ValueError):
        return value


def _safe_name(name: str) -> str:
    name = Path(name).name
    name = re.sub(r'[<>:"/\\|?*\x00-\x1f]', "_", name)
    return name.strip(" .") or "вложение.xlsx"


def _unique_path(folder: Path, filename: str) -> Path:
    path = folder / filename

    if not path.exists():
        return path

    stem, suffix = path.stem, path.suffix
    counter = 2

    while path.exists():
        path = folder / f"{stem} ({counter}){suffix}"
        counter += 1

    return path


def _search_date(days: int) -> str:
    day = datetime.now() - timedelta(days=max(days, 1))
    return f"{day.day:02d}-{_MONTHS[day.month - 1]}-{day.year}"


def _received_at(message) -> tuple[str, str]:
    """Возвращает ISO-время и короткое отображение даты письма."""

    try:
        value = parsedate_to_datetime(message.get("Date", ""))
        if value is None:
            raise ValueError
        value = value.astimezone()
    except (TypeError, ValueError, OverflowError):
        value = datetime.now().astimezone()

    return value.isoformat(), value.strftime("%d.%m.%Y %H:%M")


def _attachments(message, suffixes=ALLOWED_SUFFIXES) -> list[tuple[str, bytes]]:
    found = []

    for part in message.walk():
        if part.get_content_maintype() == "multipart":
            continue

        filename = _decode(part.get_filename() or "")

        if not filename or Path(filename).suffix.lower() not in suffixes:
            continue

        payload = part.get_payload(decode=True)

        if payload:
            found.append((_safe_name(filename), payload))

    return found


def _base_item(message, source: dict, message_id: str) -> dict:
    received_at, received_display = _received_at(message)
    return {
        "message_id": message_id,
        "sender": _decode(message.get("From", "")),
        "subject": _decode(message.get("Subject", "")),
        "received_at": received_at,
        "received_display": received_display,
        "source_name": source["name"],
        "source_email": source["email"],
        "source_person": source.get("person", ""),
        "expected_subject": source.get("subject", ""),
        "order_file": "",
    }


def check_mail(config: dict | None = None) -> dict:
    """Обновляет локальный кеш писем и скачивает только ещё не виденные UID."""

    config = config or load_mail_config()
    result = {"ok": False, "error": "", "items": [], "retryable": False}

    if not is_configured(config):
        result["error"] = "Почта не настроена — заполните config/mail.json"
        append_mail_error("Проверка почты", result["error"], config)
        return result

    seen = _load_seen()
    new_seen = list(seen)
    cache_days = int(config.get("cache_days", DEFAULT_CACHE_DAYS))
    stored_items = _prune_mail_items(load_mail_items(), cache_days)
    stored_message_ids = {
        item.get("message_id") for item in stored_items if item.get("message_id")
    }

    try:
        with imaplib.IMAP4_SSL(config["imap_server"], int(config["imap_port"])) as imap:
            imap.login(config["email"], config["app_password"])
            imap.select(config.get("folder") or "INBOX", readonly=True)

            since_days = min(int(config.get("since_days", cache_days)), cache_days)
            since = _search_date(since_days)
            cache_key = _mailbox_cache_key(config, _uidvalidity(imap))
            cached_uids = _load_uid_cache(cache_key)
            active_uids = set()
            uid_sources = {}

            for source in sources(config):
                status, data = _search_uids(imap, since, source["email"])

                if status != "OK" or not data:
                    continue

                for uid in data[0].split():
                    uid_value = uid.decode() if isinstance(uid, bytes) else str(uid)
                    uid_key = f'{source["email"]}|{source.get("kind", KIND_ORDERS)}|{uid_value}'
                    active_uids.add(uid_key)

                    if uid_key not in cached_uids:
                        uid_sources[uid] = (source, uid_key)

            ORDERS_FOLDER.mkdir(parents=True, exist_ok=True)
            INVOICES_FOLDER.mkdir(parents=True, exist_ok=True)
            completed_uids = cached_uids & active_uids

            for uid, (source, uid_key) in uid_sources.items():
                status, data = _fetch_message(imap, uid)
                raw_message = _message_bytes(data)

                if status != "OK" or raw_message is None:
                    continue

                message = email.message_from_bytes(raw_message)
                uid_value = uid.decode() if isinstance(uid, bytes) else str(uid)
                message_id = message.get("Message-ID") or f"uid:{uid_value}"

                # Если запись уже есть в локальном кеше, вложение скачивать повторно
                # не нужно. UID всё равно запоминаем для быстрых следующих проверок.
                if message_id in stored_message_ids:
                    completed_uids.add(uid_key)
                    continue

                base = _base_item(message, source, message_id)
                kind = source.get("kind", KIND_ORDERS)
                suffixes = PDF_SUFFIXES if kind == KIND_INVOICES else ALLOWED_SUFFIXES
                attachments = _attachments(message, suffixes)
                letter_items = []

                for filename, payload in attachments:
                    folder = INVOICES_FOLDER if kind == KIND_INVOICES else ORDERS_FOLDER
                    path = _unique_path(folder, filename)
                    path.write_bytes(payload)

                    item = {
                        **base,
                        "file": path.name,
                        "path": str(path),
                        "kind": kind,
                    }

                    if kind == KIND_ORDERS:
                        expected_subject = source.get("subject") or DEFAULT_ORDER_SUBJECT

                        if _normalise_subject(base["subject"]) != _normalise_subject(
                            expected_subject
                        ):
                            item["verdict"] = _subject_rejection(expected_subject)
                        else:
                            item["verdict"] = validate_order_file(path)

                    letter_items.append(item)

                if not letter_items:
                    letter_items.append({
                        **base,
                        "file": "",
                        "path": "",
                        "kind": KIND_MESSAGE,
                    })

                result["items"].extend(letter_items)
                stored_items = letter_items + stored_items
                stored_message_ids.add(message_id)
                completed_uids.add(uid_key)

                if message_id not in new_seen:
                    new_seen.append(message_id)

            _save_uid_cache(cache_key, completed_uids)

    except imaplib.IMAP4.error as error:
        safe_error = _safe_error_text(error, config)
        result["error"] = f"Почтовый сервер отказал: {safe_error}"
        result["retryable"] = _imap_error_is_retryable(error)
        append_mail_error("Проверка почты", result["error"], config)
        return result
    except (OSError, TimeoutError) as error:
        safe_error = _safe_error_text(error, config)
        result["error"] = f"Не удалось подключиться к почте: {safe_error}"
        result["retryable"] = True
        append_mail_error("Проверка почты", result["error"], config)
        return result
    except (TypeError, ValueError) as error:
        safe_error = _safe_error_text(error, config)
        result["error"] = f"Некорректные настройки почты: {safe_error}"
        append_mail_error("Проверка почты", result["error"], config)
        return result

    _save_mail_items(stored_items)

    if new_seen != seen:
        _save_seen(new_seen)

    result["ok"] = True
    return result


def check_mail_with_retry(config: dict | None = None) -> dict:
    """Повторяет автоматическую проверку только при временных сбоях."""

    config = config or load_mail_config()
    max_attempts, delay = _retry_settings(config)
    result = {"ok": False, "error": "", "items": [], "retryable": False}

    for attempt in range(1, max_attempts + 1):
        result = check_mail(config)
        result["attempts"] = attempt

        if result.get("ok") or not result.get("retryable") or attempt == max_attempts:
            return result

        if delay:
            time.sleep(delay)

    return result
