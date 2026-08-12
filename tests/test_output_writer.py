import os
from datetime import datetime

from modules.output_writer import build_output_path, open_result
from modules.paths import PROCESSED_FOLDER


def test_build_output_path_creates_dated_folder_and_filename(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    now = datetime(2026, 8, 11, 9, 30, 3)

    output_file, date_folder = build_output_path(now)

    assert date_folder == "11.08.26"
    assert output_file == os.path.join(
        PROCESSED_FOLDER, "11.08.26", "заказ_обработан_09-30-03.xlsx"
    )
    assert os.path.isdir(os.path.join(PROCESSED_FOLDER, "11.08.26"))


def test_open_result_opens_file_when_setting_enabled(monkeypatch):
    calls = []
    monkeypatch.setattr(os, "startfile", lambda path: calls.append(path), raising=False)

    open_result("out.xlsx", {"open_file_after_processing": True, "open_folder_after_processing": False})

    assert calls == ["out.xlsx"]


def test_open_result_opens_folder_when_only_that_setting_enabled(monkeypatch):
    calls = []
    monkeypatch.setattr(os, "startfile", lambda path: calls.append(path), raising=False)

    open_result(
        os.path.join(PROCESSED_FOLDER, "out.xlsx"),
        {"open_file_after_processing": False, "open_folder_after_processing": True},
    )

    assert calls == [str(PROCESSED_FOLDER)]


def test_open_result_does_nothing_when_both_settings_disabled(monkeypatch):
    calls = []
    monkeypatch.setattr(os, "startfile", lambda path: calls.append(path), raising=False)

    open_result("out.xlsx", {"open_file_after_processing": False, "open_folder_after_processing": False})

    assert calls == []
