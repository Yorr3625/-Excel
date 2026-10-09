from copy import deepcopy
import json
from pathlib import Path
import shutil
import subprocess
from types import SimpleNamespace

import pytest

import orders_dashboard.orders_dashboard as dashboard


@pytest.fixture
def state():
    state = SimpleNamespace(
        active_route_count=3, selected_route_index=0,
        route_stores=[["А", "Б", "В"], ["Г"], []],
        route_editor_baseline=[["А", "Б", "В"], ["Г"], []],
        template_selected_stores=[], template_move_stores=[],
        template_move_source=-1, template_move_target="", template_move_error="",
        template_discard_open=False, search_query="", routes_status="",
        route_add_index=-1, new_store_input="",
    )
    for name in (
        "reset_template_selection", "template_filtered_names", "move_template_stores",
        "close_template_move",
    ):
        method = getattr(dashboard.State, name)
        fn = getattr(method, "fn", method)
        setattr(state, name, fn.__get__(state))
    return state


def call(state, name, *args):
    return getattr(dashboard.State, name).fn(state, *args)


def computed(state, name):
    return dashboard.State.__dict__[name].fget(state)


def test_move_preserves_order_and_baseline_without_writing(state, monkeypatch):
    monkeypatch.setattr(dashboard, "save_stores", lambda *args: pytest.fail("draft must not be saved"))
    baseline = deepcopy(state.route_editor_baseline)
    state.template_selected_stores = ["В", "А"]
    assert call(state, "move_template_stores", 0, 1, ["В", "А"])
    assert state.route_stores == [["Б"], ["Г", "А", "В"], []]
    assert state.route_editor_baseline == baseline
    assert state.template_selected_stores == []
    assert computed(state, "template_dirty")
    assert sum(map(len, state.route_stores)) == 4


@pytest.mark.parametrize("source,target,names", [
    (0, 0, ["А"]), (-1, 1, ["А"]), (0, 3, ["А"]),
    (3, 1, ["А"]), (0, 1, []), (0, 1, ["А", "не существует"]),
])
def test_invalid_move_is_atomic(state, source, target, names):
    before = deepcopy(state.route_stores)
    assert not call(state, "move_template_stores", source, target, names)
    assert state.route_stores == before
    assert state.template_move_error


def test_conflicts_do_not_move_nonconflicting_stores(state):
    state.route_stores[1].append("Б")
    before = deepcopy(state.route_stores)
    assert not call(state, "move_template_stores", 0, 1, ["А", "Б"])
    assert state.route_stores == before
    assert "Б" in state.template_move_error


def test_repeated_drop_cannot_delete_target_store(state):
    payload = json.dumps({"source": 0, "name": "Б"})
    call(state, "drop_template_store", 1, payload)
    before = deepcopy(state.route_stores)
    call(state, "drop_template_store", 1, payload)
    assert state.route_stores == before
    assert state.route_stores[1] == ["Г", "Б"]


@pytest.mark.parametrize("payload", ['bad', '{}', '[]', 'null', '{"source":true,"name":"А"}'])
def test_malformed_drop_is_ignored(state, payload):
    before = deepcopy(state.route_stores)
    call(state, "drop_template_store", 1, payload)
    assert state.route_stores == before


def test_search_keeps_target_routes_and_hidden_selection(state):
    state.search_query = "Б"
    state.template_selected_stores = ["А"]
    assert [row["name"] for row in computed(state, "template_stores")] == ["Б"]
    assert len(computed(state, "template_routes")) == 3
    assert computed(state, "template_routes")[0]["count"] == 3
    assert computed(state, "template_routes")[0]["matches"] == 1
    call(state, "select_template_matches")
    assert state.template_selected_stores == ["А", "Б"]
    call(state, "open_template_move", "")
    state.template_move_target = "Маршрут №2"
    call(state, "confirm_template_move")
    assert state.route_stores == [["В"], ["Г", "А", "Б"], []]
    assert state.template_move_source == -1


def test_selection_resets_on_route_change_not_draft(state):
    state.template_selected_stores = ["А"]
    before = deepcopy(state.route_stores)
    call(state, "select_template_route", 1)
    assert state.selected_route_index == 1
    assert state.template_selected_stores == []
    assert state.route_stores == before


def test_move_dialog_requires_target_and_excludes_source(state):
    call(state, "open_template_move", "А")
    assert computed(state, "template_move_options") == ["Маршрут №2", "Маршрут №3"]
    call(state, "confirm_template_move")
    assert state.template_move_error
    assert state.route_stores[0] == ["А", "Б", "В"]


def test_discard_restores_baseline_without_writing(state, monkeypatch):
    monkeypatch.setattr(dashboard, "save_stores", lambda *args: pytest.fail("discard must not write"))
    call(state, "move_template_stores", 0, 2, ["А"])
    call(state, "discard_template_changes")
    assert state.route_stores == state.route_editor_baseline
    assert not computed(state, "template_dirty")


def test_drag_behavior():
    node = shutil.which("node")
    if not node:
        pytest.skip("Node.js is required for native drag behavior tests")
    result = subprocess.run(
        [node, "--test", str(Path(__file__).with_name("route_template_dnd_behavior.cjs"))],
        capture_output=True, text=True, encoding="utf8", timeout=30,
    )
    assert result.returncode == 0, result.stdout + result.stderr


def test_template_components_compile():
    component = dashboard._routes_editor()
    rendered = str(component)
    assert "route-template-routes" in rendered
    assert "onDrop" in rendered
    assert "dataTransfer.getData" in rendered
