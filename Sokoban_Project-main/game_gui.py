import argparse
import sys
import importlib.util
from concurrent.futures import Future, ThreadPoolExecutor
from pathlib import Path
import pygame

from core.map_loader import load_map
from core.state import get_successors
from core.competitive_state import CompetitiveGameState
from search.astar import a_star_search
from search.ucs import uniform_cost_search

# Kích hoạt chế độ nét cao (High-DPI) trên Windows
if sys.platform == "win32":
    try:
        import ctypes
        ctypes.windll.shcore.SetProcessDpiAwareness(1)
    except Exception:
        pass

ROOT = Path(__file__).resolve().parent
ALGORITHMS = {"UCS": uniform_cost_search, "A*": a_star_search}

COLORS = {
    "background": (20, 26, 30),
    "background_alt": (28, 37, 42),
    "panel": (244, 242, 232),
    "floor": (220, 211, 184),
    "floor_line": (203, 192, 163),
    "wall": (59, 75, 70),
    "wall_edge": (42, 55, 52),
    "goal": (212, 91, 73),
    "box": (194, 132, 62),
    "box_edge": (112, 70, 35),
    "agent": (49, 133, 174),
    "agent2": (198, 91, 103),
    "text": (37, 46, 43),
    "muted": (116, 126, 120),
    "accent": (135, 204, 147),
    "accent_dark": (56, 115, 78),
    "button": (230, 231, 220),
    "white": (250, 250, 244),
    "line": (77, 94, 91),
}

def lerp(start: float, end: float, t: float) -> float:
    return start + (end - start) * t

class SokobanGame:
    def __init__(self, map_path: Path):
        pygame.init()
        pygame.display.set_caption("Sokoban AI Arena")
        display = pygame.display.Info()
        desktop_width = display.current_w or 1280
        desktop_height = display.current_h or 800
        window_width = min(1920, max(min(900, desktop_width), int(desktop_width * 0.96)))
        window_height = min(1200, max(min(640, desktop_height), int(desktop_height * 0.92)))
        self.screen = pygame.display.set_mode((window_width, window_height), pygame.RESIZABLE | pygame.DOUBLEBUF)
        self.clock = pygame.time.Clock()
        
        self.font = pygame.font.SysFont("Segoe UI", 18, bold=True)
        self.small_font = pygame.font.SysFont("Segoe UI", 14)
        self.label_font = pygame.font.SysFont("Segoe UI", 16, bold=True)
        self.title_font = pygame.font.SysFont("Segoe UI", 64, bold=True)
        self.heading_font = pygame.font.SysFont("Segoe UI", 28, bold=True)
        
        self.map_path = map_path
        self.grid, self.initial_state = load_map(str(map_path))
        self.assets_path = ROOT / "assets"
        self.assets = self._load_assets()
        
        self.scaled_assets_cache = {}
        self.text_cache = {}
        
        self.page = "menu"
        self.mode = "single"
        self.algorithm = "A*"
        
        # Biến nạp file AI
        self.p1_file = None
        self.p2_file = None
        self.p1_func = None
        self.p2_func = None
        
        # Tọa độ Spawn thủ công cho 2 Agent
        self.user_spawns = [None, None]
        self.spawn_pick_agent = 1
        
        self.board_layout = None
        self.turn_limit_text = "30"
        self.turn_limit_active = False
        self.sidebar_open = True
        self.buttons = {}
        self.message = "Choose a mode to begin."
        
        # ThreadPool đảm bảo tính toán AI không làm đứng hình/giật lag giao diện
        self._controller_pool = ThreadPoolExecutor(max_workers=2, thread_name_prefix="sokoban-ai")
        self._pending_controller_futures: tuple[Future, Future] | None = None
        self._pending_turn_state = None
        
        self.anim_t = 1.0
        self.anim_speed = 6.0  
        self.prev_state = self.initial_state
        
        self._reset_run()

    def _load_assets(self):
        names = ("wall", "floor", "goal", "box", "box_agent1", "box_agent2", "agent", "agent2")
        images = {}
        for name in names:
            path = self.assets_path / f"{name}.png"
            if path.is_file():
                try:
                    images[name] = pygame.image.load(str(path)).convert_alpha()
                except pygame.error as error:
                    print(f"Lỗi nạp ảnh {path}: {error}")
        return images

    def _reset_run(self):
        if self._pending_controller_futures:
            for future in self._pending_controller_futures:
                future.cancel()
        self._pending_controller_futures = None
        self._pending_turn_state = None
        
        self.states = [self.initial_state]
        self.actions = []
        self.owner_timeline = [dict(getattr(self.initial_state, "box_owners", {}))]
        self.action_index = 0
        self.total_cost = None
        self.visited = None
        self.playing = False
        self.playback_elapsed = 0
        self.prev_state = self.initial_state
        self.anim_t = 1.0
        
        if self.mode == "two":
            self.message = "Chế độ Đối kháng: Nạp AI và đặt Agent lên lưới."

    def _load_agent_file(self, player_id):
        """Nạp file .py qua hộp thoại Tkinter."""
        try:
            import tkinter as tk
            from tkinter import filedialog
            
            root = tk.Tk()
            root.withdraw()
            root.wm_attributes('-topmost', 1) 
            root.update()
            
            selected = filedialog.askopenfilename(
                parent=root,
                title=f"Chọn file thuật toán (.py) cho Agent {player_id}",
                filetypes=(("Python files", "*.py"), ("All files", "*.*")),
            )
            
            root.update()
            root.destroy()
            
            if not selected:
                return
                
            filepath = Path(selected)
            module_name = f"dynamic_agent_{player_id}"
            
            spec = importlib.util.spec_from_file_location(module_name, filepath)
            module = importlib.util.module_from_spec(spec)
            sys.modules[module_name] = module
            spec.loader.exec_module(module)
            
            if not hasattr(module, "get_action"):
                self.message = f"Lỗi: File '{filepath.name}' không chứa hàm 'get_action'!"
                return

            if player_id == 1:
                self.p1_file = filepath.name
                self.p1_func = module.get_action
            else:
                self.p2_file = filepath.name
                self.p2_func = module.get_action
                
            self.message = f"Đã nạp thành công '{filepath.name}' cho P{player_id}."
            
        except Exception as e:
            self.message = f"Lỗi nạp file AI: {e}"

    def _select_spawn_at(self, point):
        """Click trên lưới để đổi vị trí Agent."""
        if self.page != "game" or self.mode != "two" or self.board_layout is None:
            return
        
        if isinstance(self.states[-1], CompetitiveGameState):
            self.message = "Trận đấu đang diễn ra. Bấm 'Reset Match' để xếp lại map."
            return
            
        origin_x, origin_y, tile, rows, columns = self.board_layout
        column = (point[0] - origin_x) // tile
        row = (point[1] - origin_y) // tile
        if not (0 <= row < rows and 0 <= column < columns):
            return
            
        pos = (row, column)
        other_index = 1 if self.spawn_pick_agent == 1 else 0
        current_index = self.spawn_pick_agent - 1
        
        # Nếu click lại đúng chỗ mình đang đứng -> xóa đi
        if self.user_spawns[current_index] == pos:
            self.user_spawns[current_index] = None
            self.message = f"Đã gỡ bỏ vị trí của P{self.spawn_pick_agent}."
            return
            
        if pos in self.grid["walls"] or pos in self.initial_state.boxes:
            self.message = "Vị trí không hợp lệ! Vui lòng chọn ô trống."
            return
            
        if pos == self.user_spawns[other_index]:
            self.message = "Vị trí đã bị đối thủ chiếm!"
            return
            
        self.user_spawns[current_index] = pos
        self.message = f"Đã đặt P{self.spawn_pick_agent} tại {pos}."

    def _turn_limit(self):
        try:
            return max(1, min(10000, int(self.turn_limit_text)))
        except ValueError:
            return 30

    def _start_competitive_match(self):
        """Kiểm tra điều kiện và khởi tạo CompetitiveGameState."""
        if not self.p1_func or not self.p2_func:
            self.playing = False
            self.message = "Lỗi: Cần nạp đủ file AI cho cả 2 Agent."
            return
            
        if not all(self.user_spawns):
            self.playing = False
            self.message = "Lỗi: Vui lòng click vào map để chọn vị trí cho cả 2 Agent."
            return
            
        try:
            boxes = self.initial_state.boxes
            owners = {goal: 0 for goal in self.grid["goals"]}
            comp_state = CompetitiveGameState(self.user_spawns[0], self.user_spawns[1], boxes, owners=owners)
            
            self.states = [comp_state]
            self.actions = []
            self.owner_timeline = [dict(comp_state.box_owners)]
            self.action_index = 0
            self.prev_state = comp_state
            self.anim_t = 1.0
            
            self.playing = True
            self.message = f"Trận đấu bắt đầu! Giới hạn {self._turn_limit()} lượt."
        except ValueError as e:
            self.playing = False
            self.message = f"Lỗi khởi tạo State: {e}"

    def _advance_competitive_turn(self):
        """Ném tác vụ cho ThreadPool tính toán để GUI không bị treo."""
        if self._pending_controller_futures:
            return
        current = self.states[-1]
        if current.t >= self._turn_limit():
            self.playing = False
            return

        self._pending_turn_state = current
        self._pending_controller_futures = (
            self._controller_pool.submit(self.p1_func, 1, current, self.grid, time_limit=0.95),
            self._controller_pool.submit(self.p2_func, 2, current, self.grid, time_limit=0.95),
        )
        self.message = f"Turn {current.t + 1}: Agents đang tính toán..."

    def _collect_competitive_turn(self):
        """Thu gom kết quả khi các Thread đã chạy xong."""
        futures = self._pending_controller_futures
        if not futures or not all(future.done() for future in futures):
            return

        current = self._pending_turn_state
        self._pending_controller_futures = None
        self._pending_turn_state = None
        
        try:
            action1 = futures[0].result()
        except Exception as e:
            print(f"[ERROR] P1 Crash: {e}")
            action1 = "Wait"
            
        try:
            action2 = futures[1].result()
        except Exception as e:
            print(f"[ERROR] P2 Crash: {e}")
            action2 = "Wait"
            
        if current is not self.states[-1]:
            return

        next_state = current.apply_joint_action(action1, action2, self.grid)
        self.prev_state = current
        self.states.append(next_state)
        self.actions.append(next_state.last_actions)
        self.owner_timeline.append(dict(next_state.box_owners))
        self.action_index = len(self.actions)
        self.anim_t = 0.0

        if next_state.t >= self._turn_limit():
            self.playing = False
            score1, score2 = next_state.score(1), next_state.score(2)
            if score1 == score2:
                result = f"Hòa {score1}-{score2}."
            else:
                winner = 1 if score1 > score2 else 2
                result = f"P{winner} chiến thắng: {score1}-{score2}."
            self.message = f"Kết thúc trận! {result}"
        else:
            self.message = f"Turn {next_state.t}: P1 {next_state.last_actions[0]} | P2 {next_state.last_actions[1]}"

    def _text(self, text, position, color=None, font=None):
        font_obj = font or self.font
        color_val = color or COLORS["text"]
        text_str = str(text)
        cache_key = (text_str, color_val, font_obj)
        if cache_key not in self.text_cache:
            self.text_cache[cache_key] = font_obj.render(text_str, True, color_val)
        surface = self.text_cache[cache_key]
        self.screen.blit(surface, position)
        return surface.get_rect(topleft=position)

    def _button(self, name, label, rect, active=False, small=False, is_file_btn=False, danger=False):
        if danger:
            fill = (168, 62, 62) if active else (138, 42, 42)
            ink = COLORS["white"]
        else:
            fill = COLORS["accent_dark"] if active else COLORS["button"]
            if is_file_btn and active:
                fill = (70, 130, 95)
            ink = COLORS["white"] if active else COLORS["text"]
            
        pygame.draw.rect(self.screen, fill, rect, border_radius=8)
        pygame.draw.rect(self.screen, (255, 255, 255, 40), rect, 1, border_radius=8)
        
        font_obj = self.small_font if small else self.label_font
        cache_key = (label, ink, font_obj)
        if cache_key not in self.text_cache:
            self.text_cache[cache_key] = font_obj.render(label, True, ink)
        surface = self.text_cache[cache_key]
        self.screen.blit(surface, surface.get_rect(center=rect.center))
        self.buttons[name] = rect

    def _asset(self, name, rect):
        image = self.assets.get(name)
        if image is None:
            return False
        cache_key = (name, rect.size)
        if cache_key not in self.scaled_assets_cache:
            self.scaled_assets_cache[cache_key] = pygame.transform.smoothscale(image, rect.size)
        self.screen.blit(self.scaled_assets_cache[cache_key], rect)
        return True

    def _draw_board(self, area):
        rows = self.grid["height"]
        columns = self.grid["width"]
        tile = max(1, min(160, area.width // max(1, columns), area.height // max(1, rows)))
        board_width, board_height = columns * tile, rows * tile
        origin_x = area.x + (area.width - board_width) // 2
        origin_y = area.y + (area.height - board_height) // 2
        self.board_layout = (origin_x, origin_y, tile, rows, columns)
        board_rect = pygame.Rect(origin_x, origin_y, board_width, board_height)

        curr_state = self.states[self.action_index]
        prev_state = self.prev_state
        t = min(1.0, self.anim_t)

        for r in range(rows):
            for c in range(columns):
                pos = (r, c)
                rect = pygame.Rect(origin_x + c * tile, origin_y + r * tile, tile, tile)
                if pos in self.grid["walls"]:
                    if not self._asset("wall", rect):
                        pygame.draw.rect(self.screen, COLORS["wall"], rect)
                        pygame.draw.rect(self.screen, COLORS["wall_edge"], rect, 2)
                    continue

                if not self._asset("floor", rect):
                    pygame.draw.rect(self.screen, COLORS["floor"], rect)
                    pygame.draw.rect(self.screen, COLORS["floor_line"], rect, 1)

                if pos in self.grid["goals"]:
                    goal_rect = rect.inflate(-tile // 3, -tile // 3)
                    if not self._asset("goal", goal_rect):
                        pygame.draw.circle(self.screen, COLORS["goal"], rect.center, max(4, tile // 6))

        curr_boxes = list(curr_state.boxes)
        prev_boxes = list(prev_state.boxes)
        
        interpolated_boxes = []
        unpaired_curr = curr_boxes.copy()
        for pb in prev_boxes:
            best_match = min(unpaired_curr, key=lambda cb: abs(cb[0]-pb[0]) + abs(cb[1]-pb[1]))
            if abs(best_match[0]-pb[0]) + abs(best_match[1]-pb[1]) <= 1:
                interpolated_boxes.append((pb, best_match))
                unpaired_curr.remove(best_match)
            else:
                interpolated_boxes.append((pb, pb))

        owners = self.owner_timeline[self.action_index]
        for p_box, c_box in interpolated_boxes:
            interp_r = lerp(p_box[0], c_box[0], t)
            interp_c = lerp(p_box[1], c_box[1], t)
            
            box_x = origin_x + interp_c * tile + tile // 16
            box_y = origin_y + interp_r * tile + tile // 16
            box_size = tile - tile // 8
            box_rect = pygame.Rect(int(box_x), int(box_y), int(box_size), int(box_size))
            
            owner = owners.get(c_box, 0)
            sprite = f"box_agent{owner}" if owner in (1, 2) else "box"
            if not self._asset(sprite, box_rect) and not self._asset("box", box_rect):
                fill = COLORS["agent"] if owner == 1 else COLORS["agent2"] if owner == 2 else COLORS["box"]
                pygame.draw.rect(self.screen, fill, box_rect, border_radius=6)
                pygame.draw.rect(self.screen, COLORS["box_edge"], box_rect, 2, border_radius=6)

        # Vẽ Sprite Agent (Nếu pos là None thì bỏ qua -> Map trống)
        if self.mode == "two":
            if isinstance(curr_state, CompetitiveGameState):
                previous_agents = (prev_state.a1, prev_state.a2)
                current_agents = (curr_state.a1, curr_state.a2)
            else:
                previous_agents = tuple(self.user_spawns)
                current_agents = tuple(self.user_spawns)
                
            agent_pairs = tuple(
                (previous, current, asset_name, color)
                for previous, current, asset_name, color in zip(
                    previous_agents, current_agents,
                    ("agent", "agent2"), (COLORS["agent"], COLORS["agent2"]),
                )
            )
        else:
            agent_pairs = ((prev_state.agent_pos, curr_state.agent_pos, "agent", COLORS["agent"]),)
            
        for previous_agent, current_agent, asset_name, color in agent_pairs:
            if previous_agent is None or current_agent is None:
                continue
                
            agent_r = lerp(previous_agent[0], current_agent[0], t)
            agent_c = lerp(previous_agent[1], current_agent[1], t)
            inset = max(3, tile // 8)
            ag_size = tile - 2 * inset
            ag_x = origin_x + agent_c * tile + inset
            ag_y = origin_y + agent_r * tile + inset
            agent_rect = pygame.Rect(int(ag_x), int(ag_y), int(ag_size), int(ag_size))
            
            if not self._asset(asset_name, agent_rect):
                pygame.draw.circle(self.screen, color, agent_rect.center, tile // 3)
                pygame.draw.circle(self.screen, COLORS["white"], agent_rect.center, tile // 3, 2)

        return board_rect

    def _draw_menu(self):
        self.buttons.clear()
        self.screen.fill(COLORS["background"])
        width, height = self.screen.get_size()
        
        left = max(48, width // 11)
        self._text("Introduction to AI Midterm Project", (left, 76), COLORS["accent"], self.small_font)
        self._text("SOKOBAN", (left - 4, 100), COLORS["white"], self.title_font)
        self._text("Academic Search Engine Demo", (left + 2, 175), (190, 201, 192), self.font)
        self._text(">> SELECT MODE <<", (left + 2, 250), COLORS["accent"], self.small_font)

        card_y = 280
        card_width = min(250, max(190, (width - 3 * left) // 2))
        card_height = 138
        gap = 18

        for index, (mode, title, note) in enumerate((
            ("single", "ONE AGENT", "Req 1 - 4 (A* & UCS)"),
            ("two", "TWO AGENTS", "Req 6 - 8 (Multi-Agent)"),
        )):
            card = pygame.Rect(left + index * (card_width + gap), card_y, card_width, card_height)
            selected = self.mode == mode
            pygame.draw.rect(self.screen, COLORS["background_alt"], card, border_radius=10)
            pygame.draw.rect(self.screen, COLORS["accent"] if selected else COLORS["line"], card, 2 if selected else 1, border_radius=10)
            self._text(f"0{index + 1}", (card.x + 17, card.y + 15), COLORS["accent"], self.small_font)
            self._text(title, (card.x + 17, card.y + 49), COLORS["white"], self.label_font)
            self._text(note, (card.x + 17, card.y + 82), (177, 188, 180), self.small_font)
            self.buttons[f"mode_{mode}"] = card

        play_width = card_width * 2 + gap
        self._button("start", "START GAME UI", pygame.Rect(left, card_y + card_height + 24, play_width, 54), active=True)
        self._button("menu_map", "Choose map", pygame.Rect(left, card_y + card_height + 90, card_width, 40), small=True)
        self._text(f"MAP: {self.map_path.name}", (left, card_y + card_height + 145), (177, 188, 180), self.small_font)

        preview_width = min(420, max(280, width // 3))
        preview = pygame.Rect(width - preview_width - max(48, width // 12), 170, preview_width, min(420, height - 240))
        pygame.draw.rect(self.screen, (25, 33, 38), preview.inflate(20, 20), border_radius=12)
        self._draw_board(preview)

    def _draw_sidebar(self, panel):
        pygame.draw.rect(self.screen, COLORS["panel"], panel)
        pygame.draw.line(self.screen, (218, 221, 209), panel.topleft, (panel.left, panel.bottom), 1)
        x = panel.x + 20
        inner_width = panel.width - 40
        
        self._text("CONTROL PANEL", (x, panel.y + 18), COLORS["accent_dark"], self.small_font)
        self._text("Solver Setup", (x, panel.y + 40), COLORS["text"], self.heading_font)
        self._button("sidebar_close", "<", pygame.Rect(panel.right - 40, panel.y + 16, 26, 26), small=True)

        compact = panel.height < 700
        mode_y = panel.y + (68 if compact else 86)
        self._text("MODE", (x, mode_y), COLORS["muted"], self.small_font)
        option_width = (inner_width - 8) // 2
        self._button("mode_single", "Single", pygame.Rect(x, mode_y + 22, option_width, 34), active=self.mode == "single", small=True)
        self._button("mode_two", "Two-Agent", pygame.Rect(x + option_width + 8, mode_y + 22, option_width, 34), active=self.mode == "two", small=True)

        map_y = mode_y + (62 if compact else 70)
        self._text("MAP FILE", (x, map_y), COLORS["muted"], self.small_font)
        self._text(self.map_path.name, (x, map_y + 20), COLORS["text"], self.small_font)
        self._button("change_map", "Change Map...", pygame.Rect(x, map_y + 44, inner_width, 32), small=True)

        algo_y = map_y + (82 if compact else 90)
        
        if self.mode == "single":
            self._text("ALGORITHM", (x, algo_y), COLORS["muted"], self.small_font)
            self._button("algo_ucs", "UCS", pygame.Rect(x, algo_y + 22, option_width, 34), active=self.algorithm == "UCS", small=True)
            self._button("algo_astar", "A* (Hungarian)", pygame.Rect(x + option_width + 8, algo_y + 22, option_width, 34), active=self.algorithm == "A*", small=True)
            self._button("solve", "Solve Puzzle", pygame.Rect(x, algo_y + 64, inner_width, 38), active=True, small=True)
            stats_y = algo_y + (110 if compact else 118)
        else:
            self._text("AI MODULES (Click to load)", (x, algo_y), COLORS["muted"], self.small_font)
            spawn_button_y = algo_y + 22
            
            p1_label = (self.p1_file[:13] + "...") if self.p1_file and len(self.p1_file) > 16 else (self.p1_file or "Load P1...")
            p2_label = (self.p2_file[:13] + "...") if self.p2_file and len(self.p2_file) > 16 else (self.p2_file or "Load P2...")
            
            self._button("load_p1", p1_label, pygame.Rect(x, spawn_button_y, option_width, 32), active=self.p1_func is not None, small=True, is_file_btn=True)
            self._button("load_p2", p2_label, pygame.Rect(x + option_width + 8, spawn_button_y, option_width, 32), active=self.p2_func is not None, small=True, is_file_btn=True)
            
            self._text("SPAWN SETUP (Click board)", (x, algo_y + 64), COLORS["muted"], self.small_font)
            self._button("clear_spawns", "Clear Spawns", pygame.Rect(x + inner_width - 80, algo_y + 60, 80, 24), active=False, small=True)
            
            p1_pos_str = f"P1: {self.user_spawns[0] or '... '}"
            p2_pos_str = f"P2: {self.user_spawns[1] or '... '}"
            
            self._button("spawn_pick_1", p1_pos_str, pygame.Rect(x, algo_y + 88, option_width, 28), active=self.spawn_pick_agent == 1, small=True)
            self._button("spawn_pick_2", p2_pos_str, pygame.Rect(x + option_width + 8, algo_y + 88, option_width, 28), active=self.spawn_pick_agent == 2, small=True)
            
            self._text("TURN LIMIT n", (x, algo_y + 128), COLORS["muted"], self.small_font)
            turn_rect = pygame.Rect(x, algo_y + 148, inner_width, 26)
            pygame.draw.rect(self.screen, COLORS["white"], turn_rect, border_radius=5)
            pygame.draw.rect(self.screen, COLORS["accent_dark"] if self.turn_limit_active else (190, 195, 185), turn_rect, 1, border_radius=5)
            self._text(self.turn_limit_text or "1", (turn_rect.x + 10, turn_rect.y + 4), COLORS["text"], self.small_font)
            self.buttons["turn_limit_input"] = turn_rect
            
            # --- NÚT START VÀ RESET TÁCH BIỆT ---
            self._button("start_match", "Start Match", pygame.Rect(x, algo_y + 184, option_width, 34), active=True, small=True)
            self._button("reset_match", "Reset Match", pygame.Rect(x + option_width + 8, algo_y + 184, option_width, 34), active=False, small=True, danger=True)
            stats_y = algo_y + 228

        pygame.draw.line(self.screen, (218, 221, 209), (x, stats_y), (x + inner_width, stats_y), 1)
        self._text("METRICS", (x, stats_y + 10), COLORS["muted"], self.small_font)
        
        if self.mode == "two":
            current = self.states[self.action_index]
            if isinstance(current, CompetitiveGameState):
                turn_label = f"Turn: {current.t} / {self._turn_limit()}"
                score1, score2 = current.score(1), current.score(2)
            else:
                turn_label = f"Setup / {self._turn_limit()} turns"
                score1 = score2 = 0
            self._text(turn_label, (x, stats_y + 32), COLORS["text"], self.small_font)
            self._text(f"Agent 1 score: {score1}", (x, stats_y + 54), COLORS["agent"], self.small_font)
            self._text(f"Agent 2 score: {score2}", (x, stats_y + 76), COLORS["agent2"], self.small_font)
        else:
            self._text(f"Action Step:    {self.action_index} / {len(self.actions)}", (x, stats_y + 32), COLORS["text"], self.small_font)
            cost_str = "-" if self.total_cost is None else str(self.total_cost)
            self._text(f"Path Cost:      {cost_str}", (x, stats_y + 54), COLORS["text"], self.small_font)
            visited_str = "-" if self.visited is None else f"{self.visited:,}"
            self._text(f"Explored Nodes: {visited_str}", (x, stats_y + 76), COLORS["text"], self.small_font)

        controls_y = panel.bottom - (100 if compact else 110)
        play_label = "Pause" if self.playing else ("Resume" if self.mode == "two" and isinstance(self.states[-1], CompetitiveGameState) else "Auto Play")
        self._button("play_pause", play_label, pygame.Rect(x, controls_y, inner_width, 36), active=self.playing, small=True)
        half = (inner_width - 8) // 2
        self._button("step_back", "Previous", pygame.Rect(x, controls_y + 42, half, 32), small=True)
        self._button("step_forward", "Next", pygame.Rect(x + half + 8, controls_y + 42, half, 32), small=True)
        self._text("SPACE: Pause | LEFT/RIGHT: Step", (x, panel.bottom - 20), COLORS["muted"], self.small_font)

    def _draw_game(self):
        self.buttons.clear()
        self.screen.fill(COLORS["background"])
        width, height = self.screen.get_size()

        header = pygame.Rect(0, 0, width, 58)
        pygame.draw.rect(self.screen, COLORS["background_alt"], header)
        pygame.draw.line(self.screen, COLORS["line"], (0, header.bottom), (width, header.bottom), 1)

        self._button("home", "MENU", pygame.Rect(18, 12, 64, 34), small=True)
        self._text("SOKOBAN AI", (96, 17), COLORS["white"], self.label_font)
        self._text(f"FPS: {int(self.clock.get_fps())}", (220, 20), COLORS["accent"], self.small_font)
        self._text(f"Map: {self.map_path.name}", (width - 320, 20), (196, 205, 197), self.small_font)
        
        if self.mode == "two":
            current = self.states[self.action_index]
            step_label = (f"Turn: {current.t}/{self._turn_limit()}" if isinstance(current, CompetitiveGameState) else "Setup Phase")
        else:
            step_label = f"Step: {self.action_index}/{len(self.actions)}"
        self._text(step_label, (width - 180, 20), COLORS["white"], self.small_font)

        panel_width = min(330, max(280, width // 3)) if self.sidebar_open else 0
        if self.sidebar_open:
            panel = pygame.Rect(width - panel_width, header.bottom, panel_width, height - header.bottom)
            self._draw_sidebar(panel)
            board_right = panel.left
        else:
            board_right = width
            self._button("sidebar_open", ">", pygame.Rect(width - 48, 70, 36, 38), small=True)

        board_area = pygame.Rect(24, 70, max(100, board_right - 48), height - 98)
        self._draw_board(board_area)

        if self.message:
            msg = self.small_font.render(self.message, True, COLORS["white"])
            rect = msg.get_rect(midbottom=(board_area.centerx, height - 12))
            self.screen.blit(msg, rect)

    def _draw(self):
        if self.page == "menu":
            self._draw_menu()
        else:
            self._draw_game()

    def _make_timeline(self, actions):
        states = [self.initial_state]
        owners = [{}]
        for action in actions:
            current = states[-1]
            next_state = next(
                candidate_state
                for candidate_action, candidate_state, _ in get_successors(current, self.grid)
                if candidate_action == action
            )
            owner_map = dict(owners[-1])
            moved_boxes = next_state.boxes - current.boxes
            if moved_boxes:
                moved_box = next(iter(moved_boxes))
                old_box = next(iter(current.boxes - next_state.boxes))
                owner_map.pop(old_box, None)
                owner_map[moved_box] = 1
            states.append(next_state)
            owners.append(owner_map)
        return states, owners

    def _choose_map(self):
        try:
            import tkinter as tk
            from tkinter import filedialog
            root = tk.Tk()
            root.withdraw()
            root.wm_attributes('-topmost', 1)
            root.update()
            
            selected = filedialog.askopenfilename(
                parent=root,
                title="Choose Sokoban map",
                filetypes=(("Text maps", "*.txt"), ("All files", "*.*")),
            )
            
            root.update()
            root.destroy()
            
            if not selected:
                return
                
            grid, initial_state = load_map(selected)
            if initial_state.agent_pos is None and self.mode == "single":
                raise ValueError("Bản đồ Single phải chứa vị trí người chơi 'A'")
                
            self.grid = grid
            self.initial_state = initial_state
            self.map_path = Path(selected)
            self.scaled_assets_cache.clear()
            self._reset_run()
            self.message = f"Loaded {self.map_path.name}"
        except Exception as error:
            self.message = f"Lỗi nạp map: {error}"

    def find_solution(self):
        self.playing = False
        self.message = f"Solving with {self.algorithm}..."
        self._draw()
        pygame.display.flip()
        
        actions, cost, visited = ALGORITHMS[self.algorithm](self.initial_state, self.grid)
        self.action_index = 0
        self.total_cost = cost if actions is not None else None
        self.visited = visited
        
        if actions is None:
            self.actions = []
            self.states = [self.initial_state]
            self.owner_timeline = [{}]
            self.message = "Không tìm thấy lời giải cho map này."
            return
            
        self.actions = actions
        self.states, self.owner_timeline = self._make_timeline(actions)
        self.playing = bool(actions)
        self.message = "Đã tìm thấy lời giải! Đang phát chuyển động." if actions else "Đã ở đích."

    def _step(self, amount):
        if self.mode == "two":
            if amount < 0:
                new_index = max(0, self.action_index + amount)
            elif self.action_index < len(self.actions):
                new_index = min(len(self.actions), self.action_index + amount)
            else:
                self._advance_competitive_turn()
                return

            if new_index != self.action_index:
                self.prev_state = self.states[self.action_index]
                self.action_index = new_index
                self.anim_t = 0.0
            return

        if not self.actions:
            return
        new_index = max(0, min(len(self.actions), self.action_index + amount))
        if new_index != self.action_index:
            self.prev_state = self.states[self.action_index]
            self.action_index = new_index
            self.anim_t = 0.0
            
        if self.action_index == len(self.actions):
            self.playing = False
            self.message = "Puzzle Solved!"

    def _activate(self, name):
        if name != "turn_limit_input":
            self.turn_limit_active = False
            
        if name in ("mode_single", "mode_single_menu"):
            self.mode = "single"
            self._reset_run()
            self.message = "Single-agent mode selected."
            
        elif name in ("mode_two", "mode_two_menu"):
            self.mode = "two"
            self._reset_run()
            
        elif name == "start":
            self.page = "game"
            self.sidebar_open = True
            self._reset_run()
            
        elif name in ("menu_map", "change_map"):
            self._choose_map()
            
        elif name == "load_p1":
            self._load_agent_file(1)
            
        elif name == "load_p2":
            self._load_agent_file(2)
            
        elif name == "spawn_pick_1":
            self.spawn_pick_agent = 1
            
        elif name == "spawn_pick_2":
            self.spawn_pick_agent = 2
            
        elif name == "clear_spawns":
            self.user_spawns = [None, None]
            self.message = "Đã xóa vị trí của cả 2 Agent. Vui lòng click để đặt lại."
            
        elif name == "home":
            self.page = "menu"
            self.playing = False
            
        elif name == "sidebar_close":
            self.sidebar_open = False
        elif name == "sidebar_open":
            self.sidebar_open = True
        elif name == "algo_ucs":
            self.algorithm = "UCS"
        elif name == "algo_astar":
            self.algorithm = "A*"
            
        elif name == "solve":
            self.find_solution()
            
        elif name == "start_match":
            if not self.playing and not isinstance(self.states[-1], CompetitiveGameState):
                self._start_competitive_match()
                
        elif name == "reset_match":
            self._reset_run()
            # Tự động gỡ các vị trí cũ để ép xếp lại
            self.user_spawns = [None, None]
            self.message = "Đã Reset trận đấu và xóa tọa độ Spawn."
                
        elif name == "turn_limit_input":
            self.turn_limit_active = True
            
        elif name == "play_pause" and (self.actions or self.mode == "two"):
            if self.mode == "two" and not isinstance(self.states[-1], CompetitiveGameState):
                self.message = "Vui lòng bấm 'Start Match' trước khi Auto Play."
            else:
                self.playing = not self.playing
                self.message = "Đang chạy mô phỏng..." if self.playing else "Đã dừng (Pause)."
                
        elif name == "step_back":
            self._step(-1)
        elif name == "step_forward":
            self._step(1)

    def run(self):
        running = True
        while running:
            dt = self.clock.tick(120) / 1000.0
            
            if self.anim_t < 1.0:
                self.anim_t = min(1.0, self.anim_t + self.anim_speed * dt)

            self._collect_competitive_turn()

            if self.page == "game" and self.playing:
                self.playback_elapsed += dt
                if self.playback_elapsed >= 0.22:
                    self.playback_elapsed = 0
                    self._step(1)

            for event in pygame.event.get():
                if event.type == pygame.QUIT:
                    running = False
                elif event.type == pygame.VIDEORESIZE:
                    self.screen = pygame.display.set_mode(event.size, pygame.RESIZABLE | pygame.DOUBLEBUF)
                    self.scaled_assets_cache.clear()
                elif event.type == pygame.KEYDOWN and self.page == "game":
                    if self.turn_limit_active:
                        if event.key in (pygame.K_RETURN, pygame.K_ESCAPE):
                            self.turn_limit_active = False
                        elif event.key == pygame.K_BACKSPACE:
                            self.turn_limit_text = self.turn_limit_text[:-1]
                        elif event.unicode.isdecimal() and len(self.turn_limit_text) < 5:
                            self.turn_limit_text += event.unicode
                        continue
                    if event.key == pygame.K_TAB:
                        self.sidebar_open = not self.sidebar_open
                    elif event.key == pygame.K_SPACE and (self.actions or self.mode == "two"):
                        if self.mode == "two" and not isinstance(self.states[-1], CompetitiveGameState):
                            self.message = "Vui lòng bấm 'Start Match' trước."
                        else:
                            self.playing = not self.playing
                            self.message = "Đang chạy mô phỏng..." if self.playing else "Đã dừng (Pause)."
                    elif event.key == pygame.K_LEFT:
                        self._step(-1)
                    elif event.key == pygame.K_RIGHT:
                        self._step(1)
                    elif event.key == pygame.K_r:
                        self._reset_run()
                elif event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
                    matched = False
                    for name, rect in self.buttons.items():
                        if rect.collidepoint(event.pos):
                            self._activate(name)
                            matched = True
                            break
                    if not matched:
                        self.turn_limit_active = False
                        self._select_spawn_at(event.pos)

            self._draw()
            pygame.display.flip()

        for future in self._pending_controller_futures or ():
            future.cancel()
        self._controller_pool.shutdown(wait=False, cancel_futures=True)
        pygame.quit()

def main():
    parser = argparse.ArgumentParser(description="Sokoban search game")
    parser.add_argument("--map", type=Path, default=ROOT / "example_map.txt", help="Initial map file")
    args = parser.parse_args()
    SokobanGame(args.map).run()

if __name__ == "__main__":
    main()