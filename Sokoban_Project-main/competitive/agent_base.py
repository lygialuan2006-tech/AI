"""Base module for competitive agents. Handles timing, memory, and fallback."""

import time
from collections import deque
from core.competitive_state import ACTIONS, Position
from competitive.controller_memory import update_agent_memory, _MEMORY

_DIRECTIONS = tuple((name, delta) for name, delta in ACTIONS.items() if name != "Wait")

def _inside(position: Position, grid: dict) -> bool:
    return (
        0 <= position[0] < grid["height"]
        and 0 <= position[1] < grid["width"]
        and position not in grid["walls"]
    )

def _target_options(state, grid: dict, agent_id: int, deadline: float, cooled_goals: set[Position]):
    goals = sorted(grid["goals"])
    other_id = 2 if agent_id == 1 else 1
    other_agent = state.a2 if agent_id == 1 else state.a1
    options = []
    
    for goal in goals:
        if time.perf_counter() >= deadline:
            break
        if goal in cooled_goals:
            continue
        owner = state.owners.get(goal, 0)
        if owner == agent_id:
            continue
            
        mode = "dislodge" if goal in state.boxes else "place"
        priority = (0 if owner == other_id else 1) if mode == "dislodge" else (2 if owner == other_id else 3)
        
        # [FIX 3]: Đo khoảng cách đối thủ tới mục tiêu (Manhattan).
        dist_opponent = abs(other_agent[0] - goal[0]) + abs(other_agent[1] - goal[1])
        # Nếu đối thủ đứng ngay cạnh mục tiêu (<= 2 ô), giảm độ ưu tiên (Cộng thêm 10 vào priority)
        if dist_opponent <= 2:
            priority += 10
            
        options.append((priority, goal, mode))
        
    return sorted(options)

def _safe_fallback(agent_pos, other_agent, boxes, grid, agent_id, state, recent_positions):
    """Nước đi an toàn dự phòng khi hết giờ hoặc không tìm thấy đường."""
    goals, owners, opponent_id = grid["goals"], state.owners, 2 if agent_id == 1 else 1
    directions = list(_DIRECTIONS)
    
    rotation = (state.t * agent_id * 7) % len(directions)
    directions = directions[rotation:] + directions[:rotation]
    choices = []

    for order, (action, (dr, dc)) in enumerate(directions):
        dest = (agent_pos[0] + dr, agent_pos[1] + dc)
        if not _inside(dest, grid) or dest == other_agent:
            continue
        
        if dest in boxes:
            if dest in goals and owners.get(dest, 0) == agent_id:
                continue  # Luật cũ: Không tự đẩy hộp trên đích của mình
            box_dest = (dest[0] + dr, dest[1] + dc)
            if not _inside(box_dest, grid) or box_dest in boxes or box_dest == other_agent:
                continue
            priority = 0 if (dest in goals and owners.get(dest, 0) not in (0, agent_id)) else (1 if (box_dest in goals and owners.get(box_dest, 0) != agent_id) else 3)
        else:
            priority = 2
            
        penalty = recent_positions.count(dest) * 10
        choices.append((priority + penalty, order, action))

    if choices:
        return min(choices)[2]

    # [BẢN VÁ 1] ĐƯỜNG CÙNG MỞ LỐI (LAST RESORT)
    # Nếu choices rỗng (như Agent Cam: bị vây bởi tường, đối thủ và hộp nhà mình)
    # Agent bắt buộc phải chấp nhận hi sinh điểm, phá hộp của mình để lấy đường sống
    for action, (dr, dc) in _DIRECTIONS:
        dest = (agent_pos[0] + dr, agent_pos[1] + dc)
        if _inside(dest, grid) and dest != other_agent:
            if dest in boxes:
                box_dest = (dest[0] + dr, dest[1] + dc)
                if _inside(box_dest, grid) and box_dest not in boxes and box_dest != other_agent:
                    return action
            else:
                return action
                
    return "Wait"

def run_turn(agent_id, state, grid, time_limit, search_func) -> str:
    """Điều phối lượt chơi, đo deadline và gọi hàm search của từng agent."""
    start_time = time.perf_counter()
    deadline = start_time + max(0.0, min(float(time_limit), 0.95))
    agent_pos = state.a1 if agent_id == 1 else state.a2
    other_agent = state.a2 if agent_id == 1 else state.a1
    
    recent_positions, cooled_goals = update_agent_memory(agent_id, state, grid)
    
    # [BẢN VÁ 2] NHƯỜNG ĐƯỜNG BẤT ĐỐI XỨNG (ASYMMETRIC YIELDING)
    # Nếu Agent liên tục không thể nhích đi đâu được do bị Cancel lệnh (Body Clash)
    if recent_positions.count(agent_pos) >= 2:
        # Dùng phép chia dư lẻ để ép: 1 con bắt buộc đứng im, nhường con kia đi
        if (state.t + agent_id) % 2 == 0:
            print(f"[YIELD] Turn {state.t}: Agent {agent_id} chủ động nhường đường.")
            return "Wait"

    fallback = _safe_fallback(agent_pos, other_agent, state.boxes, grid, agent_id, state, recent_positions)

    for _, goal, mode in _target_options(state, grid, agent_id, deadline, cooled_goals):
        if time.perf_counter() >= deadline:
            break
            
        action = search_func(state, agent_id, goal, mode, grid, deadline, recent_positions)
        
        if action is not None:
            dr, dc = dict(_DIRECTIONS)[action]
            next_pos = (agent_pos[0] + dr, agent_pos[1] + dc)
            if recent_positions.count(next_pos) >= 3:
                # [BẢN VÁ 3] NÂNG MỨC PHẠT SỔ ĐEN
                if agent_id in _MEMORY:
                    _MEMORY[agent_id]["goal_cooldowns"][goal] = state.t + 8
                return fallback
            return action
        else:
            if agent_id in _MEMORY:
                # Blacklist các mục tiêu vô vọng dài hạn hơn để giải phóng sức mạnh CPU
                _MEMORY[agent_id]["goal_cooldowns"][goal] = state.t + 5

    return fallback