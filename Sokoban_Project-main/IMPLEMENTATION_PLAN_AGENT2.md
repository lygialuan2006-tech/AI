# Agent 2 and Search Extension Plan

## Current Status

- Competitive mode is implemented in `core/competitive_state.py`, the two controller modules under `competitive/`, and `game_gui.py`.
- The original plan and acceptance criteria below are retained as design history; use `REQ6_8_IMPLEMENTATION.md` for the current competitive behavior and `PROJECT_VALIDATION_AND_PRESENTATION.md` for validation status and remaining work.
- The single-agent `GameState` and UCS/A* APIs remain separate from the competitive state model.

## Proposed State Model

Keep the existing `GameState` unchanged so existing UCS/A* and benchmark behavior remain stable. Add a separate immutable `CompetitiveState` for two-agent matches:

- `agents`: the two agent positions, indexed by agent ID.
- `boxes`: all current box positions.
- `box_owners`: a mapping from box position to the ID of the agent that most recently pushed it.
- `turn`: completed simultaneous turns.
- `score`: derived from boxes currently on goals and their recorded owner.

Moving a box must move its owner entry with it. When either agent pushes that box, replace the owner with the pushing agent. This supports pushing a box off a goal and later claiming it by placing it on a goal again.

## Simultaneous Turn Resolution

1. Ask each controller for one action using the same read-only state snapshot.
2. Convert both actions into movement or push intents without mutating the snapshot.
3. Validate walls, boxes, destination cells, agent overlap, crossing/swapping positions, and simultaneous pushes.
4. Resolve conflicts deterministically. Recommended initial policy: reject both actions involved in a conflict; document this policy in the UI and tests.
5. Apply all remaining non-conflicting intents together to produce one new `CompetitiveState`.
6. Recompute score and finish after the user-provided turn limit.

The engine should define a `Wait` action so a controller can yield instead of proposing an invalid move.

## Search Plug-in Design

Provide a small controller interface, for example `choose_action(state, agent_id, grid, deadline) -> action`. Keep each competing agent implementation in a separate module, as required by the assignment.

Search algorithms should be independently selectable and addable as modules. A proposed contract for a search module is:

- stable identifier and display name;
- a `find_plan(problem, deadline)` or `choose_action(problem, deadline)` entry point;
- explicit handling of no-path and deadline outcomes;
- no dependence on Pygame, so algorithms can be tested independently.

Start with the algorithms already available, then add DFS/BFS/UCS/A* as separate modules. Use an explicit registry or validated discovery of modules in a documented search-plugin folder. The UI should list only modules that satisfy the contract and show a useful error if a plug-in fails to load. Do not use unrestricted dynamic imports from arbitrary paths.

Each decision must respect the 1,000 ms limit. Pass a monotonic deadline through the controller and search loop, stop before the deadline, and return a legal fallback action such as `Wait` if planning runs out of time.

## Implementation Sequence

1. Add `CompetitiveState` and tests while leaving `GameState` intact.
2. Implement pure action-intent generation and simultaneous conflict resolution; test collisions, swaps, pushes, and blocked moves.
3. Add owner transfer and goal scoring tests, including removing and reclaiming an already placed box.
4. Define the controller/search contracts and register the existing algorithms without changing their single-agent public APIs.
5. Add independent agent modules and per-agent algorithm selection in the competitive sidebar.
6. Connect the competitive UI to turn execution, turn limit, score, reset, and history playback.
7. Render agent sprites and owner-specific box sprites from the competitive state; retain generic asset fallbacks.
8. Validate the 1,000 ms decision limit and rerun the existing single-agent benchmark and GUI smoke tests.

## Acceptance Criteria

- Existing single-agent UCS/A* behavior and benchmark remain unchanged.
- Each competitive turn is computed from one shared pre-turn snapshot.
- Agents cannot overlap, swap through one another, or push boxes into illegal cells.
- Box ownership changes only when pushed and follows the box afterward.
- Scores count boxes on goals for their current recorded owner.
- Each agent's algorithm is selectable independently, and a new conforming search module can be registered without modifying the game-state engine.
- A timed-out controller returns a legal fallback within the one-second limit.
- The GUI clearly distinguishes unowned boxes and boxes owned by either agent using the supplied sprites.
