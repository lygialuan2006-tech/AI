import unittest

from competitive import controller_memory
from competitive.agent_player1 import get_action as player1_action
from competitive.agent_player2 import get_action as player2_action
from core.competitive_state import CompetitiveGameState


class CompetitiveControllerTests(unittest.TestCase):
    def setUp(self):
        controller_memory._MEMORY.clear()
        self.grid = {
            "height": 5,
            "width": 7,
            "walls": set(),
            "goals": {(2, 4)},
        }

    def test_box_keeps_color_owner_when_pushed_off_goal(self):
        state = CompetitiveGameState(
            (0, 0),
            (2, 5),
            {(2, 4)},
            owners={(2, 4): 2},
            box_owners={(2, 4): 2},
        )
        next_state = state.apply_joint_action("Wait", "West", self.grid)

        self.assertEqual(next_state.owners[(2, 4)], 0)
        self.assertEqual(next_state.box_owners[(2, 3)], 2)
        self.assertEqual(next_state.owner_timeline[-1][(2, 3)], 2)

    def test_goal_is_cooled_after_agent_pushes_its_box_off(self):
        state = CompetitiveGameState(
            (0, 0),
            (2, 5),
            {(2, 4)},
            owners={(2, 4): 2},
            box_owners={(2, 4): 2},
        )
        controller_memory.update_agent_memory(2, state, self.grid)
        next_state = state.apply_joint_action("Wait", "West", self.grid)
        _, cooled_goals = controller_memory.update_agent_memory(
            2, next_state, self.grid
        )

        self.assertIn((2, 4), cooled_goals)

    def test_zero_budget_controllers_choose_legal_progress_when_available(self):
        state = CompetitiveGameState(
            (2, 1),
            (4, 5),
            {(2, 3)},
            owners={(2, 4): 0},
        )

        action1 = player1_action(1, state, self.grid, time_limit=0)
        action2 = player2_action(2, state, self.grid, time_limit=0)
        next_state = state.apply_joint_action(action1, action2, self.grid)

        self.assertNotEqual(action1, "Wait")
        self.assertNotEqual(action2, "Wait")
        self.assertNotEqual(next_state.a1, state.a1)
        self.assertNotEqual(next_state.a2, state.a2)
        self.assertNotEqual(next_state.a1, next_state.a2)


if __name__ == "__main__":
    unittest.main(verbosity=2)
