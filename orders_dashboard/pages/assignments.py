from typing import TypedDict

import reflex as rx

from orders_dashboard.components import (
    design_button, design_heading, design_icon, design_page,
    employee_avatar, employee_role_pill, personnel_field,
)


class EmployeeView(TypedDict):
    id: str
    name: str
    initials: str
    role: str


class VehicleColumn(TypedDict):
    id: str
    name: str
    plate: str
    count_label: str
    employees: list[EmployeeView]
    route: str
    departure: str


def employee_view(employee: dict) -> EmployeeView:
    return {
        "id": employee["id"], "name": employee["name"],
        "initials": "".join(part[0] for part in employee["name"].split()[:2]).upper(),
        "role": employee.get("role", "driver"),
    }


def employee_card(item, vehicle_id, *, State):
    return rx.el.article(
        rx.el.div(
            employee_avatar(item["initials"]),
            rx.el.div(rx.el.strong(item["name"]), employee_role_pill(item["role"]), class_name="personnel-identity"),
            class_name="personnel-person",
        ),
        rx.el.select(
            rx.foreach(State.assignment_vehicle_options, lambda option: rx.el.option(option["label"], value=option["id"])),
            value=vehicle_id,
            on_change=lambda value: State.assign_employee(item["id"], value),
            aria_label="Назначить машину: " + item["name"],
            class_name="personnel-select",
        ),
        class_name="personnel-employee-card",
    )


def vehicle_column(item, *, State):
    return rx.el.section(
        rx.el.div(
            rx.el.div(design_icon("truck", 20), rx.el.h2(item["name"]), rx.el.span(item["count_label"], class_name="personnel-count"), class_name="personnel-column-title"),
            rx.el.div(
                rx.el.span(item["plate"], class_name="personnel-plate"),
                rx.el.div(
                    rx.el.button(design_icon("edit", 16), type="button", on_click=State.edit_assignment_vehicle(item["id"]), aria_label="Изменить " + item["name"], class_name="personnel-icon-button"),
                    rx.el.button(design_icon("trash", 16), type="button", on_click=State.ask_delete_assignment_vehicle(item["id"]), aria_label="Удалить " + item["name"], class_name="personnel-icon-button"),
                    class_name="personnel-inline",
                ),
                class_name="personnel-column-actions",
            ),
        ),
        rx.el.div(
            rx.foreach(item["employees"], lambda employee: employee_card(employee, item["id"], State=State)),
            rx.cond(item["employees"].length() == 0, rx.el.p("Нет сотрудников", class_name="personnel-empty")),
            class_name="personnel-column-members",
        ),
        rx.el.dl(
            rx.el.div(rx.el.dt("Маршрут"), rx.el.dd(item["route"])),
            rx.el.div(rx.el.dt("Время выезда"), rx.el.dd(item["departure"])),
            class_name="personnel-vehicle-info",
        ),
        class_name="personnel-column",
    )


def vehicle_form(*, State):
    return rx.cond(
        State.assignment_form_open,
        rx.el.section(
            rx.el.h2(rx.cond(State.assignment_vehicle_id == "", "Новая машина", "Изменить машину")),
            rx.el.form(
                personnel_field("Название машины", "name", State.assignment_vehicle_name, required=True),
                personnel_field("Госномер", "plate", State.assignment_vehicle_plate, required=True),
                personnel_field("Маршрут", "route", State.assignment_vehicle_route),
                personnel_field("Время выезда", "departure", State.assignment_vehicle_departure, "time", required=True),
                personnel_field("Мест в экипаже", "capacity", State.assignment_vehicle_capacity, "number", min="1", required=True),
                rx.el.div(
                    rx.el.button("Сохранить", type="submit", class_name="button button-primary"),
                    design_button("Отмена", State.close_assignment_vehicle_form),
                    class_name="personnel-inline",
                ),
                on_submit=State.save_assignment_vehicle,
                reset_on_submit=False,
                class_name="personnel-form",
                key=State.assignment_vehicle_id + State.assignment_vehicle_name,
            ),
            class_name="personnel-panel",
        ),
    )


def assignments_page(*, State):
    return design_page(
        design_heading("Распределение по машинам", "Команда и транспорт", "Состав экипажей, маршруты и время выезда на выбранную дату.",
                       design_button("Добавить машину", State.clear_assignment_vehicle_form, "plus", primary=True)),
        rx.el.div(
            rx.el.label("Дата распределения", rx.el.input(type="date", value=State.personnel_date, on_change=State.set_personnel_date), class_name="personnel-field"),
            rx.el.input(value=State.assignment_search, on_change=State.set_assignment_search, placeholder="Поиск сотрудников…", aria_label="Поиск сотрудников", class_name="personnel-search"),
            design_button("Обновить", State.load_assignment_page, "refresh"),
            class_name="personnel-toolbar",
        ),
        rx.cond(State.assignment_status != "", rx.el.p(State.assignment_status, role="status", class_name="personnel-message")),
        vehicle_form(State=State),
        rx.cond(
            State.assignment_delete_id != "",
            rx.el.section(
                rx.el.p("Удалить машину из справочника? Сотрудники вернутся в свободный список. История посещаемости сохранится."),
                rx.el.div(design_button("Удалить машину", State.delete_assignment_vehicle, "trash"), design_button("Отмена", State.cancel_delete_assignment_vehicle), class_name="personnel-inline"),
                class_name="personnel-panel", role="alert",
            ),
        ),
        rx.el.div(
            rx.el.section(
                rx.el.div(design_icon("users", 20), rx.el.h2("Не распределены"), rx.el.span(State.assignment_unassigned.length(), class_name="personnel-count"), class_name="personnel-column-title"),
                rx.el.div(
                    rx.foreach(State.assignment_unassigned, lambda employee: employee_card(employee, "", State=State)),
                    rx.cond(State.assignment_unassigned.length() == 0, rx.el.p("Свободных сотрудников нет", class_name="personnel-empty")),
                    class_name="personnel-column-members",
                ),
                class_name="personnel-column personnel-unassigned",
            ),
            rx.foreach(State.assignment_columns, lambda vehicle: vehicle_column(vehicle, State=State)),
            rx.el.button(design_icon("plus", 24), "Добавить машину", on_click=State.clear_assignment_vehicle_form, type="button", class_name="personnel-add-column"),
            class_name="personnel-board",
        ),
        class_name="personnel-page",
    )
