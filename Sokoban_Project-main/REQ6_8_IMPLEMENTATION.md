# Req 6-8: Competitive Sokoban

## Files

- `core/competitive_state.py` defines the immutable-by-convention competitive state model and simultaneous turn resolver. `CompetitiveGameState` stores both agent positions, box positions, turn count, goal scoring ownership, visual box ownership, action resolution, and ownership history. `apply_joint_action()` validates both intentions from the same pre-turn state, resolves conflicts, moves accepted agents/boxes together, updates ownership, and returns the next state. `score()` counts goals owned by an agent; `owner_timeline` returns box-owner snapshots for GUI replay.
- `competitive/agent_player1.py` provides player 1's GBFS controller. `get_action()` selects an unowned/opponent goal, plans toward placing or dislodging a box, and returns only the first action. Reverse-push BFS and reachable pushing-position distances inform the search. Recent positions are penalized; a goal the agent just vacated is temporarily cooled down. The requested budget is capped at 950 ms, and timeout returns the best partial step or a safe legal fallback.
- `competitive/agent_player2.py` provides player 2's separate BFS controller. Its `get_action()` searches legal walking/pushing states toward a selected goal and returns one action. It shares recent-position tracking and goal cooldowns and has a legal-move timeout fallback.
- `competitive/controller_memory.py` stores short per-agent recent-position histories and temporarily suppresses immediate re-targeting of a goal that the same agent has just vacated.
- `core/map_loader.py` recognizes optional `E` map metadata and exposes it as `grid['agent2_start']`; the competitive GUI deliberately does not use it as an automatic spawn. Existing one-agent maps remain valid.
- `game_gui.py` connects the competitive model and both controllers to Pygame. It provides a turn-limit input, match start/pause, forward/backward replay, live scores, final result, and distinct player/box colors. Search runs on background workers; each controller gets a 250 ms GUI budget. Press Play to enter setup, select P1/P2 in the sidebar, then click an empty tile on the game board to place that agent; click its marker to remove it. The match cannot start until both are placed. Spawn overrides reset when changing maps.

## Arbitration and scoring

Each controller sees the same state snapshot. The state resolver converts invalid actions to `Wait`, blocks head-on swaps and shared destinations, cancels competing or jammed pushes, rejects pushes into the other agent, and propagates cancellations when a mover depends on an agent that did not leave its cell. Accepted actions are then applied simultaneously. Moving a box off a goal resets that goal's scoring owner to `0`; pushing a box onto a goal assigns that goal to the pushing agent. Independently, every pushed box records its last pusher for GUI coloring, even when it is no longer on a goal. Starting goals, including goals occupied by `C`, begin unowned.

## Run

```text
python -m pip install -r requirements.txt
python game_gui.py
```

Choose **Two Agents**, set `n` in the turn-limit field, and start the match. Space pauses/resumes. Left and Right navigate the recorded match. A map can place the second agent with `E`; `A`, `B`, `C`, `D`, and `%` retain their single-agent meanings.

An 80-turn run on `example_map.txt` completed without unchanged board states or `Wait/Wait` turns after adding timeout progress fallbacks; the maximum observed turn time with 250 ms per-controller budgets was 0.463 seconds in the current development environment. In a separate headless check, Pygame rendered while worker searches were active; this confirms the event loop is not synchronously waiting on search, but is not a physical-display FPS benchmark.
