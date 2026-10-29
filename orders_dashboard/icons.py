"""Shared Tabler icon components."""
import reflex as rx


TABLER_ICON_MAP = {
    "layout_dashboard": "IconLayoutDashboard",
    "package": "IconPackage",
    "route": "IconRoute",
    "truck": "IconTruck",
    "history": "IconHistory",
    "settings": "IconSettings",
    "boxes": "IconPackages",
    "sun": "IconSun",
    "moon": "IconMoon",
    "upload": "IconUpload",
    "file_spreadsheet": "IconFileSpreadsheet",
    "file_pdf": "IconFileTypePdf",
    "chart_no_axes_column": "IconChartBar",
    "map": "IconMap",
    "award": "IconAward",
    "list": "IconList",
    "map_pin": "IconMapPin",
    "mail": "IconMail",
    "inbox": "IconInbox",
    "refresh": "IconRefresh",
    "circle_x": "IconCircleX",
    "x": "IconX",
    "plus": "IconPlus",
    "camera": "IconCamera",
    "circle_check": "IconCircleCheck",
    "circle": "IconCircle",
    "store": "IconBuildingStore",
    "fuel": "IconGasStation",
    "triangle_alert": "IconAlertTriangle",
    "key": "IconKey",
    "info": "IconInfoCircle",
    "save": "IconDeviceFloppy",
    "folder": "IconFolderOpen",
    "scale": "IconScale",
    "edit": "IconEdit",
    "ai": "IconSparkles",
    "send": "IconSend",
    "warehouse": "IconBuildingWarehouse",
    "search": "IconSearch",
    "chevron_left": "IconChevronLeft",
    "chevron_right": "IconChevronRight",
    "chevron_down": "IconChevronDown",
    "arrow_right": "IconArrowRight",
    "clock": "IconClock",
    "file_text": "IconFileText",
    "layout_grid": "IconLayoutGrid",
    "lock": "IconLock",
    "menu": "IconMenu",
    "log_out": "IconLogout",
    "panel_left_open": "IconLayoutSidebarLeftExpand",
    "panel_left_close": "IconLayoutSidebarLeftCollapse",
    "refresh_cw": "IconRefresh",
    "undo_2": "IconArrowBackUp",
    "user": "IconUser",
    "users": "IconUsers",
    "calendar_check": "IconCalendarCheck",
    "pencil": "IconPencil",
    "trash": "IconTrash",
}


class TablerIcon(rx.Component):
    """Outline icon from the single Tabler Icons set used by the web UI."""

    library = "@tabler/icons-react"
    tag = "IconHelpCircle"

    size: rx.Var[int]
    color: rx.Var[str]
    stroke_width: rx.Var[float]

    @classmethod
    def create(cls, **props):
        name = props.pop("tag", "")
        props["tag"] = TABLER_ICON_MAP.get(name, "IconHelpCircle")
        props.setdefault("stroke_width", 1.8)
        return super().create(**props)


fa_icon = TablerIcon.create
