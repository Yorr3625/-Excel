import json
from datetime import datetime, timedelta

import pytest

from modules import mail_watcher


@pytest.fixture(autouse=True)
def _isolated(tmp_path, monkeypatch):
    monkeypatch.setattr(mail_watcher, "MAIL_CONFIG_FILE", tmp_path / "mail.json")
    monkeypatch.setattr(
        mail_watcher,
        "MAIL_EXAMPLE_CONFIG_FILE",
        tmp_path / "mail.example.json",
    )
    monkeypatch.setattr(mail_watcher, "SEEN_FILE", tmp_path / "mail_seen.json")
    monkeypatch.setattr(mail_watcher, "MAIL_ITEMS_FILE", tmp_path / "mail_items.json")
    monkeypatch.setattr(mail_watcher, "MAIL_UID_CACHE_FILE", tmp_path / "mail_uid_cache.json")
    monkeypatch.setattr(mail_watcher, "MAIL_ERROR_LOG_FILE", tmp_path / "mail_errors.json")
    monkeypatch.setattr(mail_watcher, "ORDERS_FOLDER", tmp_path / "orders")
    monkeypatch.setattr(mail_watcher, "INVOICES_FOLDER", tmp_path / "invoices")


def _write_example_sources():
    mail_watcher.MAIL_EXAMPLE_CONFIG_FILE.write_text(
        json.dumps({
            "sources": [{
                "name": "Заказы",
                "email": "orders@example.com",
                "kind": "orders",
            }],
        }),
        encoding="utf-8",
    )


def _config(**overrides):
    config = {
        "enabled": True,
        "imap_server": "imap.gmail.com",
        "imap_port": 993,
        "email": "me@gmail.com",
        "app_password": "secret",
        "senders": ["boss@example.com"],
        "folder": "INBOX",
        "since_days": 7,
    }
    config.update(overrides)
    return config


def test_missing_config_falls_back_to_defaults():
    config = mail_watcher.load_mail_config()

    assert config["imap_server"] == "imap.gmail.com"
    assert config["enabled"] is False


def test_broken_config_does_not_crash():
    mail_watcher.MAIL_CONFIG_FILE.write_text("{сломано", encoding="utf-8")

    assert mail_watcher.load_mail_config()["enabled"] is False


def test_sources_add_categories_and_olga_to_legacy_mail_config():
    configured = mail_watcher.sources({
        "sources": [
            {
                "name": "Молоко",
                "email": mail_watcher.DEFAULT_MILK_ORDER_EMAIL,
                "kind": "orders",
            },
            {
                "name": "Бухгалтер",
                "email": "zosya-c@mail.ru",
                "kind": "invoices",
            },
            {
                "name": "Старый источник",
                "email": "old@example.com",
                "kind": "invoices",
            },
        ],
    })

    assert configured[0]["categories"] == []
    assert configured[1]["categories"] == [
        {"name": "Молоко", "markers": ("фм 40", "фм40", "мдв")},
        {"name": "Парус", "markers": ("парус",)},
        {"name": "Краймери", "markers": ("краймер", "краймар")},
    ]
    assert configured[2]["categories"] == []
    assert configured[3] == mail_watcher.OLGA_ORDER_SOURCE


def test_empty_config_does_not_add_mail_sources():
    assert mail_watcher.sources({}) == []


def test_invoice_category_prefers_subject_and_uses_filename_as_fallback():
    categories = [
        {"name": "Молоко", "markers": ["фм 40", "мдв"]},
        {"name": "Парус", "markers": ["парус"]},
        {"name": "Краймери", "markers": ["краймар", "краймери"]},
    ]

    assert mail_watcher.invoice_category(
        "накладная.pdf", categories, "ПАРУС на завтра"
    ) == "Парус"
    assert mail_watcher.invoice_category(
        "ФМ40, МДВ.pdf", categories
    ) == "Молоко"
    assert mail_watcher.invoice_category(
        "КРАЙМАР 01.pdf", categories
    ) == "Краймери"
    assert mail_watcher.invoice_category("накладная.pdf", categories) == ""
    assert mail_watcher.invoice_category(
        "", categories, "Спецификация ПАРУС.xls", mail_watcher.KIND_MESSAGE
    ) == ""


def test_save_credentials_normalises_key_and_uses_template_sources():
    _write_example_sources()

    ok, message = mail_watcher.save_mail_credentials(
        "  me@example.com ",
        "abcd efgh ijkl mnop",
    )

    assert ok
    assert message == "Данные почты сохранены"
    saved = mail_watcher.load_mail_config()
    assert saved["enabled"] is True
    assert saved["email"] == "me@example.com"
    assert saved["app_password"] == "abcdefghijklmnop"
    assert saved["sources"][0]["email"] == "orders@example.com"


def test_save_credentials_rejects_missing_values():
    _write_example_sources()

    ok, message = mail_watcher.save_mail_credentials("", "secret")
    assert not ok
    assert message == "Введите адрес электронной почты"

    ok, message = mail_watcher.save_mail_credentials("me@example.com", "")
    assert not ok
    assert message == "Введите ключ приложения"
    assert not mail_watcher.MAIL_CONFIG_FILE.exists()


def test_save_credentials_keeps_existing_key_when_edit_field_is_empty():
    _write_example_sources()
    first_ok, _ = mail_watcher.save_mail_credentials("old@example.com", "old key")
    assert first_ok

    second_ok, _ = mail_watcher.save_mail_credentials("new@example.com", "")

    assert second_ok
    saved = mail_watcher.load_mail_config()
    assert saved["email"] == "new@example.com"
    assert saved["app_password"] == "oldkey"


@pytest.mark.parametrize(
    "overrides",
    [
        {"enabled": False},
        {"email": ""},
        {"app_password": ""},
        {"senders": []},
    ],
)
def test_incomplete_config_is_not_ready(overrides):
    assert not mail_watcher.is_configured(_config(**overrides))


def test_full_config_is_ready():
    assert mail_watcher.is_configured(_config())


def test_check_mail_reports_missing_setup_instead_of_connecting():
    result = mail_watcher.check_mail(_config(enabled=False))

    assert not result["ok"]
    assert "не настроена" in result["error"]


def test_filename_from_letter_cannot_escape_orders_folder():
    """Имя вложения приходит извне и попадает в путь — его нужно чистить."""

    assert mail_watcher._safe_name("../../../evil.xlsx") == "evil.xlsx"
    assert mail_watcher._safe_name("C:\\Windows\\system.xlsx") == "system.xlsx"
    assert "/" not in mail_watcher._safe_name("a/b/c.xlsx")
    assert mail_watcher._safe_name("") == "вложение.xlsx"
    assert mail_watcher._safe_name("..") == "вложение.xlsx"


def test_unique_path_does_not_overwrite_existing_order(tmp_path):
    folder = tmp_path / "orders"
    folder.mkdir()
    (folder / "заказ.xlsx").write_text("первый", encoding="utf-8")

    path = mail_watcher._unique_path(folder, "заказ.xlsx")

    assert path.name == "заказ (2).xlsx"
    assert (folder / "заказ.xlsx").read_text(encoding="utf-8") == "первый"


def test_search_date_uses_english_month():
    """IMAP не понимает названия месяцев в локали системы."""

    date = mail_watcher._search_date(1)
    month = date.split("-")[1]

    assert month in mail_watcher._MONTHS


def test_seen_ids_survive_roundtrip():
    mail_watcher._save_seen(["<a@mail>", "<b@mail>"])

    assert mail_watcher._load_seen() == ["<a@mail>", "<b@mail>"]


def test_seen_list_is_capped(monkeypatch):
    monkeypatch.setattr(mail_watcher, "SEEN_LIMIT", 3)

    mail_watcher._save_seen([f"<{i}@mail>" for i in range(10)])

    seen = mail_watcher._load_seen()

    assert len(seen) == 3
    assert seen[-1] == "<9@mail>"


def test_broken_seen_file_does_not_crash():
    mail_watcher.SEEN_FILE.parent.mkdir(parents=True, exist_ok=True)
    mail_watcher.SEEN_FILE.write_text("не json", encoding="utf-8")

    assert mail_watcher._load_seen() == []


def test_decode_handles_encoded_subject():
    encoded = "=?utf-8?b?0JfQsNC60LDQtw==?="

    assert mail_watcher._decode(encoded) == "Заказ"


def test_decode_survives_broken_header():
    assert mail_watcher._decode("обычный текст") == "обычный текст"
    assert mail_watcher._decode("") == ""


class _FakePart:
    def __init__(self, filename, payload, maintype="application"):
        self._filename = filename
        self._payload = payload
        self._maintype = maintype

    def get_content_maintype(self):
        return self._maintype

    def get_filename(self):
        return self._filename

    def get_payload(self, decode=False):
        return self._payload


class _FakeMessage:
    def __init__(self, parts):
        self._parts = parts

    def walk(self):
        return self._parts


def test_only_excel_attachments_are_taken():
    """Из письма забираем только таблицы: подпись, картинка, pdf — мимо."""

    message = _FakeMessage([
        _FakePart(None, None, maintype="multipart"),
        _FakePart("заказ.xlsx", b"xlsx"),
        _FakePart("подпись.png", b"png"),
        _FakePart("накладная.pdf", b"pdf"),
        _FakePart("данные.xlsm", b"xlsm"),
        _FakePart("старый.xls", b"xls"),
        _FakePart("бинарный.xlsb", b"xlsb"),
        _FakePart("шаблон.xltx", b"xltx"),
        _FakePart("макро-шаблон.xltm", b"xltm"),
        _FakePart(None, b"message body"),
    ])

    found = mail_watcher._attachments(message)

    assert [name for name, _ in found] == [
        "заказ.xlsx",
        "данные.xlsm",
        "старый.xls",
        "бинарный.xlsb",
        "шаблон.xltx",
        "макро-шаблон.xltm",
    ]


def test_excel_attachment_suffix_matching_is_case_insensitive():
    message = _FakeMessage([_FakePart("ЗАКАЗ.XLSB", b"xlsb")])

    assert mail_watcher._attachments(message)[0][0] == "ЗАКАЗ.XLSB"


def test_attachment_name_is_sanitised_on_extraction():
    message = _FakeMessage([_FakePart("../../evil.xlsx", b"xlsx")])

    found = mail_watcher._attachments(message)

    assert found[0][0] == "evil.xlsx"


# --- сквозная проверка с поддельным IMAP ---


def _letter_with_attachment(
    filename: str,
    payload: bytes,
    sender="boss@example.com",
    subject=mail_watcher.DEFAULT_ORDER_SUBJECT,
):
    """Собирает настоящее письмо MIME с вложением.

    Политика SMTP нужна, чтобы кириллица в теме и имени файла кодировалась
    по RFC 2047 — именно в таком виде письма и приходят с почтового сервера.
    """

    from email.message import EmailMessage
    from email.policy import SMTP

    message = EmailMessage(policy=SMTP)
    message["From"] = sender
    message["To"] = "me@gmail.com"
    message["Subject"] = subject
    # Message-ID — структурный заголовок, кириллицу в него класть нельзя
    message["Message-ID"] = f"<{abs(hash(filename))}@example.com>"
    message.set_content("Файл во вложении")
    message.add_attachment(
        payload,
        maintype="application",
        subtype="vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        filename=filename,
    )

    return message


class _FakeIMAP:
    """Минимальный IMAP-сервер, отдающий заранее заданные письма."""

    def __init__(self, letters):
        self._letters = letters
        self.readonly_used = None
        self.logged_in = False
        self.fetch_calls = 0
        self.search_calls = 0

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False

    def login(self, email_addr, password):
        self.logged_in = True
        return "OK", [b""]

    def select(self, folder, readonly=False):
        self.readonly_used = readonly
        return "OK", [b"1"]

    def response(self, name):
        return name, [b"12345"]

    def uid(self, command, *args):
        if command == "SEARCH":
            return self.search(*args)
        if command == "FETCH":
            return self.fetch(*args)
        raise AssertionError(f"Неожиданная UID-команда: {command}")

    def search(self, charset, *criteria):
        self.search_calls += 1
        return "OK", [b" ".join(str(i + 1).encode() for i in range(len(self._letters)))]

    def fetch(self, uid, spec):
        self.fetch_calls += 1
        index = int(uid) - 1
        return "OK", [(b"", self._letters[index].as_bytes())]


def test_check_connection_logs_in_without_searching(monkeypatch):
    fake = _FakeIMAP([])
    monkeypatch.setattr(mail_watcher.imaplib, "IMAP4_SSL", lambda *a, **kw: fake)

    result = mail_watcher.check_mail_connection(_config())

    assert result == {"ok": True, "error": "", "retryable": False}
    assert fake.logged_in is True
    assert fake.readonly_used is True
    assert fake.search_calls == 0
    assert fake.fetch_calls == 0


def test_check_connection_does_not_retry_authentication_error(monkeypatch):
    class AuthenticationFailure(_FakeIMAP):
        def login(self, email_addr, password):
            raise mail_watcher.imaplib.IMAP4.error("AUTHENTICATIONFAILED")

    monkeypatch.setattr(
        mail_watcher.imaplib,
        "IMAP4_SSL",
        lambda *a, **kw: AuthenticationFailure([]),
    )

    result = mail_watcher.check_mail_connection(_config())

    assert result["ok"] is False
    assert result["retryable"] is False
    assert len(mail_watcher.load_mail_error_log()) == 1


def test_mail_retry_stops_after_success(monkeypatch):
    calls = []
    sleeps = []

    def fake_check(config):
        calls.append(config)
        if len(calls) < 3:
            return {
                "ok": False,
                "error": "временный сбой",
                "items": [],
                "retryable": True,
            }
        return {"ok": True, "error": "", "items": [], "retryable": False}

    monkeypatch.setattr(mail_watcher, "check_mail", fake_check)
    monkeypatch.setattr(mail_watcher.time, "sleep", sleeps.append)

    result = mail_watcher.check_mail_with_retry(
        _config(retry_attempts=5, retry_delay_seconds=0.25)
    )

    assert result["ok"] is True
    assert result["attempts"] == 3
    assert len(calls) == 3
    assert sleeps == [0.25, 0.25]


def test_mail_retry_does_not_repeat_permanent_error(monkeypatch):
    calls = []

    def fake_check(config):
        calls.append(config)
        return {
            "ok": False,
            "error": "неверный пароль",
            "items": [],
            "retryable": False,
        }

    monkeypatch.setattr(mail_watcher, "check_mail", fake_check)

    result = mail_watcher.check_mail_with_retry(_config(retry_attempts=5))

    assert result["attempts"] == 1
    assert len(calls) == 1


def test_mail_error_log_masks_credentials_limits_and_clears(monkeypatch):
    monkeypatch.setattr(mail_watcher, "MAIL_ERROR_LOG_LIMIT", 2)
    config = _config(email="private@example.com", app_password="top secret")

    for index in range(3):
        mail_watcher.append_mail_error(
            "Проверка",
            f"Ошибка {index}: private@example.com / top secret / topsecret",
            config,
        )

    entries = mail_watcher.load_mail_error_log()
    combined = json.dumps(entries, ensure_ascii=False)

    assert len(entries) == 2
    assert entries[0]["error"].startswith("Ошибка 2")
    assert "private@example.com" not in combined
    assert "top secret" not in combined
    assert "topsecret" not in combined
    assert "***" in combined

    mail_watcher.clear_mail_error_log()

    assert mail_watcher.load_mail_error_log() == []


def _order_xlsx_bytes(stores):
    """xlsx со структурой заказа (строка 2 и столбцы 2-3 — служебные)."""

    import io

    from openpyxl import Workbook

    wb = Workbook()
    ws = wb.active
    ws.append(["Товар", "служебный1", "служебный2", *stores])
    ws.append(["служебная строка", "", "", *[""] * len(stores)])
    ws.append(["Товар A", "", "", *[1] * len(stores)])

    buffer = io.BytesIO()
    wb.save(buffer)
    return buffer.getvalue()


@pytest.fixture
def _stores_for_validation(tmp_path, monkeypatch):
    from modules import order_validator

    region = tmp_path / "stores_region.json"
    city = tmp_path / "stores_city.json"

    region.write_text(
        json.dumps({"route_1": ["фм 10", "фм 14", "фм 17"], "route_2": [], "route_3": [], "route_4": []}),
        encoding="utf-8",
    )
    city.write_text(
        json.dumps({"route_1": [], "route_2": [], "route_3": [], "route_4": []}),
        encoding="utf-8",
    )

    monkeypatch.setattr(
        order_validator,
        "stores_file_for",
        lambda mode: city if mode == "Город" else region,
    )


def test_order_from_letter_is_saved_and_accepted(monkeypatch, _stores_for_validation):
    letter = _letter_with_attachment("заказ.xlsx", _order_xlsx_bytes(["фм 10", "фм 14", "фм 17"]))
    fake = _FakeIMAP([letter])

    monkeypatch.setattr(mail_watcher.imaplib, "IMAP4_SSL", lambda *a, **kw: fake)

    result = mail_watcher.check_mail(_config())

    assert result["ok"], result["error"]
    assert len(result["items"]) == 1

    item = result["items"][0]
    assert item["file"] == "заказ.xlsx"
    assert item["verdict"]["ok"]
    assert item["verdict"]["mode"] == "Область"
    assert (mail_watcher.ORDERS_FOLDER / "заказ.xlsx").exists()

    # почтовый ящик открыт только на чтение — письма не помечаются прочитанными
    assert fake.readonly_used is True


def test_valid_excel_with_wrong_subject_is_not_order(monkeypatch, _stores_for_validation):
    letter = _letter_with_attachment(
        "заказ.xlsx",
        _order_xlsx_bytes(["фм 10", "фм 14", "фм 17"]),
        subject="Заказ на завтра",
    )
    monkeypatch.setattr(
        mail_watcher.imaplib,
        "IMAP4_SSL",
        lambda *a, **kw: _FakeIMAP([letter]),
    )

    result = mail_watcher.check_mail(_config())

    assert result["ok"]
    item = result["items"][0]
    assert not item["verdict"]["ok"]
    assert item["verdict"]["reason"] == (
        "Тема письма должна быть «Заказ ТС МОЛОКО»"
    )
    assert (mail_watcher.ORDERS_FOLDER / "заказ.xlsx").exists()


def test_order_subject_ignores_case_and_repeated_spaces(
    monkeypatch,
    _stores_for_validation,
):
    letter = _letter_with_attachment(
        "заказ.xlsx",
        _order_xlsx_bytes(["фм 10", "фм 14", "фм 17"]),
        subject="заказ   тс молоко",
    )
    monkeypatch.setattr(
        mail_watcher.imaplib,
        "IMAP4_SSL",
        lambda *a, **kw: _FakeIMAP([letter]),
    )

    result = mail_watcher.check_mail(_config())

    assert result["ok"]
    assert result["items"][0]["verdict"]["ok"]


def test_foreign_excel_from_letter_is_saved_but_marked_not_order(monkeypatch, _stores_for_validation):
    """Прислали Excel, но не заказ — файл виден, однако помечен как непригодный."""

    import io

    from openpyxl import Workbook

    wb = Workbook()
    ws = wb.active
    ws.append(["Наименование", "Цена"])
    ws.append(["Гвозди", 100])
    buffer = io.BytesIO()
    wb.save(buffer)

    letter = _letter_with_attachment("прайс.xlsx", buffer.getvalue())
    monkeypatch.setattr(mail_watcher.imaplib, "IMAP4_SSL", lambda *a, **kw: _FakeIMAP([letter]))

    result = mail_watcher.check_mail(_config())

    assert result["ok"]
    assert len(result["items"]) == 1
    assert not result["items"][0]["verdict"]["ok"]
    assert "Не похоже на заказ" in result["items"][0]["verdict"]["reason"]


def test_same_letter_is_not_downloaded_twice(monkeypatch, _stores_for_validation):
    letter = _letter_with_attachment("заказ.xlsx", _order_xlsx_bytes(["фм 10", "фм 14", "фм 17"]))
    fake = _FakeIMAP([letter])
    monkeypatch.setattr(mail_watcher.imaplib, "IMAP4_SSL", lambda *a, **kw: fake)

    first = mail_watcher.check_mail(_config())
    second = mail_watcher.check_mail(_config())

    assert len(first["items"]) == 1
    assert second["items"] == []
    assert fake.fetch_calls == 1


def test_seen_letter_missing_from_cache_is_restored(monkeypatch, _stores_for_validation):
    """Старый mail_seen не должен скрывать письмо, которого нет в mail_items."""

    letter = _letter_with_attachment("заказ.xlsx", _order_xlsx_bytes(["фм 10", "фм 14", "фм 17"]))
    message_id = letter["Message-ID"]
    mail_watcher._save_seen([message_id])
    monkeypatch.setattr(
        mail_watcher.imaplib,
        "IMAP4_SSL",
        lambda *a, **kw: _FakeIMAP([letter]),
    )

    result = mail_watcher.check_mail(_config())

    assert result["ok"]
    assert len(result["items"]) == 1
    assert mail_watcher.load_mail_items()[0]["message_id"] == message_id


def test_mail_cache_removes_old_messages_but_keeps_linked_invoices():
    now = datetime.now().astimezone()
    recent = (now - timedelta(days=2)).isoformat()
    old = (now - timedelta(days=30)).isoformat()
    items = [
        {"message_id": "recent", "received_at": recent, "order_file": ""},
        {"message_id": "old", "received_at": old, "order_file": ""},
        {"message_id": "linked", "received_at": old, "order_file": "заказ.xlsx"},
    ]

    kept = mail_watcher._prune_mail_items(items, 14)

    assert [item["message_id"] for item in kept] == ["recent", "linked"]


def test_letter_without_attachment_is_kept_as_message(monkeypatch, _stores_for_validation):
    from email.message import EmailMessage

    from email.policy import SMTP

    message = EmailMessage(policy=SMTP)
    message["From"] = "boss@example.com"
    message["Subject"] = "Просто письмо"
    message["Message-ID"] = "<plain@example.com>"
    message.set_content("Без вложений")

    monkeypatch.setattr(mail_watcher.imaplib, "IMAP4_SSL", lambda *a, **kw: _FakeIMAP([message]))

    result = mail_watcher.check_mail(_config())

    assert result["ok"]
    assert len(result["items"]) == 1
    assert result["items"][0]["kind"] == mail_watcher.KIND_MESSAGE
    assert result["items"][0]["file"] == ""


def test_invoice_pdf_is_saved_with_received_date(monkeypatch):
    letter = _letter_with_attachment(
        "ФМ 40, МДВ.pdf",
        b"%PDF-1.4 invoice",
        sender="zosya-c@mail.ru",
        subject="",
    )
    letter["Date"] = "Fri, 14 Aug 2026 09:30:00 +0300"
    fake = _FakeIMAP([letter])
    monkeypatch.setattr(mail_watcher.imaplib, "IMAP4_SSL", lambda *a, **kw: fake)

    config = _config(
        senders=[],
        sources=[{
            "name": "Бухгалтер",
            "email": "zosya-c@mail.ru",
            "person": "Светлана Никифорова",
            "kind": "invoices",
        }],
    )
    result = mail_watcher.check_mail(config)

    assert result["ok"], result["error"]
    item = result["items"][0]
    assert item["kind"] == mail_watcher.KIND_INVOICES
    assert item["source_name"] == "Бухгалтер"
    assert item["source_person"] == "Светлана Никифорова"
    assert item["subject"] == ""
    assert item["received_display"] == "14.08.2026 09:30"
    assert (mail_watcher.INVOICES_FOLDER / "ФМ 40, МДВ.pdf").exists()


def test_city_invoice_candidates_use_name_date_and_one_group():
    items = [
        {
            "kind": "orders",
            "file": "заказ.xlsx",
            "received_at": "2026-11-10T18:30:00+03:00",
            "order_file": "",
            "verdict": {"ok": True, "mode": "Город"},
        },
        {
            "kind": "invoices",
            "file": "ФМ 40, МДВ 11.11.2026.pdf",
            "received_at": "2026-11-11T09:00:00+03:00",
            "order_file": "",
        },
        {
            "kind": "invoices",
            "file": "ФМ-40 МДВ дубль 10-11-2026.pdf",
            "received_at": "2026-11-10T20:00:00+03:00",
            "order_file": "",
        },
        {
            "kind": "invoices",
            "file": "Горловка 10.11.2026.pdf",
            "received_at": "2026-11-10T12:00:00+03:00",
            "order_file": "",
        },
        {
            "kind": "invoices",
            "file": "ФМ 40, МДВ 12.11.2026.pdf",
            "received_at": "2026-11-12T09:00:00+03:00",
            "order_file": "",
        },
        {
            "kind": "invoices",
            "file": "ФМ 40, МДВ уже привязана.pdf",
            "received_at": "2026-11-10T10:00:00+03:00",
            "order_file": "другой заказ.xlsx",
        },
    ]

    order_date, order_mode, suggested, other = (
        mail_watcher.split_invoice_candidates(items, "заказ.xlsx")
    )

    assert order_date.isoformat() == "2026-11-10"
    assert order_mode == "Город"
    assert [item["file"] for item in suggested] == [
        "ФМ 40, МДВ 11.11.2026.pdf",
    ]
    assert suggested[0]["date_relation"] == "На следующий день"
    assert [item["file"] for item in other] == [
        "ФМ-40 МДВ дубль 10-11-2026.pdf",
        "Горловка 10.11.2026.pdf",
        "ФМ 40, МДВ 12.11.2026.pdf",
    ]


def test_region_invoice_candidates_offer_at_most_three_groups():
    items = [
        {
            "kind": "orders",
            "file": "область.xlsx",
            "received_at": "2026-11-10T18:30:00+03:00",
            "order_file": "",
            "verdict": {"ok": True, "mode": "Область"},
        },
        {
            "kind": "invoices",
            "file": "Кировское, Торез, Шахтёрск 10.11.2026.pdf",
            "received_at": "2026-11-10T20:00:00+03:00",
            "order_file": "",
        },
        {
            "kind": "invoices",
            "file": "Горловка 11-11-2026.pdf",
            "received_at": "2026-11-11T09:00:00+03:00",
            "order_file": "",
        },
        {
            "kind": "invoices",
            "file": "Харцызск, Макеевка 10 ноября.pdf",
            "received_at": "2026-11-10T21:00:00+03:00",
            "order_file": "",
        },
        {
            "kind": "invoices",
            "file": "Горловка повторно.pdf",
            "received_at": "2026-11-10T22:00:00+03:00",
            "order_file": "",
        },
        {
            "kind": "invoices",
            "file": "ФМ 40, МДВ 10.11.2026.pdf",
            "received_at": "2026-11-10T12:00:00+03:00",
            "order_file": "",
        },
        {
            "kind": "invoices",
            "file": "неизвестная накладная.pdf",
            "received_at": "2026-11-10T12:30:00+03:00",
            "order_file": "",
        },
        {
            "kind": "invoices",
            "file": "Торез 12.11.2026.pdf",
            "received_at": "2026-11-12T09:00:00+03:00",
            "order_file": "",
        },
    ]

    order_date, order_mode, suggested, other = (
        mail_watcher.split_invoice_candidates(items, "область.xlsx")
    )

    assert order_date.isoformat() == "2026-11-10"
    assert order_mode == "Область"
    assert [item["file"] for item in suggested] == [
        "Кировское, Торез, Шахтёрск 10.11.2026.pdf",
        "Харцызск, Макеевка 10 ноября.pdf",
        "Горловка 11-11-2026.pdf",
    ]
    assert [item["date_relation"] for item in suggested] == [
        "В день заказа",
        "В день заказа",
        "На следующий день",
    ]
    assert [item["file"] for item in other] == [
        "Горловка повторно.pdf",
        "ФМ 40, МДВ 10.11.2026.pdf",
        "неизвестная накладная.pdf",
        "Торез 12.11.2026.pdf",
    ]


def test_invoice_candidates_show_all_when_order_date_is_unknown():
    items = [
        {
            "kind": "invoices",
            "file": "ФМ 40.pdf",
            "received_at": "2026-11-11T09:00:00+03:00",
            "order_file": "",
        },
    ]

    order_date, order_mode, suggested, other = (
        mail_watcher.split_invoice_candidates(items, "ручной заказ.xlsx")
    )

    assert order_date is None
    assert order_mode == ""
    assert suggested == []
    assert [item["file"] for item in other] == ["ФМ 40.pdf"]


def test_invoice_candidate_accepts_display_date_from_old_cache():
    items = [
        {
            "kind": "orders",
            "file": "заказ.xlsx",
            "received_display": "10.11.2026 18:30",
            "order_file": "",
        },
        {
            "kind": "invoices",
            "file": "МДВ.pdf",
            "received_display": "11.11.2026 09:00",
            "order_file": "",
        },
    ]

    order_date, order_mode, suggested, other = (
        mail_watcher.split_invoice_candidates(items, "заказ.xlsx")
    )

    assert order_date.isoformat() == "2026-11-10"
    assert order_mode == ""
    assert [item["file"] for item in suggested] == ["МДВ.pdf"]
    assert other == []


def test_invoice_can_be_linked_and_unlinked(monkeypatch):
    letter = _letter_with_attachment("ФМ 40.pdf", b"%PDF", sender="zosya-c@mail.ru")
    monkeypatch.setattr(
        mail_watcher.imaplib,
        "IMAP4_SSL",
        lambda *a, **kw: _FakeIMAP([letter]),
    )
    config = _config(
        senders=[],
        sources=[{
            "name": "Бухгалтер",
            "email": "zosya-c@mail.ru",
            "kind": "invoices",
        }],
    )
    item = mail_watcher.check_mail(config)["items"][0]

    assert mail_watcher.link_invoice(item["path"], "заказ.xlsx")
    assert mail_watcher.load_mail_items()[0]["order_file"] == "заказ.xlsx"
    assert mail_watcher.unlink_invoice(item["path"])
    assert mail_watcher.load_mail_items()[0]["order_file"] == ""
