import asyncio
from io import BytesIO
from pathlib import Path
from types import SimpleNamespace

from openpyxl import Workbook, load_workbook
from starlette.datastructures import UploadFile

import orders_dashboard.orders_dashboard as dashboard


def upload_state():
    return SimpleNamespace(
        status="", selected_file="", uploaded_file_path="", order_mail_metadata={"old": True},
        order_record_warning="", output_file="old.xlsx", log_file="old.log", error_text="old error",
        duplicate_note="", _reset_preview=lambda: None, detect_and_set_mode=lambda: None,
    )


def test_manual_excel_upload_saves_bytes_and_updates_selected_file(tmp_path, monkeypatch):
    book = Workbook()
    book.active.append(["Товар", "Магазин"])
    book.active.append(["Яблоки", 12])
    content = BytesIO()
    book.save(content)
    content.seek(0)
    monkeypatch.setattr(dashboard.rx, "get_upload_dir", lambda: tmp_path)
    monkeypatch.setattr(dashboard, "was_processed", lambda name: None)
    state = upload_state()
    asyncio.run(dashboard.State.handle_upload.fn(state, [UploadFile(content, filename="заказ.xlsx")]))
    saved = tmp_path / "заказ.xlsx"
    assert saved.exists()
    loaded = load_workbook(saved)
    assert loaded.active.cell(2, 2).value == 12
    loaded.close()
    assert state.selected_file == "заказ.xlsx"
    assert state.uploaded_file_path == str(saved)
    assert state.status == "Файл загружен: заказ.xlsx"
    assert state.order_mail_metadata is None
    assert state.output_file == state.log_file == state.error_text == ""


def test_manual_upload_without_selection_has_clear_status():
    state = upload_state()
    asyncio.run(dashboard.State.handle_upload.fn(state, []))
    assert state.status == "Сначала выберите Excel-файл"
    assert state.uploaded_file_path == ""


def test_manual_upload_rejects_non_excel_without_writing(tmp_path, monkeypatch):
    monkeypatch.setattr(dashboard.rx, "get_upload_dir", lambda: tmp_path)
    state = upload_state()
    asyncio.run(dashboard.State.handle_upload.fn(state, [UploadFile(BytesIO(b"text"), filename="notes.txt")]))
    assert "Неподдерживаемый формат" in state.status
    assert not list(tmp_path.iterdir())


def test_upload_button_uses_same_file_context_as_picker():
    def walk(component):
        yield component
        for child in component.children:
            yield from walk(child)

    button = next(component for component in walk(dashboard.order_panel())
                  if component.tag == "Button" and "handle_upload" in str(component.event_triggers))
    rendered = str(button.render())
    assert 'filesById?.["order_upload"]' in rendered
    assert '"uploadFiles"' in rendered
    picker = dashboard.upload_area()
    assert str(picker.children[0].id) == dashboard.UPLOAD_ID
    assert len(picker.children[0].children) == 2  # Native input and one content container.
    stylesheet = (Path(__file__).parents[1] / "assets/dashboard-design.css").read_text(encoding="utf-8")
    assert '.file-picker input[type="file"] { display:block !important;' in stylesheet
