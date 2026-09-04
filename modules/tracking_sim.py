import random
from datetime import datetime

from modules.config import load_stores


ROUTE_KEYS = [f"route_{i}" for i in range(1, 9)]
ROUTE_LABELS = [f"Машина №{i}" for i in range(1, 9)]
ROUTE_COLORS = [
    "#1f883d", "#2f6fed", "#7c5cff", "#e8590c",
    "#d6409f", "#12b886", "#795548", "#607d8b",
]

TICK_SECONDS = 1.0
BASE_SPEED_KMH = 42.0
STOP_DWELL_TICKS = 3
HARSH_EVENT_CHANCE = 0.12
FUEL_L_PER_KM = 0.28
FUEL_PRICE = 58.0


def waypoint_x(index: int, total: int) -> float:
    """X-координата (0..100) точки маршрута на условной схеме-полосе."""

    if total <= 1:
        return 50.0
    return round(6 + (index % total) * (88 / (total - 1)), 2)


def lerp_x(stop_index: int, progress: float, total: int) -> float:
    x0 = waypoint_x(stop_index, total)
    x1 = waypoint_x((stop_index + 1) % total, total)
    return round(x0 + (x1 - x0) * progress, 2)


def init_vehicles(stores_file: str, route_count: int = len(ROUTE_KEYS)) -> list[dict]:
    try:
        data = load_stores(stores_file)
    except (OSError, ValueError):
        data = {}

    vehicles = []

    for index, key in enumerate(ROUTE_KEYS[:route_count]):
        stops = list(data.get(key, []))
        waypoints = ["База"] + stops
        n = len(waypoints)
        leg_km = [round(random.uniform(4, 12), 1) for _ in range(n)] if n > 1 else []

        vehicles.append({
            "route_index": index,
            "label": ROUTE_LABELS[index],
            "color": ROUTE_COLORS[index],
            "waypoints": waypoints,
            "leg_km": leg_km,
            "stop_index": 0,
            "progress": 0.0,
            "dwell_left": 0,
            "x": waypoint_x(0, n),
            "speed_kmh": 0.0,
            "status": "Нет магазинов в маршруте" if not stops else "На базе",
            "event_flag": "none",
            "distance_km": 0.0,
            "fuel_l": 0.0,
            "cost": 0.0,
            "harsh_count": 0,
            "score": 100,
            "laps": 0,
            "progress_percent": 0,
        })

    return vehicles


def advance_tick(vehicles: list[dict]) -> tuple[list[dict], list[str]]:
    """Один шаг симуляции: возвращает обновлённые машины и новые записи журнала."""

    updated = []
    events = []

    for v in vehicles:
        n = len(v["waypoints"])

        if n <= 1:
            updated.append(v)
            continue

        nv = dict(v)

        if v["dwell_left"] > 0:
            dwell_left = v["dwell_left"] - 1
            nv["dwell_left"] = dwell_left
            nv["speed_kmh"] = 0.0
            nv["event_flag"] = "none"
            if dwell_left == 0:
                nv["status"] = "В пути"
            elif v["stop_index"] == 0:
                nv["status"] = "Погрузка на базе"
            else:
                nv["status"] = f"Разгрузка: {v['waypoints'][v['stop_index']]}"
        else:
            leg_km_list = v["leg_km"]
            leg_km = leg_km_list[v["stop_index"] % len(leg_km_list)] if leg_km_list else 6.0

            speed = max(BASE_SPEED_KMH + random.uniform(-6, 8), 5.0)
            event = "none"
            score = v["score"]
            harsh_count = v["harsh_count"]

            if random.random() < HARSH_EVENT_CHANCE:
                event = random.choice(["harsh_accel", "harsh_brake"])
                score = max(0, score - random.randint(3, 8))
                harsh_count += 1
                speed = max(speed + (14 if event == "harsh_accel" else -12), 5.0)
                target = v["waypoints"][(v["stop_index"] + 1) % n]
                kind = "резкий разгон" if event == "harsh_accel" else "резкое торможение"
                events.append(f"{datetime.now():%H:%M:%S} — {v['label']}: {kind} на подъезде к «{target}»")
            else:
                score = min(100, score + 0.4)

            distance_step = speed * TICK_SECONDS / 3600
            progress = v["progress"] + (distance_step / leg_km if leg_km else 1.0)
            fuel_step = distance_step * FUEL_L_PER_KM * (1.25 if event != "none" else 1.0)

            nv["speed_kmh"] = round(speed, 1)
            nv["event_flag"] = event
            nv["score"] = round(score)
            nv["harsh_count"] = harsh_count
            nv["distance_km"] = round(v["distance_km"] + distance_step, 2)
            nv["fuel_l"] = round(v["fuel_l"] + fuel_step, 2)
            nv["cost"] = round(nv["fuel_l"] * FUEL_PRICE, 0)

            if progress >= 1:
                next_index = (v["stop_index"] + 1) % n
                nv["stop_index"] = next_index
                nv["progress"] = 0.0
                nv["dwell_left"] = STOP_DWELL_TICKS
                nv["laps"] = v["laps"] + (1 if next_index == 0 else 0)
                nv["status"] = "Погрузка на базе" if next_index == 0 else f"Прибытие: {v['waypoints'][next_index]}"
                nv["progress_percent"] = round((next_index / (n - 1)) * 100)
            else:
                nv["stop_index"] = v["stop_index"]
                nv["progress"] = progress
                nv["status"] = "В пути"
                current_target = (v["stop_index"] + 1) % n
                if current_target == 0:
                    nv["progress_percent"] = 100
                else:
                    nv["progress_percent"] = round(((v["stop_index"] + progress) / (n - 1)) * 100)

        nv["x"] = (
            waypoint_x(nv["stop_index"], n)
            if nv["dwell_left"] > 0
            else lerp_x(nv["stop_index"], nv["progress"], n)
        )
        updated.append(nv)

    return updated, events


def lane_y(route_index: int) -> float:
    return 3 + route_index * 6


def build_map_svg(vehicles: list[dict]) -> str:
    lanes = len(vehicles) or 1
    height = 6 + lanes * 6
    # Intrinsic width/height (not %) keep the aspect ratio fixed, so CSS
    # "width:100%;height:auto" scales both axes uniformly — no overflow,
    # no stretched/oval markers.
    parts = [
        f'<svg viewBox="0 0 100 {height}" width="1000" height="{height * 10}" '
        'xmlns="http://www.w3.org/2000/svg" style="width:100%;height:auto;display:block;">'
    ]

    for v in vehicles:
        n = len(v["waypoints"])
        y = lane_y(v["route_index"])

        if n <= 1:
            parts.append(f'<circle cx="6" cy="{y}" r="1" fill="{v["color"]}" opacity="0.4" />')
            continue

        x0 = waypoint_x(0, n)
        x1 = waypoint_x(n - 1, n)
        parts.append(
            f'<line x1="{x0}" y1="{y}" x2="{x1}" y2="{y}" stroke="{v["color"]}" '
            f'stroke-opacity="0.28" stroke-width="0.9" />'
        )

        for j in range(n):
            wx = waypoint_x(j, n)
            radius = 1.05 if j == 0 else 0.65
            parts.append(f'<circle cx="{wx}" cy="{y}" r="{radius}" fill="{v["color"]}" opacity="0.85" />')

        if v["event_flag"] == "harsh_brake":
            parts.append(f'<circle cx="{v["x"]}" cy="{y}" r="2.2" fill="#e5484d" opacity="0.35" />')
        elif v["event_flag"] == "harsh_accel":
            parts.append(f'<circle cx="{v["x"]}" cy="{y}" r="2.2" fill="#f5a623" opacity="0.35" />')

        parts.append(
            f'<circle cx="{v["x"]}" cy="{y}" r="1.3" fill="{v["color"]}" stroke="white" stroke-width="0.3" />'
        )

    parts.append("</svg>")
    return "".join(parts)
