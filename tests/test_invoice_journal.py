import json

import pytest

from modules import invoice_journal


@pytest.fixture(autouse=True)
def _isolated_invoice_data(tmp_path, monkeypatch):
    data_dir = tmp_path / "data"
    monkeypatch.setattr(invoice_journal, "DATA_DIR", data_dir)
    monkeypatch.setattr(invoice_journal, "INVOICE_OCR_JOURNAL_FILE", data_dir / "invoice_ocr_journal.json")
    monkeypatch.setattr(invoice_journal, "INVOICE_OCR_PHOTOS_FOLDER", data_dir / "invoice_ocr_photos")


def _line(**overrides):
    return {
        "name": "Банан",
        "unit": "кг",
        "quantity": "25",
        "unit_price": "140",
        "line_total": "3500",
        **overrides,
    }


def test_stages_photos_under_generated_invoice_folder():
    invoice_id, references = invoice_journal.stage_invoice_photos([(b"photo", ".jpg")])

    assert len(invoice_id) == 32
    assert references == [f"invoice_ocr_photos/{invoice_id}/photo-01.jpg"]
    assert (invoice_journal.DATA_DIR / references[0]).read_bytes() == b"photo"


def test_discard_removes_only_its_own_draft_folder():
    first_id, _ = invoice_journal.stage_invoice_photos([(b"first", ".jpg")])
    second_id, second_refs = invoice_journal.stage_invoice_photos([(b"second", ".png")])

    invoice_journal.discard_staged_invoice(first_id)

    assert not (invoice_journal.INVOICE_OCR_PHOTOS_FOLDER / first_id).exists()
    assert (invoice_journal.DATA_DIR / second_refs[0]).read_bytes() == b"second"
    assert second_id != first_id


def test_append_saves_confirmed_invoice_and_decimal_total():
    invoice_id, refs = invoice_journal.stage_invoice_photos([(b"photo", ".jpg")])

    entry = invoice_journal.append_invoice_entry(
        invoice_id,
        "заказ.xlsx",
        "Маршрут №1",
        refs,
        [_line(line_total="3500.50"), _line(name="Молоко", line_total="12.25")],
    )

    assert entry["total"] == "3512.75"
    assert entry["order_file"] == "заказ.xlsx"
    entries = invoice_journal.load_invoice_entries()
    assert entries[0]["id"] == invoice_id
    assert len(entries[0]["lines"]) == 2


def test_invalid_line_does_not_create_journal_entry():
    invoice_id, refs = invoice_journal.stage_invoice_photos([(b"photo", ".jpg")])

    with pytest.raises(invoice_journal.InvoiceJournalError, match="Количество"):
        invoice_journal.append_invoice_entry(
            invoice_id,
            "заказ.xlsx",
            "Маршрут №1",
            refs,
            [_line(quantity="0")],
        )

    assert not invoice_journal.INVOICE_OCR_JOURNAL_FILE.exists()


def test_corrupt_journal_is_not_overwritten():
    invoice_journal.INVOICE_OCR_JOURNAL_FILE.parent.mkdir(parents=True)
    invoice_journal.INVOICE_OCR_JOURNAL_FILE.write_text("{bad json", encoding="utf-8")

    with pytest.raises(invoice_journal.InvoiceJournalError, match="не был перезаписан"):
        invoice_journal.load_invoice_entries()

    assert invoice_journal.INVOICE_OCR_JOURNAL_FILE.read_text(encoding="utf-8") == "{bad json"
