"""Проверка почты: ищет письма от заданных отправителей с вложением-заказом.

Работает только на чтение: почтовый ящик открывается в режиме readonly,
письма не помечаются прочитанными и не удаляются. Чтобы не скачивать одно
и то же письмо повторно, обработанные идентификаторы запоминаются в
data/mail_seen.json.

Вложение скачивается, но не обрабатывается автоматически — сначала оно
проходит проверку modules.order_validator, и решение принимает человек.
"""

import email
import imaplib
import json
import re
from datetime import datetime, timedelta
from email.header import decode_header, make_header
from pathlib import Path

from modules.order_validator import ALLOWED_SUFFIXES, validate_order_file
from modules.paths import CONFIG_DIR, DATA_DIR, ORDERS_FOLDER


MAIL_CONFIG_FILE = CONFIG_DIR / "mail.json"
SEEN_FILE = DATA_DIR / "mail_seen.json"

# Сколько идентификаторов писем помним, чтобы файл не рос бесконечно.
SEEN_LIMIT = 500

# IMAP ждёт дату вида 12-Aug-2026 по-английски. strftime("%b") зависит от
# локали системы, поэтому месяц подставляем вручную.
_MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]

DEFAULT_CONFIG = {
    "enabled": False,
    "imap_server": "imap.gmail.com",
    "imap_port": 993,
    "email": "",
    "app_password": "",
    "senders": [],
    "folder": "INBOX",
    "since_days": 7,
    "check_interval_minutes": 10,
}


def load_mail_config() -> dict:
    config = dict(DEFAULT_CONFIG)

    try:
        config.update(json.loads(MAIL_CONFIG_FILE.read_text(encoding="utf-8")))
    except (OSError, json.JSONDecodeError):
        pass

    return config


def is_configured(config: dict | None = None) -> bool:
    config = config or load_mail_config()

    return bool(
        config.get("enabled")
        and config.get("email")
        and config.get("app_password")
        and config.get("senders")
    )


def _load_seen() -> list:
    try:
        return json.loads(SEEN_FILE.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return []


def _save_seen(seen: list) -> None:
    SEEN_FILE.parent.mkdir(parents=True, exist_ok=True)
    SEEN_FILE.write_text(
        json.dumps(seen[-SEEN_LIMIT:], ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def _decode(value: str) -> str:
    """Раскодирует заголовок письма (Subject, имя файла) в читаемый вид."""

    if not value:
        return ""

    try:
        return str(make_header(decode_header(value)))
    except (UnicodeDecodeError, LookupError, ValueError):
        return value


def _safe_name(name: str) -> str:
    """Имя файла из письма приходит извне — вычищаем всё, чем можно навредить."""

    name = Path(name).name                      # убираем любые пути
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


def _attachments(message) -> list[tuple[str, bytes]]:
    found = []

    for part in message.walk():
        if part.get_content_maintype() == "multipart":
            continue

        filename = _decode(part.get_filename() or "")

        if not filename:
            continue

        if Path(filename).suffix.lower() not in ALLOWED_SUFFIXES:
            continue

        payload = part.get_payload(decode=True)

        if payload:
            found.append((_safe_name(filename), payload))

    return found


def check_mail(config: dict | None = None) -> dict:
    """Забирает новые вложения-заказы.

    Возвращает {"ok": bool, "error": str, "items": [...]}, где каждый item —
    {"file", "path", "sender", "subject", "verdict"}.
    """

    config = config or load_mail_config()
    result = {"ok": False, "error": "", "items": []}

    if not is_configured(config):
        result["error"] = "Почта не настроена — заполните config/mail.json"
        return result

    seen = _load_seen()
    new_seen = list(seen)

    try:
        with imaplib.IMAP4_SSL(config["imap_server"], int(config["imap_port"])) as imap:
            imap.login(config["email"], config["app_password"])

            # readonly: письма не помечаются прочитанными
            imap.select(config.get("folder") or "INBOX", readonly=True)

            since = _search_date(int(config.get("since_days", 7)))
            uids = []

            for sender in config["senders"]:
                status, data = imap.search(None, "SINCE", since, "FROM", f'"{sender}"')

                if status == "OK":
                    uids.extend(data[0].split())

            ORDERS_FOLDER.mkdir(parents=True, exist_ok=True)

            for uid in uids:
                key = uid.decode() if isinstance(uid, bytes) else str(uid)

                status, data = imap.fetch(uid, "(RFC822)")

                if status != "OK" or not data or not data[0]:
                    continue

                message = email.message_from_bytes(data[0][1])
                message_id = message.get("Message-ID") or f"uid:{key}"

                if message_id in seen:
                    continue

                sender = _decode(message.get("From", ""))
                subject = _decode(message.get("Subject", ""))
                attachments = _attachments(message)

                if not attachments:
                    continue

                for filename, payload in attachments:
                    path = _unique_path(ORDERS_FOLDER, filename)
                    path.write_bytes(payload)

                    result["items"].append({
                        "file": path.name,
                        "path": str(path),
                        "sender": sender,
                        "subject": subject,
                        "verdict": validate_order_file(path),
                    })

                new_seen.append(message_id)

    except imaplib.IMAP4.error as error:
        result["error"] = f"Почтовый сервер отказал: {error}"
        return result
    except (OSError, ValueError) as error:
        result["error"] = f"Не удалось подключиться к почте: {error}"
        return result

    if new_seen != seen:
        _save_seen(new_seen)

    result["ok"] = True
    return result
