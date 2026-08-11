from modules.reporter import format_summary


def _stats(**overrides):
    stats = {
        "route_count": {"Маршрут №1": 2, "Маршрут №2": 1},
        "conflict_count": 0,
        "conflict_list": [],
        "unknown_stores": [],
    }
    stats.update(overrides)
    return stats


def test_format_summary_includes_output_and_log_paths():
    text = format_summary("out.xlsx", _stats(), "logs/лог.txt")

    assert "Создан файл: out.xlsx" in text
    assert "Лог сохранён: logs/лог.txt" in text


def test_format_summary_includes_route_totals_with_percentages():
    stats = _stats(route_totals={"Маршрут №1": 75, "Маршрут №2": 25})

    text = format_summary("out.xlsx", stats, "log.txt")

    assert "Маршрут №1: 75 (75.0%)" in text
    assert "Маршрут №2: 25 (25.0%)" in text
    assert "Общий итог: 100" in text


def test_format_summary_handles_zero_grand_total_without_division_error():
    stats = _stats(route_totals={"Маршрут №1": 0, "Маршрут №2": 0})

    text = format_summary("out.xlsx", stats, "log.txt")

    assert "Маршрут №1: 0 (0.0%)" in text


def test_format_summary_lists_conflicts_and_unknown_stores():
    stats = _stats(
        conflict_count=1,
        conflict_list=[{"ячейка": "B2", "текст": "фм 4 фм 42", "маршруты": ["Маршрут №1", "Маршрут №2"]}],
        unknown_stores=["Неизвестный магазин"],
    )

    text = format_summary("out.xlsx", stats, "log.txt")

    assert "Ошибочные адреса:" in text
    assert "B2 | фм 4 фм 42" in text
    assert "Неизвестные магазины:" in text
    assert "Неизвестный магазин" in text
