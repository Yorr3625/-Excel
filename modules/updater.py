"""Проверка и безопасная установка обновлений из GitHub."""

from __future__ import annotations

import re
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from modules.backup import BackupError, create_backup
from modules.version import (
    APP_VERSION,
    PROJECT_ROOT,
    UPDATE_BRANCH,
    UPDATE_VERSION_URL,
)


_VERSION_PATTERN = re.compile(
    r"^\s*APP_VERSION\s*=\s*(['\"])([^'\"]+)\1\s*$",
    re.MULTILINE,
)
_SEMVER_PATTERN = re.compile(r"^(0|[1-9]\d*)\.(0|[1-9]\d*)\.(0|[1-9]\d*)$")


@dataclass(frozen=True)
class UpdateCheckResult:
    """Результат проверки удалённой версии."""

    current_version: str
    latest_version: str = ""
    update_available: bool = False
    ok: bool = False
    message: str = ""


@dataclass(frozen=True)
class UpdateResult:
    """Результат безопасного fast-forward обновления проекта."""

    ok: bool
    changed: bool = False
    message: str = ""


class UpdaterError(RuntimeError):
    """Ошибка, которую можно безопасно показать пользователю."""


def _version_key(version: str) -> tuple[int, int, int]:
    match = _SEMVER_PATTERN.fullmatch(version.strip())
    if not match:
        raise ValueError(f"Некорректная версия: {version}")
    return tuple(int(part) for part in match.groups())


def extract_version(text: str) -> str:
    """Извлекает APP_VERSION из текста version.py и проверяет его формат."""

    match = _VERSION_PATTERN.search(text)
    if not match:
        raise ValueError("В удалённом файле не найден APP_VERSION")

    version = match.group(2)
    _version_key(version)
    return version


def check_for_update(
    current_version: str = APP_VERSION,
    url: str = UPDATE_VERSION_URL,
    timeout: float = 10.0,
) -> UpdateCheckResult:
    """Проверяет версию в GitHub без изменения локальных файлов."""

    try:
        _version_key(current_version)
        request = Request(
            url,
            headers={"User-Agent": f"OrdersDashboard/{current_version}"},
        )
        with urlopen(request, timeout=timeout) as response:
            remote_text = response.read().decode("utf-8")
        latest_version = extract_version(remote_text)
        update_available = _version_key(latest_version) > _version_key(current_version)
    except HTTPError as exc:
        return UpdateCheckResult(
            current_version=current_version,
            ok=False,
            message=f"GitHub вернул ошибку HTTP {exc.code}.",
        )
    except (URLError, TimeoutError, OSError) as exc:
        reason = getattr(exc, "reason", "") or str(exc)
        return UpdateCheckResult(
            current_version=current_version,
            ok=False,
            message=f"Не удалось проверить обновления: {reason}.",
        )
    except (UnicodeError, ValueError) as exc:
        return UpdateCheckResult(
            current_version=current_version,
            ok=False,
            message=f"GitHub вернул некорректные данные: {exc}.",
        )

    if update_available:
        message = f"Доступна новая версия {latest_version}."
    elif latest_version == current_version:
        message = f"Установлена последняя версия {current_version}."
    else:
        message = (
            f"Установлена версия {current_version}; версия GitHub {latest_version} "
            "не новее."
        )

    return UpdateCheckResult(
        current_version=current_version,
        latest_version=latest_version,
        update_available=update_available,
        ok=True,
        message=message,
    )


def _run_command(
    command: list[str],
    root: Path,
    timeout: float,
) -> subprocess.CompletedProcess[str]:
    try:
        return subprocess.run(
            command,
            cwd=str(root),
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=timeout,
            check=False,
        )
    except FileNotFoundError as exc:
        executable = command[0] if command else "команда"
        raise UpdaterError(f"Не найден исполняемый файл {executable}.") from exc
    except subprocess.TimeoutExpired as exc:
        raise UpdaterError("Операция обновления превысила допустимое время.") from exc
    except OSError as exc:
        raise UpdaterError(f"Не удалось запустить команду обновления: {exc}") from exc


def _command_error(result: subprocess.CompletedProcess[str]) -> str:
    details = (result.stderr or result.stdout or "").strip().splitlines()
    return details[-1] if details else "Команда завершилась с ошибкой."


def update_project(
    root: str | Path = PROJECT_ROOT,
    timeout: float = 120.0,
    dependency_timeout: float = 300.0,
) -> UpdateResult:
    """Загружает только fast-forward-изменения и не трогает рабочие данные."""

    project_root = Path(root).resolve()
    if not (project_root / ".git").exists():
        return UpdateResult(
            ok=False,
            message=(
                "Автоматическое обновление доступно только в копии проекта, "
                "скачанной через Git."
            ),
        )

    try:
        fetch = _run_command(
            ["git", "fetch", "origin", UPDATE_BRANCH], project_root, timeout
        )
        if fetch.returncode != 0:
            return UpdateResult(
                ok=False,
                message=f"Не удалось получить обновления: {_command_error(fetch)}",
            )

        status = _run_command(["git", "status", "--porcelain"], project_root, timeout)
        if status.returncode != 0:
            return UpdateResult(
                ok=False,
                message=f"Не удалось проверить локальные изменения: {_command_error(status)}",
            )
        if status.stdout.strip():
            return UpdateResult(
                ok=False,
                message=(
                    "Обновление остановлено: в проекте есть локальные изменения. "
                    "Сохраните их или уберите перед обновлением."
                ),
            )

        current_branch = _run_command(
            ["git", "branch", "--show-current"], project_root, timeout
        )
        if current_branch.returncode != 0:
            return UpdateResult(
                ok=False,
                message=f"Не удалось определить текущую ветку: {_command_error(current_branch)}",
            )
        if current_branch.stdout.strip() != UPDATE_BRANCH:
            branch = current_branch.stdout.strip() or "отсутствующая (detached HEAD)"
            return UpdateResult(
                ok=False,
                message=(
                    f"Обновление доступно только в ветке {UPDATE_BRANCH}; "
                    f"сейчас выбрана ветка {branch}."
                ),
            )

        revisions = _run_command(
            [
                "git",
                "rev-list",
                "--left-right",
                "--count",
                f"HEAD...origin/{UPDATE_BRANCH}",
            ],
            project_root,
            timeout,
        )
        if revisions.returncode != 0:
            return UpdateResult(
                ok=False,
                message=f"Не удалось определить состояние Git: {_command_error(revisions)}",
            )

        try:
            ahead, behind = (int(value) for value in revisions.stdout.split())
        except (TypeError, ValueError):
            return UpdateResult(ok=False, message="Git вернул неизвестное состояние веток.")

        if ahead:
            return UpdateResult(
                ok=False,
                message=(
                    "Обновление остановлено: в локальной ветке есть собственные коммиты. "
                    "Синхронизируйте их вручную."
                ),
            )
        if not behind:
            return UpdateResult(ok=True, message="Установлена последняя версия.")

        try:
            create_backup(project_root=project_root, reason="перед обновлением")
        except BackupError as exc:
            return UpdateResult(
                ok=False,
                message=f"Обновление остановлено: не удалось создать резервную копию: {exc}",
            )

        requirements = _run_command(
            [
                "git",
                "diff",
                "--quiet",
                "HEAD",
                f"origin/{UPDATE_BRANCH}",
                "--",
                "requirements.txt",
            ],
            project_root,
            timeout,
        )
        if requirements.returncode not in (0, 1):
            return UpdateResult(
                ok=False,
                message=f"Не удалось проверить зависимости: {_command_error(requirements)}",
            )
        requirements_changed = requirements.returncode == 1

        merge = _run_command(
            ["git", "merge", "--ff-only", f"origin/{UPDATE_BRANCH}"],
            project_root,
            timeout,
        )
        if merge.returncode != 0:
            return UpdateResult(
                ok=False,
                message=f"Не удалось применить обновление: {_command_error(merge)}",
            )

        if requirements_changed:
            dependencies = _run_command(
                [
                    sys.executable,
                    "-m",
                    "pip",
                    "install",
                    "--disable-pip-version-check",
                    "-q",
                    "-r",
                    "requirements.txt",
                ],
                project_root,
                dependency_timeout,
            )
            if dependencies.returncode != 0:
                return UpdateResult(
                    ok=False,
                    changed=True,
                    message=(
                        "Исходники обновлены, но не удалось установить новые зависимости: "
                        f"{_command_error(dependencies)}"
                    ),
                )

    except UpdaterError as exc:
        return UpdateResult(ok=False, message=str(exc))

    return UpdateResult(
        ok=True,
        changed=True,
        message="Обновление установлено. Дашборд перезапускается.",
    )
