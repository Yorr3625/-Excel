def remove_unused_rows_and_cols(ws):
    """Удаляет служебную строку №2 и столбцы №2-3, которые не нужны."""

    ws.delete_rows(2)
    ws.delete_cols(2, 2)


def delete_columns_by_text(ws, texts):
    """
    Удаляет все столбцы, в которых хотя бы одна ячейка
    содержит один из текстов из списка texts (без учёта регистра).
    """

    cols_to_delete = []

    for row in ws.iter_rows():

        for cell in row:

            if not cell.value:
                continue

            value = str(cell.value).lower()

            for text in texts:

                if text.lower() in value:
                    cols_to_delete.append(cell.column)
                    break

    # удаляем с конца, чтобы номера столбцов не сбились
    for col_num in sorted(set(cols_to_delete), reverse=True):
        ws.delete_cols(col_num)
