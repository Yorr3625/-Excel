from datetime import datetime
from typing import TypedDict

import reflex as rx

from orders_dashboard.components import (
    design_button, design_heading, design_icon, design_page,
    employee_avatar, employee_role_pill, metric_card, personnel_field, status_pill,
)
from orders_dashboard.pages.assignments import EmployeeView, employee_view
from orders_dashboard import theme as ui

STATUS_LABELS = {"unmarked": "Не отмечен", "present": "Пришёл", "late": "Опоздал", "absent": "Отсутствует"}


class AttendanceRow(EmployeeView):
    vehicle: str
    status: str
    status_label: str
    arrived_at: str
    comment: str
    delay: str


class AttendanceGroup(TypedDict):
    title: str
    count: int
    rows: list[AttendanceRow]


def attendance_row_view(employee: dict, record: dict, vehicle: str, shift_start: str) -> AttendanceRow:
    status = record.get("status", "unmarked")
    arrived_at = record.get("arrived_at", "")
    delay = ""
    if status == "late" and arrived_at:
        arrival = datetime.strptime(arrived_at, "%H:%M")
        start = datetime.strptime(record.get("shift_start", shift_start), "%H:%M")
        minutes = int((arrival - start).total_seconds() // 60)
        delay = f"+{minutes} мин" if minutes > 0 else ""
    return {
        **employee_view(employee), "vehicle": vehicle or record.get("vehicle_name", "") or "—",
        "status": status, "status_label": STATUS_LABELS[status], "arrived_at": arrived_at or "—",
        "comment": record.get("comment", ""), "delay": delay,
    }


def attendance_row(item, *, State):
    return rx.el.div(
        rx.el.div(employee_avatar(item["initials"]), rx.el.strong(item["name"]), class_name="personnel-person attendance-name"),
        employee_role_pill(item["role"]),
        rx.el.span(item["vehicle"], class_name="attendance-vehicle"),
        status_pill(item["status_label"]),
        rx.el.div(rx.el.span(item["arrived_at"]), rx.cond(item["delay"] != "", rx.el.span(item["delay"], class_name="attendance-delay")), class_name="attendance-arrival"),
        rx.el.span(item["comment"], class_name="attendance-comment"),
        rx.menu.root(
            rx.menu.trigger(rx.el.button(design_icon("menu", 16), aria_label="Отметить " + item["name"], class_name="personnel-icon-button", type="button")),
            rx.menu.content(
                rx.menu.item("Пришёл сейчас", on_click=State.mark_attendance(item["id"], "present")),
                rx.menu.item("Отсутствует", on_click=State.mark_attendance(item["id"], "absent")),
                rx.menu.item("Изменить время и комментарий", on_click=State.edit_attendance(item["id"])),
                rx.menu.separator(),
                rx.menu.item("Снять отметку", on_click=State.mark_attendance(item["id"], "unmarked")),
            ),
        ),
        class_name="attendance-row", role="listitem",
    )


def attendance_editor(*, State):
    return rx.cond(
        State.attendance_edit_id != "",
        rx.el.section(
            rx.el.h2("Отметка: ", State.attendance_edit_name),
            rx.el.form(
                rx.el.label("Статус", rx.el.select(
                    rx.el.option("Пришёл / опоздал (по времени)", value="present"),
                    rx.el.option("Отсутствует", value="absent"),
                    rx.el.option("Не отмечен", value="unmarked"),
                    name="status", default_value=State.attendance_edit_status, class_name="personnel-select",
                ), class_name="personnel-field"),
                personnel_field("Время прихода", "arrived_at", State.attendance_edit_time, "time"),
                personnel_field("Комментарий / причина отсутствия", "comment", State.attendance_edit_comment, max_length=1000),
                rx.el.div(rx.el.button("Сохранить отметку", type="submit", class_name="button button-primary"), design_button("Отмена", State.close_attendance_editor), class_name="personnel-inline"),
                on_submit=State.save_attendance_record, reset_on_submit=False,
                class_name="personnel-form", key=State.attendance_edit_id + State.attendance_edit_time,
            ),
            class_name="personnel-panel",
        ),
    )


def attendance_page(*, State):
    return design_page(
        design_heading("Посещаемость", "Команда", "Учёт рабочего времени и история отметок по датам."),
        rx.el.div(
            rx.el.div(
                design_button("Назад", State.change_attendance_date(-1), "chevron_left"),
                rx.el.label("Дата посещаемости", rx.el.input(type="date", value=State.personnel_date, on_change=State.set_personnel_date), class_name="personnel-field"),
                design_button("Вперёд", State.change_attendance_date(1), "chevron_right"),
                class_name="personnel-inline",
            ),
            rx.el.input(value=State.attendance_search, on_change=State.set_attendance_search, placeholder="Поиск сотрудников…", aria_label="Поиск сотрудников", class_name="personnel-search"),
            design_button("Обновить", State.load_attendance_page, "refresh"),
            class_name="personnel-toolbar",
        ),
        rx.el.div(
            metric_card("Всего", State.attendance_total),
            metric_card("Пришли", State.attendance_present, value_color=ui.STATUS_GREEN_TEXT),
            metric_card("Опоздали", State.attendance_late, value_color=ui.STATUS_AMBER_TEXT),
            metric_card("Отсутствуют", State.attendance_absent, value_color=ui.STATUS_RED_TEXT),
            class_name="attendance-summary",
        ),
        rx.el.p("Начало смены: ", State.shift_start, ". Изменить можно в настройках. Опоздание определяется по времени прихода.", class_name="personnel-message"),
        rx.cond(State.attendance_message != "", rx.el.p(State.attendance_message, role="status", class_name="personnel-message")),
        attendance_editor(State=State),
        rx.el.div(
            rx.el.span("Сотрудник"), rx.el.span("Роль"), rx.el.span("Машина"), rx.el.span("Статус"),
            rx.el.span("Время прихода"), rx.el.span("Комментарий"), rx.el.span(),
            class_name="attendance-row attendance-table-heading", aria_hidden=True,
        ),
        rx.foreach(State.attendance_groups, lambda group: rx.el.details(
            rx.el.summary(rx.el.strong(group["title"]), rx.el.span(group["count"], class_name="personnel-count")),
            rx.el.div(
                rx.foreach(group["rows"], lambda item: attendance_row(item, State=State)),
                rx.cond(group["rows"].length() == 0, rx.el.p("Нет сотрудников", class_name="personnel-empty")),
                role="list",
            ),
            open=True, class_name="attendance-group",
        )),
        class_name="personnel-page",
    )
