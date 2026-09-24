"""Безопасный список и одноразовые ссылки на обработанные Excel-файлы."""

from __future__ import annotations

from datetime import datetime
from pathlib import Path
import secrets
import threading
import time

from modules import paths


EXCEL_SUFFIX = ".xlsx"
DOWNLOAD_TICKET_TTL_SECONDS = 60
_DOWNLOAD_TICKETS: dict[str, tuple[str, float]] = {}
_DOWNLOAD_TICKETS_LOCK = threading.Lock()


class ProcessedFileError(ValueError):
    """Запрошенный обработанный файл не существует или недоступен."""


def _root() -> Path:
    return Path(paths.PROCESSED_FOLDER).resolve(strict=False)


def _is_within_root(path: Path, root: Path) -> bool:
    try:
        path.relative_to(root)
    except ValueError:
        return False
    return True


def _valid_date_folder(name: str) -> bool:
    try:
        return datetime.strptime(name, "%d.%m.%y").strftime("%d.%m.%y") == name
    except ValueError:
        return False


def _safe_relative_path(relative_path: str) -> tuple[str, ...]:
    if not isinstance(relative_path, str) or not relative_path:
        raise ProcessedFileError("Некорректный путь к файлу.")

    normalized = relative_path.replace("\\", "/")
    raw_parts = normalized.split("/")
    if (
        len(raw_parts) != 2
        or any(part in {"", ".", ".."} for part in raw_parts)
        or any("\x00" in part for part in raw_parts)
        or not _valid_date_folder(raw_parts[0])
        or Path(raw_parts[1]).suffix.lower() != EXCEL_SUFFIX
    ):
        raise ProcessedFileError("Некорректный путь к файлу.")
    return tuple(raw_parts)


def resolve_processed_file(relative_path: str) -> Path:
    """Проверяет идентификатор и возвращает файл только внутри каталога результатов."""

    parts = _safe_relative_path(relative_path)
    root = _root()
    candidate = root.joinpath(*parts)

    # Не разрешаем symlink даже тогда, когда он указывает обратно внутрь каталога.
    if any((root.joinpath(*parts[:index])).is_symlink() for index in range(1, len(parts) + 1)):
        raise ProcessedFileError("Файл недоступен.")

    resolved = candidate.resolve(strict=False)
    if not _is_within_root(resolved, root) or resolved != candidate:
        raise ProcessedFileError("Файл недоступен.")
    if not candidate.is_file() or candidate.suffix.lower() != EXCEL_SUFFIX:
        raise ProcessedFileError("Файл не найден.")
    return candidate


def _file_entry(path: Path, root: Path) -> dict:
    stat = path.stat()
    relative_path = path.relative_to(root).as_posix()
    modified_at = datetime.fromtimestamp(stat.st_mtime).strftime("%d.%m.%Y %H:%M")
    return {
        "relative_path": relative_path,
        "filename": path.name,
        "folder": path.parent.name,
        "modified_at": modified_at,
        "size": stat.st_size,
        "size_label": _format_size(stat.st_size),
        "sort_time": stat.st_mtime,
    }


def _format_size(size: int) -> str:
    value = float(size)
    for unit in ("Б", "КБ", "МБ", "ГБ"):
        if value < 1024 or unit == "ГБ":
            return f"{int(value)} {unit}" if unit == "Б" else f"{value:.1f} {unit}"
        value /= 1024
    return "0 Б"


def list_processed_files() -> list[dict]:
    """Возвращает Excel-файлы из непосредственных датированных подпапок."""

    root = _root()
    if not root.is_dir():
        return []

    entries = []
    for folder in root.iterdir():
        if folder.is_symlink() or not folder.is_dir() or not _valid_date_folder(folder.name):
            continue
        for path in folder.iterdir():
            if path.is_symlink() or not path.is_file() or path.suffix.lower() != EXCEL_SUFFIX:
                continue
            try:
                # Повторная проверка защищает список от ссылок, появившихся во время обхода.
                safe_path = resolve_processed_file(path.relative_to(root).as_posix())
                entries.append(_file_entry(safe_path, root))
            except (OSError, ProcessedFileError):
                continue

    entries.sort(key=lambda item: item["sort_time"], reverse=True)
    for entry in entries:
        entry.pop("sort_time", None)
    return entries


def create_download_ticket(relative_path: str) -> str:
    """Создаёт короткоживущую одноразовую ссылку после проверки файла."""

    safe_path = resolve_processed_file(relative_path)
    relative = safe_path.relative_to(_root()).as_posix()
    now = time.monotonic()
    token = secrets.token_urlsafe(32)
    with _DOWNLOAD_TICKETS_LOCK:
        _purge_expired(now)
        _DOWNLOAD_TICKETS[token] = (relative, now + DOWNLOAD_TICKET_TTL_SECONDS)
    return token


def consume_download_ticket(token: str) -> Path:
    """Поглощает билет ровно один раз и снова проверяет файл на диске."""

    if not isinstance(token, str) or not token:
        raise ProcessedFileError("Ссылка на скачивание недействительна.")

    now = time.monotonic()
    with _DOWNLOAD_TICKETS_LOCK:
        _purge_expired(now)
        ticket = _DOWNLOAD_TICKETS.pop(token, None)

    if ticket is None or ticket[1] <= now:
        raise ProcessedFileError("Ссылка на скачивание недействительна или устарела.")
    return resolve_processed_file(ticket[0])


def _purge_expired(now: float) -> None:
    for token, (_, expires_at) in list(_DOWNLOAD_TICKETS.items()):
        if expires_at <= now:
            _DOWNLOAD_TICKETS.pop(token, None)
