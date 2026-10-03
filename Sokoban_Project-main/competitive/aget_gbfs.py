"""UCS Competitive Agent - Tìm kiếm chi phí đồng nhất."""
import time, heapq, itertools
from competitive.agent_base import run_turn, _DIRECTIONS, _inside

def ucs_search(state, agent_id, goal, mode, grid, deadline, recent_positions):
    agent_pos = state.a1 if agent_id == 1 else state.a2
    other_agent = state.a2 if agent_id == 1 else state.a1
    start = (agent_pos, state.boxes)
    
    serial = itertools.count()
    frontier = [(0, next(serial), start)]
    parents, actions_to = {start: None}, {}
    best_costs = {start: 0}

    while frontier and time.perf_counter() < deadline:
        g_cost, _, current = heapq.heappop(frontier)
        current_agent, current_boxes = current
        reached = goal not in current_boxes if mode == "dislodge" else goal in current_boxes
        
        if reached and current != start:
            while parents[current] != start:
                current = parents[current]
            return actions_to[current]

        for action, (dr, dc) in _DIRECTIONS:
            next_agent = (current_agent[0] + dr, current_agent[1] + dc)
            if not _inside(next_agent, grid) or next_agent == other_agent:
                continue

            next_boxes = current_boxes
            if next_agent in current_boxes:
                if next_agent in grid["goals"] and state.owners.get(next_agent, 0) == agent_id:
                    continue
                pushed_box = (next_agent[0] + dr, next_agent[1] + dc)
                if not _inside(pushed_box, grid) or pushed_box in current_boxes or pushed_box == other_agent:
                    continue
                next_boxes = frozenset((current_boxes - {next_agent}) | {pushed_box})

            child = (next_agent, next_boxes)
            step_cost = 1 + 50 * recent_positions.count(next_agent)
            new_cost = g_cost + step_cost
            
            if child not in best_costs or new_cost < best_costs[child]:
                best_costs[child] = new_cost
                parents[child] = current
                actions_to[child] = action
                heapq.heappush(frontier, (new_cost, next(serial), child))
    return None

def get_action(agent_id, state, grid, time_limit=0.95):
    return run_turn(agent_id, state, grid, time_limit, ucs_search)