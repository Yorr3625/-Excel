from modules.order_positions import order_position_names


def test_order_position_names_reads_first_column_skipping_header_and_total(
    tmp_path, monkeypatch, sample_order_workbook
):
    monkeypatch.setattr("modules.order_positions.ORDERS_FOLDER", tmp_path)
    sample_order_workbook.save(tmp_path / "заказ.xlsx")

    assert order_position_names("заказ.xlsx") == ["Товар A", "Товар B"]


def test_order_position_names_deduplicates_case_insensitively(tmp_path, monkeypatch):
    from openpyxl import Workbook

    monkeypatch.setattr("modules.order_positions.ORDERS_FOLDER", tmp_path)

    wb = Workbook()
    ws = wb.active
    ws.append(["Товар", "служебный1", "служебный2", "фм 4"])
    ws.append(["служебная строка", "", "", ""])
    ws.append(["Огурец", "", "", 5])
    ws.append(["огурец", "", "", 2])
    ws.append(["Помидор", "", "", 3])
    wb.save(tmp_path / "заказ.xlsx")

    assert order_position_names("заказ.xlsx") == ["Огурец", "Помидор"]


def test_order_position_names_empty_for_missing_or_blank_filename(tmp_path, monkeypatch):
    monkeypatch.setattr("modules.order_positions.ORDERS_FOLDER", tmp_path)

    assert order_position_names("") == []
    assert order_position_names("нет такого.xlsx") == []
