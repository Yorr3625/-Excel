import re


def find_and_mark_routes(ws, groups, conflict_fill):
    """
    Проходит по всем ячейкам листа, находит совпадения с названиями
    магазинов из groups и красит ячейки в цвет соответствующего маршрута.

    Возвращает словарь со статистикой обработки:
        route_count    - сколько адресов найдено по каждому маршруту
        conflict_count - количество конфликтов (адрес попал в несколько маршрутов)
        conflict_list  - подробности по каждому конфликту
        total_found    - всего успешно определено адресов
        unknown_stores - магазины из шапки, которых нет ни в одном маршруте
    """

    route_count = {group["name"]: 0 for group in groups}
    conflict_list = []
    unknown_stores = []
    conflict_count = 0
    total_found = 0

    for row in ws.iter_rows():

        for cell in row:

            text = str(cell.value or "").lower()
            matches = _find_matching_groups(text, groups)

            # один маршрут
            if len(matches) == 1:
                cell.fill = matches[0]["fill"]
                route_count[matches[0]["name"]] += 1
                total_found += 1

            # конфликт
            elif len(matches) > 1:
                cell.fill = conflict_fill
                conflict_count += 1
                conflict_list.append(
                    {
                        "ячейка": cell.coordinate,
                        "текст": cell.value,
                        "маршруты": [group["name"] for group in matches],
                    }
                )

            # неизвестный магазин (только в шапке)
            elif (
                len(matches) == 0
                and cell.row == 1
                and cell.column > 1
                and cell.value
            ):
                unknown_stores.append(str(cell.value))

    return {
        "route_count": route_count,
        "conflict_count": conflict_count,
        "conflict_list": conflict_list,
        "total_found": total_found,
        "unknown_stores": unknown_stores,
    }


def _find_matching_groups(text, groups):
    """Возвращает список групп маршрутов, чьё имя нашлось в тексте ячейки."""

    matches = []

    for group in groups:

        for name in group["names"]:

            # защита от ФМ 4 -> ФМ 42 (совпадение только по целому слову)
            pattern = r"\b" + re.escape(name.lower()) + r"\b"

            if re.search(pattern, text):
                matches.append(group)
                break

    return matches
