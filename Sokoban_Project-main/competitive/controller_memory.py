from __future__ import annotations

from collections import deque

_MEMORY: dict[int, dict] = {}


def update_agent_memory(agent_id: int, state, grid: dict):
    """Track recent positions and cool down goals an agent just vacated."""
    map_key = (
        grid["height"],
        grid["width"],
        frozenset(grid["walls"]),
        frozenset(grid["goals"]),
    )
    memory = _MEMORY.get(agent_id)
    if (
        memory is None
        or memory["map_key"] != map_key
        or state.t < memory["last_turn"]
        or state.t == 0
    ):
        memory = {
            "map_key": map_key,
            "last_turn": -1,
            "recent_positions": deque(maxlen=8),
            "goal_cooldowns": {},
            "previous_boxes": frozenset(),
            "previous_owners": {},
        }
        _MEMORY[agent_id] = memory

    previous_boxes = memory["previous_boxes"]
    removed_goal_boxes = (previous_boxes & grid["goals"]) - state.boxes
    added_boxes = state.boxes - previous_boxes
    for goal in removed_goal_boxes:
        for new_box in added_boxes:
            if (
                abs(new_box[0] - goal[0]) + abs(new_box[1] - goal[1]) == 1
                and state.box_owners.get(new_box) == agent_id
            ):
                memory["goal_cooldowns"][goal] = state.t + 8

    for goal in grid["goals"]:
        if (
            memory["previous_owners"].get(goal) == agent_id
            and state.owners.get(goal, 0) == 0
            and goal not in state.boxes
        ):
            memory["goal_cooldowns"][goal] = state.t + 8

    memory["last_turn"] = state.t
    memory["previous_boxes"] = state.boxes
    memory["previous_owners"] = dict(state.owners)
    agent_position = state.a1 if agent_id == 1 else state.a2
    memory["recent_positions"].append(agent_position)

    active_cooldowns = {
        goal for goal, until_turn in memory["goal_cooldowns"].items()
        if state.t < until_turn
    }
    return tuple(memory["recent_positions"]), active_cooldowns