from __future__ import annotations

import subprocess
from urllib.error import URLError

import pytest

from modules import updater


class _Response:
    def __init__(self, body: bytes):
        self.body = body

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return None

    def read(self):
        return self.body


def _completed(command, stdout="", stderr="", returncode=0):
    return subprocess.CompletedProcess(
        command,
        returncode,
        stdout=stdout,
        stderr=stderr,
    )


def test_extract_version_accepts_single_and_double_quotes():
    assert updater.extract_version('APP_VERSION = "2.4.1"') == "2.4.1"
    assert updater.extract_version("APP_VERSION='0.10.0'") == "0.10.0"


@pytest.mark.parametrize(
    "text",
    [
        "APP_VERSION = '2.0'",
        "APP_VERSION = 'v2.0.0'",
        "APP_NAME = 'нет версии'",
    ],
)
def test_extract_version_rejects_invalid_content(text):
    with pytest.raises(ValueError):
        updater.extract_version(text)


def test_check_for_update_reports_new_version(monkeypatch):
    calls = []

    def fake_urlopen(request, timeout):
        calls.append((request.full_url, timeout, request.get_header("User-agent")))
        return _Response(b'APP_VERSION = "1.2.0"\n')

    monkeypatch.setattr(updater, "urlopen", fake_urlopen)

    result = updater.check_for_update("1.1.9", url="https://example.test/version.py")

    assert result.ok is True
    assert result.latest_version == "1.2.0"
    assert result.update_available is True
    assert "1.2.0" in result.message
    assert calls == [("https://example.test/version.py", 10.0, "OrdersDashboard/1.1.9")]


def test_check_for_update_handles_network_error(monkeypatch):
    def fake_urlopen(request, timeout):
        raise URLError("нет соединения")

    monkeypatch.setattr(updater, "urlopen", fake_urlopen)

    result = updater.check_for_update("1.0.0")

    assert result.ok is False
    assert result.update_available is False
    assert "нет соединения" in result.message


def test_update_project_fast_forwards_clean_repository(monkeypatch, tmp_path):
    (tmp_path / ".git").mkdir()
    commands = []

    outputs = {
        "git fetch origin main": _completed([]),
        "git status --porcelain": _completed([]),
        "git branch --show-current": _completed([], stdout="main\n"),
        "git rev-list --left-right --count HEAD...origin/main": _completed(
            [], stdout="0\t2\n"
        ),
        "git diff --quiet HEAD origin/main -- requirements.txt": _completed([]),
        "git merge --ff-only origin/main": _completed([]),
    }

    def fake_run(command, **kwargs):
        commands.append((command, kwargs))
        return outputs[" ".join(command)]

    monkeypatch.setattr(updater.subprocess, "run", fake_run)

    result = updater.update_project(tmp_path)

    assert result == updater.UpdateResult(
        ok=True,
        changed=True,
        message="Обновление установлено. Дашборд перезапускается.",
    )
    assert [command for command, _ in commands] == [
        ["git", "fetch", "origin", "main"],
        ["git", "status", "--porcelain"],
        ["git", "branch", "--show-current"],
        ["git", "rev-list", "--left-right", "--count", "HEAD...origin/main"],
        ["git", "diff", "--quiet", "HEAD", "origin/main", "--", "requirements.txt"],
        ["git", "merge", "--ff-only", "origin/main"],
    ]
    assert all(kwargs["cwd"] == str(tmp_path.resolve()) for _, kwargs in commands)
    assert all(kwargs["check"] is False for _, kwargs in commands)
    assert all(kwargs.get("shell") is not True for _, kwargs in commands)


def test_update_project_creates_backup_before_merge(monkeypatch, tmp_path):
    (tmp_path / ".git").mkdir()
    calls = []
    outputs = {
        "git fetch origin main": _completed([]),
        "git status --porcelain": _completed([]),
        "git branch --show-current": _completed([], stdout="main\n"),
        "git rev-list --left-right --count HEAD...origin/main": _completed(
            [], stdout="0\t1\n"
        ),
        "git diff --quiet HEAD origin/main -- requirements.txt": _completed([]),
        "git merge --ff-only origin/main": _completed([]),
    }

    def fake_backup(**kwargs):
        calls.append(kwargs)

    def fake_run(command, **kwargs):
        return outputs[" ".join(command)]

    monkeypatch.setattr(updater, "create_backup", fake_backup)
    monkeypatch.setattr(updater.subprocess, "run", fake_run)

    result = updater.update_project(tmp_path)

    assert result.ok is True
    assert calls == [{"project_root": tmp_path.resolve(), "reason": "перед обновлением"}]


def test_update_project_stops_when_backup_fails(monkeypatch, tmp_path):
    (tmp_path / ".git").mkdir()
    commands = []
    outputs = {
        "git fetch origin main": _completed([]),
        "git status --porcelain": _completed([]),
        "git branch --show-current": _completed([], stdout="main\n"),
        "git rev-list --left-right --count HEAD...origin/main": _completed(
            [], stdout="0\t1\n"
        ),
    }

    def fake_backup(**kwargs):
        raise updater.BackupError("нет места на диске")

    def fake_run(command, **kwargs):
        commands.append(command)
        return outputs[" ".join(command)]

    monkeypatch.setattr(updater, "create_backup", fake_backup)
    monkeypatch.setattr(updater.subprocess, "run", fake_run)

    result = updater.update_project(tmp_path)

    assert result.ok is False
    assert "не удалось создать резервную копию" in result.message
    assert "нет места на диске" in result.message
    assert commands == [
        ["git", "fetch", "origin", "main"],
        ["git", "status", "--porcelain"],
        ["git", "branch", "--show-current"],
        ["git", "rev-list", "--left-right", "--count", "HEAD...origin/main"],
    ]


def test_update_project_stops_for_local_changes(monkeypatch, tmp_path):
    (tmp_path / ".git").mkdir()
    commands = []

    def fake_run(command, **kwargs):
        commands.append(command)
        if command[:3] == ["git", "status", "--porcelain"]:
            return _completed(command, stdout=" M orders_dashboard/orders_dashboard.py\n")
        return _completed(command)

    monkeypatch.setattr(updater.subprocess, "run", fake_run)

    result = updater.update_project(tmp_path)

    assert result.ok is False
    assert "локальные изменения" in result.message
    assert commands == [
        ["git", "fetch", "origin", "main"],
        ["git", "status", "--porcelain"],
    ]


def test_update_project_stops_on_non_main_branch(monkeypatch, tmp_path):
    (tmp_path / ".git").mkdir()
    commands = []

    def fake_run(command, **kwargs):
        commands.append(command)
        if command[:3] == ["git", "branch", "--show-current"]:
            return _completed(command, stdout="feature\n")
        return _completed(command)

    monkeypatch.setattr(updater.subprocess, "run", fake_run)

    result = updater.update_project(tmp_path)

    assert result.ok is False
    assert "ветке main" in result.message
    assert commands == [
        ["git", "fetch", "origin", "main"],
        ["git", "status", "--porcelain"],
        ["git", "branch", "--show-current"],
    ]


def test_update_project_requires_git_copy(tmp_path):
    result = updater.update_project(tmp_path)

    assert result.ok is False
    assert "только в копии проекта" in result.message
