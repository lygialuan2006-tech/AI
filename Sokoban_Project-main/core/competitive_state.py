from __future__ import annotations

from collections.abc import Iterable, Mapping
from typing import TypeAlias

Position: TypeAlias = tuple[int, int]
Action: TypeAlias = str

ACTIONS: dict[Action, Position] = {
    "North": (-1, 0),
    "South": (1, 0),
    "East": (0, 1),
    "West": (0, -1),
    "Wait": (0, 0),
}


class CompetitiveGameState:
    """Trạng thái và bộ phân xử một lượt Sokoban hai agent."""

    def __init__(
        self,
        a1: Position,
        a2: Position,
        boxes: Iterable[Position],
        t: int = 0,
        owners: Mapping[Position, int] | None = None,
        box_owners: Mapping[Position, int] | None = None,
        owner_timeline: Iterable[Mapping[Position, int]] | None = None,
    ) -> None:
        self.a1 = tuple(a1)
        self.a2 = tuple(a2)
        self.boxes = frozenset(tuple(box) for box in boxes)
        self.t = int(t)
        self.owners = dict(owners or {})
        self.box_owners = dict(box_owners or {})
        if any(owner not in (0, 1, 2) for owner in self.owners.values()):
            raise ValueError("Owner phải là 0, 1 hoặc 2")
        if any(owner not in (0, 1, 2) for owner in self.box_owners.values()):
            raise ValueError("Box owner phải là 0, 1 hoặc 2")
        if self.a1 == self.a2 or self.a1 in self.boxes or self.a2 in self.boxes:
            raise ValueError("Agent không được chồng lên agent khác hoặc box")

        if owner_timeline is None:
            self._owner_timeline = (dict(self.box_owners),)
        else:
            snapshots = tuple(dict(snapshot) for snapshot in owner_timeline)
            self._owner_timeline = snapshots or (dict(self.owners),)
        self.last_actions: tuple[Action, Action] = ("Wait", "Wait")

    @property
    def agent_pos(self) -> Position:
        """Alias giúp các thành phần GUI cũ đọc được vị trí agent 1."""
        return self.a1

    @property
    def owner_timeline(self) -> tuple[dict[Position, int], ...]:
        """Trả về snapshot box-owner để GUI dựng màu theo từng lượt."""
        return tuple(dict(snapshot) for snapshot in self._owner_timeline)

    def score(self, agent_id: int) -> int:
        if agent_id not in (1, 2):
            raise ValueError("agent_id phải là 1 hoặc 2")
        return sum(owner == agent_id for owner in self.owners.values())

    @staticmethod
    def _inside(position: Position, grid: dict) -> bool:
        height, width = grid.get("height"), grid.get("width")
        return (
            (height is None or 0 <= position[0] < height)
            and (width is None or 0 <= position[1] < width)
        )

    def apply_joint_action(
        self, act1: Action, act2: Action, grid: dict
    ) -> CompetitiveGameState:
        """Phân xử hai action trên cùng snapshot rồi trả về state kế tiếp."""
        walls = grid.get("walls", set())
        goals = grid.get("goals", set())
        origins = (self.a1, self.a2)
        requested = (act1, act2)
        intents = []

        for agent_index, (origin, action) in enumerate(zip(origins, requested), start=1):
            if action not in ACTIONS:
                action = "Wait"
            dr, dc = ACTIONS[action]
            destination = (origin[0] + dr, origin[1] + dc)
            intent = {
                "action": action,
                "origin": origin,
                "destination": destination,
                "box_from": None,
                "box_to": None,
                "valid": True,
                "cancelled": False,
                "agent": agent_index,
            }

            # Luật tĩnh: không thể đi ra ngoài bản đồ hoặc xuyên tường.
            if not self._inside(destination, grid) or destination in walls:
                intent["valid"] = False
            elif destination in self.boxes:
                box_destination = (destination[0] + dr, destination[1] + dc)
                intent["box_from"] = destination
                intent["box_to"] = box_destination
                if not self._inside(box_destination, grid) or box_destination in walls:
                    intent["valid"] = False

            intents.append(intent)

        first, second = intents

        def cancel(*selected: dict) -> None:
            for intent in selected:
                intent["cancelled"] = True

        # Hai agent không được đổi chỗ xuyên qua nhau trong cùng một lượt.
        if (
            first["valid"]
            and second["valid"]
            and first["destination"] == second["origin"]
            and second["destination"] == first["origin"]
        ):
            cancel(first, second)

        # Hai agent cùng nhắm một ô thì cả hai action bị chuyển thành Wait.
        if (
            first["valid"]
            and second["valid"]
            and first["destination"] == second["destination"]
        ):
            cancel(first, second)

        # Tranh cùng một box hoặc hai box bị đẩy vào cùng một ô: hủy cả hai.
        same_box = (
            first["valid"]
            and second["valid"]
            and
            first["box_from"] is not None
            and first["box_from"] == second["box_from"]
        )
        same_box_destination = (
            first["valid"]
            and second["valid"]
            and
            first["box_to"] is not None
            and first["box_to"] == second["box_to"]
        )
        boxes_jammed = (
            first["valid"]
            and second["valid"]
            and first["box_to"] is not None
            and first["box_to"] == second["box_from"]
        ) or (
            first["valid"]
            and second["valid"]
            and second["box_to"] is not None
            and second["box_to"] == first["box_from"]
        )
        if same_box or same_box_destination or boxes_jammed:
            cancel(first, second)

        # Box không thể được đẩy vào ô agent kia đang đứng hoặc định bước tới.
        for pusher, other in ((first, second), (second, first)):
            if pusher["valid"] and pusher["box_to"] is not None:
                if pusher["box_to"] == other["origin"]:
                    pusher["cancelled"] = True
                elif pusher["box_to"] == other["destination"]:
                    cancel(pusher, other)

        # Nếu ô đích của box đang bị box kia chiếm, xử lý như hai box kẹt nhau.
        for pusher, other in ((first, second), (second, first)):
            if (
                pusher["valid"]
                and pusher["box_to"] in self.boxes
                and pusher["box_to"] != pusher["box_from"]
            ):
                if other["valid"] and other["box_from"] == pusher["box_to"]:
                    cancel(pusher, other)
                else:
                    pusher["cancelled"] = True

        # Khi một agent bị chặn/hủy, ô xuất phát của nó không được xem là đã nhường.
        # Lặp đến ổn định để xử lý các phụ thuộc dây chuyền.
        changed = True
        while changed:
            changed = False
            for mover, other in ((first, second), (second, first)):
                if mover["valid"] and not mover["cancelled"]:
                    if (
                        mover["destination"] == other["origin"]
                        and (not other["valid"] or other["cancelled"])
                    ):
                        mover["cancelled"] = True
                        changed = True

        moved_boxes: list[tuple[int, Position, Position]] = []
        next_agents = []
        for intent in intents:
            accepted = intent["valid"] and not intent["cancelled"]
            next_agents.append(intent["destination"] if accepted else intent["origin"])
            if accepted and intent["box_from"] is not None:
                moved_boxes.append(
                    (intent["agent"], intent["box_from"], intent["box_to"])
                )

        next_boxes = set(self.boxes)
        next_box_owners = dict(self.box_owners)
        for _, old_box, _ in moved_boxes:
            next_boxes.remove(old_box)
            next_box_owners.pop(old_box, None)
        for agent_id, _, new_box in moved_boxes:
            next_boxes.add(new_box)
            next_box_owners[new_box] = agent_id

        # Điểm gắn với ô goal: box rời goal thì xóa chủ cũ; box vào goal ghi chủ mới.
        next_owners = dict(self.owners)
        for _, old_box, _ in moved_boxes:
            if old_box in goals:
                next_owners[old_box] = 0
        for agent_id, _, new_box in moved_boxes:
            if new_box in goals:
                next_owners[new_box] = agent_id

        resolved_actions = tuple(
            intent["action"] if intent["valid"] and not intent["cancelled"] else "Wait"
            for intent in intents
        )
        history = self._owner_timeline + (dict(next_box_owners),)
        next_state = CompetitiveGameState(
            next_agents[0],
            next_agents[1],
            next_boxes,
            t=self.t + 1,
            owners=next_owners,
            box_owners=next_box_owners,
            owner_timeline=history,
        )
        next_state.last_actions = resolved_actions
        return next_state

    def __eq__(self, other: object) -> bool:
        return (
            isinstance(other, CompetitiveGameState)
            and self.a1 == other.a1
            and self.a2 == other.a2
            and self.boxes == other.boxes
            and self.t == other.t
            and self.owners == other.owners
            and self.box_owners == other.box_owners
        )

    def __hash__(self) -> int:
        return hash(
            (
                self.a1,
                self.a2,
                self.boxes,
                self.t,
                tuple(sorted(self.owners.items())),
                tuple(sorted(self.box_owners.items())),
            )
        )

    def __repr__(self) -> str:
        return (
            f"CompetitiveGameState(a1={self.a1}, a2={self.a2}, "
            f"boxes={set(self.boxes)}, t={self.t}, owners={self.owners}, "
            f"box_owners={self.box_owners})"
        )