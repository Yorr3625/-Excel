"""Версия приложения и чтение журнала релизов."""

import re
from pathlib import Path
from typing import TypedDict


class Release(TypedDict):
    version: str
    date: str
    changes: list[str]


APP_NAME = "Обработка заказов"
APP_VERSION = "1.0.6"
UPDATE_REPOSITORY = "Yorr3625/-Excel"
UPDATE_BRANCH = "main"
UPDATE_VERSION_URL = (
    f"https://raw.githubusercontent.com/{UPDATE_REPOSITORY}/{UPDATE_BRANCH}/modules/version.py"
)
PROJECT_ROOT = Path(__file__).resolve().parent.parent
CHANGELOG_FILE = PROJECT_ROOT / "CHANGELOG.md"

_RELEASE_HEADER = re.compile(
    r"^##\s+\[?([^\]\s]+)\]?(?:\s+(?:—|-)\s+(.+))?\s*$"
)
_CHANGE_LINE = re.compile(r"^(?:[-*+])\s+(.+)$")


def parse_changelog(text: str) -> list[Release]:
    """Преобразует простой Markdown-журнал в данные для веб-страницы.

    Запись релиза начинается с заголовка второго уровня, например:
    ``## [1.0.0] — 29.08.2026``. Изменения задаются маркированными
    строками ниже заголовка. Остальной Markdown намеренно игнорируется.
    """

    releases: list[Release] = []
    current: Release | None = None

    for raw_line in text.splitlines():
        line = raw_line.strip()
        match = _RELEASE_HEADER.match(line)

        if match:
            current = {
                "version": match.group(1),
                "date": match.group(2) or "",
                "changes": [],
            }
            releases.append(current)
            continue

        if current:
            change = _CHANGE_LINE.match(line)
            if change and change.group(1).strip():
                current["changes"].append(change.group(1).strip())

    return releases


def load_changelog(path: str | Path = CHANGELOG_FILE) -> list[Release]:
    """Загружает журнал из файла; при ошибке возвращает пустой список."""

    try:
        text = Path(path).read_text(encoding="utf-8")
    except (OSError, UnicodeError):
        return []

    return parse_changelog(text)
