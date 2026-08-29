"""Создание и безопасное восстановление резервных копий состояния приложения.

В архив попадают только небольшие JSON-файлы со статистикой, историей и
настройками. Рабочие книги, результаты обработки, PDF и логи намеренно не
включаются: их можно хранить отдельно, а резервная копия состояния остаётся
компактной и проверяемой.
"""

from __future__ import annotations

import json
import os
import stat
import tempfile
import zipfile
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path, PurePosixPath

from modules import paths
from modules.version import APP_VERSION, PROJECT_ROOT


BACKUP_FORMAT_VERSION = 1
DEFAULT_BACKUP_DIRECTORY = paths.DATA_DIR / "backups"
MAX_BACKUP_UNCOMPRESSED_BYTES = 50 * 1024 * 1024
BACKUP_SUFFIX = ".zip"

# Keep this list explicit. In particular, do not archive data/orders or
# processed workbooks: those directories may be large and contain user files.
_BACKUP_RELATIVE_FILES = (
    "data/volume_history.json",
    "data/processed_files.json",
    "data/mail_items.json",
    "data/mail_seen.json",
    "data/mail_uid_cache.json",
    "data/mail_errors.json",
    "data/route_backups.json",
    "config/settings.json",
    "config/stores.json",
    "config/stores_city.json",
    "config/stores_region.json",
    "config/mail.json",
    "config/backup.json",
)
_KNOWN_RELATIVE_FILES = frozenset(_BACKUP_RELATIVE_FILES)


class BackupError(RuntimeError):
    """Ошибка создания, проверки или восстановления резервной копии."""


@dataclass(frozen=True)
class BackupInfo:
    """Метаданные архива, пригодные для показа в интерфейсе."""

    path: Path
    name: str
    created_at: str = ""
    size_bytes: int = 0
    file_count: int = 0
    valid: bool = True
    error: str = ""
    contains_secrets: bool = False


@dataclass(frozen=True)
class RestoreResult:
    """Результат восстановления состояния из архива."""

    archive: Path
    restored_files: tuple[str, ...]
    removed_files: tuple[str, ...]
    safety_backup: BackupInfo | None = None


def _project_root(project_root: str | Path | None) -> Path:
    return (Path(project_root) if project_root is not None else PROJECT_ROOT).expanduser().resolve()


def _rooted(path: str | Path, root: Path) -> Path:
    value = Path(path).expanduser()
    return value.resolve() if value.is_absolute() else (root / value).resolve()


def _backup_settings_path(root: Path) -> Path:
    return _rooted(paths.BACKUP_SETTINGS_FILE, root)


def _default_backup_directory(root: Path) -> Path:
    return _rooted(DEFAULT_BACKUP_DIRECTORY, root)


def _read_json(path: Path, default):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError):
        return default


def _atomic_write_bytes(path: Path, data: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = None

    try:
        fd, temporary = tempfile.mkstemp(
            prefix=f".{path.name}.",
            suffix=".tmp",
            dir=str(path.parent),
        )
        with os.fdopen(fd, "wb") as stream:
            stream.write(data)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
        temporary = None
    except OSError as exc:
        raise BackupError(f"Не удалось сохранить {path.name}: {exc}") from exc
    finally:
        if temporary:
            try:
                os.unlink(temporary)
            except OSError:
                pass


def _atomic_write_json(path: Path, data: dict) -> None:
    payload = json.dumps(data, ensure_ascii=False, indent=2).encode("utf-8")
    _atomic_write_bytes(path, payload)


def load_backup_directory(project_root: str | Path | None = None) -> Path:
    """Возвращает настроенную папку, не создавая её на диске."""

    root = _project_root(project_root)
    settings = _read_json(_backup_settings_path(root), {})
    raw_directory = settings.get("directory") if isinstance(settings, dict) else None

    if not isinstance(raw_directory, str) or not raw_directory.strip():
        return _default_backup_directory(root)

    return _rooted(raw_directory.strip(), root)


def save_backup_directory(
    directory: str | Path,
    project_root: str | Path | None = None,
) -> Path:
    """Сохраняет папку резервных копий и возвращает абсолютный путь."""

    root = _project_root(project_root)
    raw_directory = str(directory).strip()
    if not raw_directory:
        raise BackupError("Папка резервных копий не может быть пустой.")

    resolved = _rooted(raw_directory, root)
    try:
        resolved.mkdir(parents=True, exist_ok=True)
        if not resolved.is_dir():
            raise NotADirectoryError(str(resolved))
    except OSError as exc:
        raise BackupError(f"Не удалось открыть папку резервных копий: {exc}") from exc

    _atomic_write_json(_backup_settings_path(root), {"directory": raw_directory})
    return resolved


def _tracked_paths(root: Path) -> list[tuple[str, Path]]:
    return [(relative, root / Path(*relative.split("/"))) for relative in _BACKUP_RELATIVE_FILES]


def _present_files(root: Path) -> list[tuple[str, Path]]:
    result = []
    for relative, path in _tracked_paths(root):
        if path.is_symlink():
            raise BackupError(f"Файл состояния является символической ссылкой: {relative}")
        if path.is_file():
            result.append((relative, path))
    return result


def _next_archive_path(directory: Path, now: datetime) -> Path:
    stem = f"backup-{now:%Y%m%d-%H%M%S-%f}"
    candidate = directory / f"{stem}{BACKUP_SUFFIX}"
    suffix = 2

    while candidate.exists():
        candidate = directory / f"{stem}-{suffix}{BACKUP_SUFFIX}"
        suffix += 1

    return candidate


def create_backup(
    backup_directory: str | Path | None = None,
    project_root: str | Path | None = None,
    reason: str = "вручную",
) -> BackupInfo:
    """Создаёт атомарный ZIP-снимок состояния приложения."""

    root = _project_root(project_root)
    directory = (
        load_backup_directory(root)
        if backup_directory is None
        else _rooted(backup_directory, root)
    )

    try:
        directory.mkdir(parents=True, exist_ok=True)
        if not directory.is_dir():
            raise NotADirectoryError(str(directory))
    except OSError as exc:
        raise BackupError(f"Не удалось открыть папку резервных копий: {exc}") from exc

    present = _present_files(root)
    now = datetime.now().astimezone()
    tracked = [
        {"path": relative, "present": any(relative == item[0] for item in present)}
        for relative, _path in _tracked_paths(root)
    ]
    manifest = {
        "format_version": BACKUP_FORMAT_VERSION,
        "app_version": APP_VERSION,
        "created_at": now.isoformat(),
        "reason": str(reason or "вручную"),
        "files": tracked,
    }

    archive_path = _next_archive_path(directory, now)
    temporary = None

    try:
        fd, temporary = tempfile.mkstemp(
            prefix=".backup-",
            suffix=".tmp",
            dir=str(directory),
        )
        os.close(fd)
        with zipfile.ZipFile(temporary, "w", compression=zipfile.ZIP_DEFLATED) as archive:
            archive.writestr(
                "manifest.json",
                json.dumps(manifest, ensure_ascii=False, indent=2).encode("utf-8"),
            )
            for relative, path in present:
                archive.write(path, relative)
        os.replace(temporary, archive_path)
        temporary = None
    except (OSError, zipfile.BadZipFile, ValueError) as exc:
        raise BackupError(f"Не удалось создать резервную копию: {exc}") from exc
    finally:
        if temporary:
            try:
                os.unlink(temporary)
            except OSError:
                pass

    return BackupInfo(
        path=archive_path,
        name=archive_path.name,
        created_at=manifest["created_at"],
        size_bytes=archive_path.stat().st_size,
        file_count=len(present),
        contains_secrets=any(
            item["path"] == "config/mail.json" and item["present"]
            for item in tracked
        ),
    )


def _validate_member_name(name: str) -> str:
    if not isinstance(name, str) or not name or name.replace("\\", "/") != name:
        raise BackupError("Архив содержит некорректное имя файла.")

    path = PurePosixPath(name)
    if path.is_absolute() or "." in path.parts or ".." in path.parts:
        raise BackupError("Архив содержит небезопасный путь.")

    return name


def _read_archive(archive_path: str | Path) -> tuple[dict, dict[str, bytes]]:
    path = Path(archive_path).expanduser().resolve()
    if path.suffix.casefold() != BACKUP_SUFFIX or not path.is_file():
        raise BackupError("Резервная копия не найдена или имеет неверное расширение.")

    try:
        with zipfile.ZipFile(path, "r") as archive:
            names = archive.namelist()
            if len(names) != len(set(names)):
                raise BackupError("Архив содержит повторяющиеся имена файлов.")
            if "manifest.json" not in names:
                raise BackupError("В архиве отсутствует manifest.json.")

            for name in names:
                _validate_member_name(name)
                info = archive.getinfo(name)
                if info.is_dir() or stat.S_ISLNK(info.external_attr >> 16):
                    raise BackupError("Архив содержит папку или символическую ссылку.")

            try:
                manifest = json.loads(archive.read("manifest.json").decode("utf-8"))
            except (UnicodeError, json.JSONDecodeError) as exc:
                raise BackupError("manifest.json повреждён или содержит не JSON.") from exc

            if not isinstance(manifest, dict):
                raise BackupError("Некорректная структура manifest.json.")
            if manifest.get("format_version") != BACKUP_FORMAT_VERSION:
                raise BackupError("Версия формата резервной копии не поддерживается.")

            entries = manifest.get("files")
            if not isinstance(entries, list) or len(entries) != len(_BACKUP_RELATIVE_FILES):
                raise BackupError("В manifest.json указан неполный список файлов.")

            states: dict[str, bool] = {}
            for entry in entries:
                if not isinstance(entry, dict):
                    raise BackupError("Некорректная запись файла в manifest.json.")
                relative = _validate_member_name(entry.get("path"))
                if relative not in _KNOWN_RELATIVE_FILES or relative in states:
                    raise BackupError("manifest.json содержит неизвестный или повторный путь.")
                if not isinstance(entry.get("present"), bool):
                    raise BackupError("В manifest.json отсутствует признак наличия файла.")
                states[relative] = entry["present"]

            if set(states) != _KNOWN_RELATIVE_FILES:
                raise BackupError("manifest.json не описывает все файлы состояния.")

            present_names = {relative for relative, present in states.items() if present}
            expected_names = {"manifest.json", *present_names}
            if set(names) != expected_names:
                raise BackupError("Состав архива не совпадает с manifest.json.")

            total_size = sum(archive.getinfo(name).file_size for name in present_names)
            if total_size > MAX_BACKUP_UNCOMPRESSED_BYTES:
                raise BackupError("Размер данных в архиве превышает допустимый предел.")

            payloads = {name: archive.read(name) for name in present_names}
    except BackupError:
        raise
    except (OSError, zipfile.BadZipFile, zipfile.LargeZipFile, RuntimeError) as exc:
        raise BackupError(f"Не удалось прочитать резервную копию: {exc}") from exc

    for relative, payload in payloads.items():
        try:
            json.loads(payload.decode("utf-8"))
        except (UnicodeError, json.JSONDecodeError) as exc:
            raise BackupError(f"Файл {relative} в архиве повреждён.") from exc

    return manifest, payloads


def inspect_backup(archive_path: str | Path) -> BackupInfo:
    """Проверяет архив и возвращает метаданные, не изменяя файлы проекта."""

    path = Path(archive_path).expanduser().resolve()
    try:
        manifest, payloads = _read_archive(path)
        return BackupInfo(
            path=path,
            name=path.name,
            created_at=str(manifest.get("created_at", "")),
            size_bytes=path.stat().st_size,
            file_count=len(payloads),
            contains_secrets="config/mail.json" in payloads,
        )
    except (BackupError, OSError) as exc:
        try:
            size = path.stat().st_size
        except OSError:
            size = 0
        return BackupInfo(
            path=path,
            name=path.name,
            size_bytes=size,
            valid=False,
            error=str(exc),
        )


def list_backups(
    backup_directory: str | Path | None = None,
    project_root: str | Path | None = None,
) -> list[BackupInfo]:
    """Возвращает ZIP-архивы от новых к старым, включая повреждённые."""

    root = _project_root(project_root)
    directory = (
        load_backup_directory(root)
        if backup_directory is None
        else _rooted(backup_directory, root)
    )
    try:
        candidates = list(directory.glob(f"*{BACKUP_SUFFIX}")) if directory.is_dir() else []
        candidates.sort(key=lambda item: item.stat().st_mtime, reverse=True)
    except OSError as exc:
        raise BackupError(f"Не удалось прочитать список резервных копий: {exc}") from exc

    return [inspect_backup(path) for path in candidates]


def _safe_archive_path(archive_path: str | Path) -> Path:
    path = Path(archive_path).expanduser().resolve()
    if path.suffix.casefold() != BACKUP_SUFFIX:
        raise BackupError("Можно восстановить только ZIP-резервную копию.")
    return path


def restore_backup(
    archive_path: str | Path,
    project_root: str | Path | None = None,
    safety_backup: bool = True,
) -> RestoreResult:
    """Восстанавливает JSON-состояние после полной проверки архива.

    Перед заменой файлов по умолчанию создаётся страховочный снимок текущего
    состояния. Он позволяет отменить ошибочное восстановление обычной операцией.
    """

    root = _project_root(project_root)
    archive = _safe_archive_path(archive_path)
    manifest, payloads = _read_archive(archive)
    states = {entry["path"]: entry["present"] for entry in manifest["files"]}

    # Prepare every replacement before changing a live file. This also ensures
    # an unreadable destination is reported before the first os.replace call.
    temporary_files: list[tuple[Path, Path]] = []
    try:
        for relative, payload in payloads.items():
            target = root / Path(*relative.split("/"))
            if not target.parent.resolve().is_relative_to(root):
                raise BackupError("Путь файла состояния выходит за пределы проекта.")
            target.parent.mkdir(parents=True, exist_ok=True)
            fd, temporary = tempfile.mkstemp(
                prefix=f".{target.name}.",
                suffix=".restore.tmp",
                dir=str(target.parent),
            )
            with os.fdopen(fd, "wb") as stream:
                stream.write(payload)
                stream.flush()
                os.fsync(stream.fileno())
            temporary_files.append((target, Path(temporary)))
    except (OSError, BackupError) as exc:
        for _target, temporary in temporary_files:
            try:
                temporary.unlink()
            except OSError:
                pass
        if isinstance(exc, BackupError):
            raise
        raise BackupError(f"Не удалось подготовить восстановление: {exc}") from exc

    safety = None
    try:
        if safety_backup:
            safety = create_backup(
                project_root=root,
                reason="перед восстановлением",
            )

        for target, temporary in temporary_files:
            os.replace(temporary, target)

        removed = []
        for relative, present in states.items():
            if present:
                continue
            target = root / Path(*relative.split("/"))
            if target.exists() or target.is_symlink():
                target.unlink()
                removed.append(relative)
    except (OSError, BackupError) as exc:
        if isinstance(exc, BackupError):
            raise
        raise BackupError(f"Не удалось применить восстановление: {exc}") from exc
    finally:
        for _target, temporary in temporary_files:
            try:
                temporary.unlink()
            except OSError:
                pass

    return RestoreResult(
        archive=archive,
        restored_files=tuple(sorted(payloads)),
        removed_files=tuple(sorted(removed)),
        safety_backup=safety,
    )


__all__ = [
    "BACKUP_FORMAT_VERSION",
    "BackupError",
    "BackupInfo",
    "RestoreResult",
    "create_backup",
    "inspect_backup",
    "list_backups",
    "load_backup_directory",
    "restore_backup",
    "save_backup_directory",
]
