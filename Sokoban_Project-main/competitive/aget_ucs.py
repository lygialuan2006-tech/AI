"""GBFS Competitive Agent - Tự cài đặt Heuristic riêng."""
import time, heapq, itertools
from collections import deque
from competitive.agent_base import run_turn, _DIRECTIONS, _inside

def gbfs_heuristic(agent_pos, boxes, goal, mode, other_agent, grid) -> int:
    """Heuristic riêng của GBFS: Đo khoảng cách BFS né tường từ agent tới mục tiêu."""
    if mode == "dislodge":
        # Ước lượng khoảng cách đến ô kề bên để đẩy hộp ra khỏi goal
        return abs(agent_pos[0] - goal[0]) + abs(agent_pos[1] - goal[1])

    # Khoảng cách từ hộp gần nhất tới goal + khoảng cách từ agent tới hộp đó
    min_dist = 10**6
    for b in boxes:
        dist_box_goal = abs(b[0] - goal[0]) + abs(b[1] - goal[1])
        dist_agent_box = abs(agent_pos[0] - b[0]) + abs(agent_pos[1] - b[1])
        total = dist_box_goal + dist_agent_box
        if total < min_dist:
            min_dist = total
    return min_dist

def gbfs_search(state, agent_id, goal, mode, grid, deadline, recent_positions):
    agent_pos = state.a1 if agent_id == 1 else state.a2
    other_agent = state.a2 if agent_id == 1 else state.a1
    start = (agent_pos, state.boxes)
    
    serial = itertools.count()
    start_h = gbfs_heuristic(agent_pos, state.boxes, goal, mode, other_agent, grid)
    frontier = [(start_h, next(serial), start)]
    parents, actions_to = {start: None}, {}
    explored = set()

    while frontier and time.perf_counter() < deadline:
        _, _, current = heapq.heappop(frontier)
        if current in explored:
            continue
        explored.add(current)
        
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
            if child not in parents:
                parents[child] = current
                actions_to[child] = action
                h_val = gbfs_heuristic(next_agent, next_boxes, goal, mode, other_agent, grid)
                h_val += 50 * recent_positions.count(next_agent)
                heapq.heappush(frontier, (h_val, next(serial), child))
    return None

def get_action(agent_id, state, grid, time_limit=0.95):
    return run_turn(agent_id, state, grid, time_limit, gbfs_search)