import json
import zipfile
from pathlib import Path

import pytest

from modules import backup


def _write_json(root: Path, relative: str, value) -> None:
    path = root / Path(*relative.split("/"))
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False), encoding="utf-8")


def _manifest(present: set[str]) -> dict:
    return {
        "format_version": backup.BACKUP_FORMAT_VERSION,
        "app_version": "1.0.0",
        "created_at": "2026-08-29T12:00:00+03:00",
        "reason": "тест",
        "files": [
            {"path": relative, "present": relative in present}
            for relative in backup._BACKUP_RELATIVE_FILES
        ],
    }


def test_create_backup_contains_state_and_manifest_but_not_workbooks(tmp_path):
    _write_json(tmp_path, "data/volume_history.json", [{"date": "2026-08-29"}])
    _write_json(tmp_path, "data/processed_files.json", {"заказ.xlsx": "2026-08-29"})
    _write_json(tmp_path, "config/settings.json", {"create_logs": True})
    _write_json(tmp_path, "config/stores_city.json", {"route_1": ["Магазин"]})
    workbook = tmp_path / "data" / "orders" / "заказ.xlsx"
    workbook.parent.mkdir(parents=True)
    workbook.write_bytes(b"not part of the state backup")

    info = backup.create_backup(tmp_path / "archives", project_root=tmp_path)

    assert info.valid
    assert info.file_count == 4
    assert info.contains_secrets is False
    assert info.path.parent == (tmp_path / "archives").resolve()

    with zipfile.ZipFile(info.path) as archive:
        names = set(archive.namelist())
        manifest = json.loads(archive.read("manifest.json"))
        states = {item["path"]: item["present"] for item in manifest["files"]}

    assert states["data/volume_history.json"] is True
    assert states["config/stores_city.json"] is True
    assert "data/volume_history.json" in names
    assert "data/orders/заказ.xlsx" not in names
    assert "config/mail.json" not in names


def test_backup_directory_round_trip(tmp_path):
    selected = tmp_path / "my backups"

    saved = backup.save_backup_directory(selected, project_root=tmp_path)

    assert saved == selected.resolve()
    assert backup.load_backup_directory(tmp_path) == selected.resolve()
    assert json.loads(
        (tmp_path / "config" / "backup.json").read_text(encoding="utf-8")
    ) == {"directory": str(selected)}


def test_list_backups_marks_invalid_archives(tmp_path):
    valid = backup.create_backup(tmp_path / "archives", project_root=tmp_path)
    invalid = tmp_path / "archives" / "broken.zip"
    invalid.write_bytes(b"not a zip")

    items = backup.list_backups(tmp_path / "archives", project_root=tmp_path)

    by_name = {item.name: item for item in items}
    assert by_name[valid.name].valid is True
    assert by_name["broken.zip"].valid is False
    assert by_name["broken.zip"].error


def test_restore_replaces_state_removes_absent_files_and_makes_safety_copy(tmp_path):
    backup_dir = tmp_path / "archives"
    backup.save_backup_directory(backup_dir, project_root=tmp_path)
    _write_json(tmp_path, "data/volume_history.json", [{"route_1": 10}])
    _write_json(tmp_path, "config/settings.json", {"create_logs": True})
    source = backup.create_backup(backup_dir, project_root=tmp_path)

    _write_json(tmp_path, "data/volume_history.json", [{"route_1": 999}])
    _write_json(tmp_path, "data/mail_items.json", [{"message_id": "new"}])
    _write_json(tmp_path, "config/settings.json", {"create_logs": False})

    result = backup.restore_backup(source.path, project_root=tmp_path)

    assert result.archive == source.path.resolve()
    assert result.safety_backup is not None
    assert json.loads(
        (tmp_path / "data" / "volume_history.json").read_text(encoding="utf-8")
    ) == [{"route_1": 10}]
    assert json.loads(
        (tmp_path / "config" / "settings.json").read_text(encoding="utf-8")
    ) == {"create_logs": True}
    assert not (tmp_path / "data" / "mail_items.json").exists()
    assert result.removed_files == ("data/mail_items.json",)
    assert len(list(backup_dir.glob("*.zip"))) == 2


def test_restore_rejects_path_traversal_without_touching_project(tmp_path):
    archive = tmp_path / "malicious.zip"
    with zipfile.ZipFile(archive, "w") as zipped:
        zipped.writestr("manifest.json", json.dumps(_manifest(set())))
        zipped.writestr("../outside.json", b"should not be written")

    with pytest.raises(backup.BackupError, match="небезопасный путь"):
        backup.restore_backup(archive, project_root=tmp_path)

    assert not (tmp_path.parent / "outside.json").exists()


def test_restore_rejects_invalid_json_before_changing_current_state(tmp_path):
    current = tmp_path / "config" / "settings.json"
    current.parent.mkdir(parents=True)
    current.write_text('{"create_logs": true}', encoding="utf-8")
    archive = tmp_path / "invalid-content.zip"
    manifest = _manifest({"config/settings.json"})

    with zipfile.ZipFile(archive, "w") as zipped:
        zipped.writestr("manifest.json", json.dumps(manifest))
        zipped.writestr("config/settings.json", b"{broken")

    with pytest.raises(backup.BackupError, match="config/settings.json"):
        backup.restore_backup(archive, project_root=tmp_path, safety_backup=False)

    assert current.read_text(encoding="utf-8") == '{"create_logs": true}'


def test_backup_with_mail_config_marks_sensitive_contents(tmp_path):
    _write_json(tmp_path, "config/mail.json", {"email": "user@example.com", "app_password": "secret"})

    info = backup.create_backup(tmp_path / "archives", project_root=tmp_path)

    assert info.contains_secrets is True
    inspected = backup.inspect_backup(info.path)
    assert inspected.valid is True
    assert inspected.contains_secrets is True
