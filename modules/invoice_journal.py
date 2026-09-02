"""Локальное хранение подтверждённых накладных и их фотографий."""

from __future__ import annotations

import json
import os
import shutil
import tempfile
import threading
import uuid
from datetime import datetime
from decimal import Decimal, InvalidOperation
from pathlib import Path

from modules.paths import DATA_DIR, INVOICE_OCR_JOURNAL_FILE, INVOICE_OCR_PHOTOS_FOLDER


_JOURNAL_LOCK = threading.Lock()
_SCHEMA_VERSION = 1


class InvoiceJournalError(RuntimeError):
    """Ошибка сохранения локального журнала накладных."""


def stage_invoice_photos(photos: list[tuple[bytes, str]], draft_id: str | None = None) -> tuple[str, list[str]]:
    """Сохраняет оригиналы фото в закрытую папку черновика."""

    if not photos:
        raise InvoiceJournalError("Добавьте хотя бы одну фотографию накладной")

    invoice_id = _valid_id(draft_id or uuid.uuid4().hex)
    folder = _photo_folder(invoice_id)
    if folder.exists():
        raise InvoiceJournalError("Черновик накладной уже существует")

    try:
        folder.mkdir(parents=True, exist_ok=False)
        references = []
        for index, (content, extension) in enumerate(photos, start=1):
            if extension not in {".jpg", ".png", ".webp"} or not content:
                raise InvoiceJournalError("Не удалось сохранить одну из фотографий")
            path = folder / f"photo-{index:02d}{extension}"
            path.write_bytes(content)
            references.append(path.relative_to(DATA_DIR).as_posix())
        return invoice_id, references
    except (InvoiceJournalError, OSError, ValueError) as error:
        discard_staged_invoice(invoice_id)
        if isinstance(error, InvoiceJournalError):
            raise
        raise InvoiceJournalError("Не удалось сохранить фотографии накладной") from error


def discard_staged_invoice(invoice_id: str) -> None:
    """Удаляет только папку указанного несохранённого черновика."""

    try:
        folder = _photo_folder(_valid_id(invoice_id))
    except InvoiceJournalError:
        return
    shutil.rmtree(folder, ignore_errors=True)


def append_invoice_entry(
    invoice_id: str,
    order_file: str,
    route: str,
    photo_refs: list[str],
    lines: list[dict],
) -> dict:
    """Проверяет и атомарно добавляет подтверждённую накладную в журнал."""

    invoice_id = _valid_id(invoice_id)
    order_file = str(order_file).strip()
    route = str(route).strip()
    if not order_file or not route:
        raise InvoiceJournalError("Выберите заказ и маршрут")
    if not photo_refs or not all(_valid_photo_ref(invoice_id, reference) for reference in photo_refs):
        raise InvoiceJournalError("Фотографии накладной недоступны")

    normalized_lines = _normalize_lines(lines)
    total = sum((Decimal(line["line_total"]) for line in normalized_lines), Decimal())
    entry = {
        "id": invoice_id,
        "saved_at": datetime.now().astimezone().isoformat(timespec="seconds"),
        "order_file": order_file,
        "route": route,
        "photo_refs": list(photo_refs),
        "lines": normalized_lines,
        "total": _format_decimal(total),
    }

    with _JOURNAL_LOCK:
        journal = _load_journal()
        if any(item.get("id") == invoice_id for item in journal["entries"] if isinstance(item, dict)):
            raise InvoiceJournalError("Эта накладная уже сохранена")
        journal["entries"].append(entry)
        _atomic_write_json(INVOICE_OCR_JOURNAL_FILE, journal)

    return entry


def load_invoice_entries() -> list[dict]:
    """Возвращает сохранённые накладные от новых к старым."""

    with _JOURNAL_LOCK:
        entries = _load_journal()["entries"]
    return [entry for entry in reversed(entries) if isinstance(entry, dict)]


def _load_journal() -> dict:
    if not INVOICE_OCR_JOURNAL_FILE.exists():
        return {"schema_version": _SCHEMA_VERSION, "entries": []}

    try:
        journal = json.loads(INVOICE_OCR_JOURNAL_FILE.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as error:
        raise InvoiceJournalError("Журнал накладных повреждён и не был перезаписан") from error

    if not isinstance(journal, dict) or not isinstance(journal.get("entries"), list):
        raise InvoiceJournalError("Журнал накладных имеет неверный формат и не был перезаписан")
    return journal


def _normalize_lines(lines: list[dict]) -> list[dict[str, str]]:
    if not lines:
        raise InvoiceJournalError("Добавьте хотя бы одну товарную строку")

    result = []
    for line in lines:
        if not isinstance(line, dict):
            raise InvoiceJournalError("Одна из товарных строк имеет неверный формат")
        name = str(line.get("name", "")).strip()
        unit = str(line.get("unit", "")).strip()
        if not name or not unit:
            raise InvoiceJournalError("Укажите наименование и единицу измерения в каждой строке")
        quantity = _positive_decimal(line.get("quantity"), "Количество должно быть больше нуля")
        unit_price = _nonnegative_decimal(line.get("unit_price"), "Цена не может быть отрицательной")
        line_total = _nonnegative_decimal(line.get("line_total"), "Сумма строки не может быть отрицательной")
        result.append(
            {
                "name": name,
                "unit": unit,
                "quantity": _format_decimal(quantity),
                "unit_price": _format_decimal(unit_price),
                "line_total": _format_decimal(line_total),
            }
        )
    return result


def _positive_decimal(value: object, message: str) -> Decimal:
    number = _decimal(value, message)
    if number <= 0:
        raise InvoiceJournalError(message)
    return number


def _nonnegative_decimal(value: object, message: str) -> Decimal:
    number = _decimal(value, message)
    if number < 0:
        raise InvoiceJournalError(message)
    return number


def _decimal(value: object, message: str) -> Decimal:
    try:
        return Decimal(str(value).strip().replace(",", "."))
    except (InvalidOperation, ValueError):
        raise InvoiceJournalError(message) from None


def _format_decimal(value: Decimal) -> str:
    rendered = format(value.normalize(), "f")
    return rendered.rstrip("0").rstrip(".") if "." in rendered else rendered


def _valid_id(invoice_id: str) -> str:
    try:
        return uuid.UUID(str(invoice_id)).hex
    except (ValueError, AttributeError):
        raise InvoiceJournalError("Некорректный идентификатор накладной") from None


def _photo_folder(invoice_id: str) -> Path:
    root = INVOICE_OCR_PHOTOS_FOLDER.resolve()
    folder = (root / invoice_id).resolve()
    if folder.parent != root:
        raise InvoiceJournalError("Некорректный путь фотографий")
    return folder


def _valid_photo_ref(invoice_id: str, reference: str) -> bool:
    try:
        path = (DATA_DIR / Path(reference)).resolve()
        folder = _photo_folder(invoice_id)
        return path.parent == folder and path.is_file()
    except (InvoiceJournalError, OSError, ValueError):
        return False


def _atomic_write_json(path: Path, data: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = None
    try:
        fd, temporary = tempfile.mkstemp(prefix=f".{path.name}.", suffix=".tmp", dir=str(path.parent))
        with os.fdopen(fd, "w", encoding="utf-8") as stream:
            json.dump(data, stream, ensure_ascii=False, indent=2)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
        temporary = None
    except OSError as error:
        raise InvoiceJournalError("Не удалось сохранить журнал накладных") from error
    finally:
        if temporary:
            try:
                os.unlink(temporary)
            except OSError:
                pass
