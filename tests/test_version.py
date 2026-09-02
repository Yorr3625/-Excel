from modules.version import APP_VERSION, load_changelog, parse_changelog


def test_parse_changelog_separates_releases_and_changes():
    text = """# История

## [1.2.0] — 29.08.2026

- Новая возможность
- Исправлена ошибка

### Дополнительно

## 1.1.0 - 20.08.2026

* Предыдущее изменение
"""

    assert parse_changelog(text) == [
        {
            "version": "1.2.0",
            "date": "29.08.2026",
            "changes": ["Новая возможность", "Исправлена ошибка"],
        },
        {
            "version": "1.1.0",
            "date": "20.08.2026",
            "changes": ["Предыдущее изменение"],
        },
    ]


def test_parse_changelog_ignores_changes_before_first_release():
    assert parse_changelog("- Не относится к релизу\n\n# Заголовок") == []


def test_load_changelog_returns_empty_for_missing_file(tmp_path):
    assert load_changelog(tmp_path / "нет-такого-файла.md") == []


def test_load_changelog_reads_utf8_file(tmp_path):
    changelog = tmp_path / "CHANGELOG.md"
    changelog.write_text(
        "## [0.1.0]\n\n- Первая версия\n",
        encoding="utf-8",
    )

    assert load_changelog(changelog)[0]["changes"] == ["Первая версия"]


def test_current_version_is_stable_release():
    assert APP_VERSION == "1.0.4"
