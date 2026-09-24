import os

import pytest
from starlette.testclient import TestClient

from modules import paths
from modules.processed_files import (
    DOWNLOAD_TICKET_TTL_SECONDS,
    ProcessedFileError,
    consume_download_ticket,
    create_download_ticket,
    list_processed_files,
    resolve_processed_file,
)
from orders_dashboard.orders_dashboard import custom_api


@pytest.fixture
def processed_folder(tmp_path, monkeypatch):
    folder = tmp_path / "processed_orders"
    monkeypatch.setattr(paths, "PROCESSED_FOLDER", folder)
    return folder


def test_list_processed_files_returns_newest_xlsx_with_metadata(processed_folder):
    older = processed_folder / "23.09.26" / "старый.xlsx"
    newer = processed_folder / "24.09.26" / "новый.xlsx"
    older.parent.mkdir(parents=True)
    newer.parent.mkdir(parents=True)
    older.write_bytes(b"old")
    newer.write_bytes(b"new file")
    os.utime(older, (100, 100))
    os.utime(newer, (200, 200))
    (newer.parent / "не Excel.txt").write_text("skip", encoding="utf-8")
    other_folder = processed_folder / "other"
    other_folder.mkdir()
    (other_folder / "другой.xlsx").write_bytes(b"skip")

    entries = list_processed_files()

    assert [entry["relative_path"] for entry in entries] == [
        "24.09.26/новый.xlsx",
        "23.09.26/старый.xlsx",
    ]
    assert entries[0]["filename"] == "новый.xlsx"
    assert entries[0]["folder"] == "24.09.26"
    assert entries[0]["size"] == 8
    assert entries[0]["size_label"] == "8 Б"


def test_list_processed_files_returns_empty_when_folder_is_missing(processed_folder):
    assert list_processed_files() == []


def test_resolve_processed_file_rejects_paths_outside_root(processed_folder):
    with pytest.raises(ProcessedFileError):
        resolve_processed_file("../outside.xlsx")
    with pytest.raises(ProcessedFileError):
        resolve_processed_file("24.09.26/../outside.xlsx")
    with pytest.raises(ProcessedFileError):
        resolve_processed_file("24.09.26/report.pdf")
    with pytest.raises(ProcessedFileError):
        resolve_processed_file("other/другой.xlsx")
    with pytest.raises(ProcessedFileError):
        resolve_processed_file("24.09.26//report.xlsx")
    with pytest.raises(ProcessedFileError):
        resolve_processed_file("C:/outside.xlsx")


def test_resolve_processed_file_rejects_symlink(processed_folder, tmp_path):
    target = tmp_path / "outside.xlsx"
    target.write_bytes(b"outside")
    link = processed_folder / "24.09.26" / "link.xlsx"
    link.parent.mkdir(parents=True)
    try:
        link.symlink_to(target)
    except (OSError, NotImplementedError):
        pytest.skip("Создание symlink недоступно в окружении теста")

    assert list_processed_files() == []
    with pytest.raises(ProcessedFileError):
        resolve_processed_file("24.09.26/link.xlsx")


def test_download_ticket_is_single_use_and_serves_file(processed_folder):
    output = processed_folder / "24.09.26" / "заказ.xlsx"
    output.parent.mkdir(parents=True)
    output.write_bytes(b"xlsx bytes")
    ticket = create_download_ticket("24.09.26/заказ.xlsx")

    client = TestClient(custom_api)
    response = client.get(f"/api/processed-files/download/{ticket}")

    assert response.status_code == 200
    assert response.content == b"xlsx bytes"
    assert response.headers["cache-control"] == "no-store"
    assert "attachment" in response.headers["content-disposition"]
    assert client.get(f"/api/processed-files/download/{ticket}").status_code == 404


def test_download_ticket_rechecks_file_and_rejects_expired(processed_folder, monkeypatch):
    output = processed_folder / "24.09.26" / "заказ.xlsx"
    output.parent.mkdir(parents=True)
    output.write_bytes(b"xlsx bytes")
    ticket = create_download_ticket("24.09.26/заказ.xlsx")
    output.unlink()

    with pytest.raises(ProcessedFileError):
        consume_download_ticket(ticket)

    output.write_bytes(b"xlsx bytes")
    monkeypatch.setattr("modules.processed_files.time.monotonic", lambda: 1000.0)
    second_ticket = create_download_ticket("24.09.26/заказ.xlsx")
    monkeypatch.setattr(
        "modules.processed_files.time.monotonic",
        lambda: 1000.0 + DOWNLOAD_TICKET_TTL_SECONDS + 1,
    )
    with pytest.raises(ProcessedFileError):
        consume_download_ticket(second_ticket)


def test_download_endpoint_rejects_unknown_ticket():
    assert TestClient(custom_api).get("/api/processed-files/download/not-a-ticket").status_code == 404
