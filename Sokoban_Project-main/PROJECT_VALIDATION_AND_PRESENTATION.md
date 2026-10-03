# Project Validation and Presentation Notes

## Scope and verdict

This review maps the assignment's Task 1 requirements (Req 1-8) to the current source. “Pass” means the implementation path exists and the listed focused check passed; it does not certify macOS behavior or competitive strength. The attached formulation describes the intended model. The supplied-map UCS regression currently fails because the solver stops at its 50,000-state limit.

## File-to-requirement map

| File | Requirements | Responsibility |
|---|---|---|
| `core/state.py` | Req 1-2 | Single-agent state, goal test, four actions, legal successor generation, one-unit action cost. Successors now enforce grid bounds as well as walls and box blocking. |
| `core/map_loader.py` | Req 1, 5-6, 8 | Parses `%`, `A`, `B`, `C`, `D`, and optional `E`; returns static walls/goals and the initial single-agent state. Competitive GUI spawn positions are selected manually and do not default to `A`/`E`. |
| `search/ucs.py` | Req 2-3 | Uniform-cost search; reports expanded states and has a 50,000-state default cutoff. |
| `search/astar.py` | Req 2 | A* search, deadlock pruning, path reconstruction, and expanded-state count. |
| `search/heuristic.py` | Req 2, 4 | Wall-aware BFS distances, Hungarian box-goal assignment, corner deadlock detection, and map-scoped caches. |
| `experiment.py` | Req 3-4 | Runtime/search experiment and heuristic checks. `--heuristic-check-only` exhaustively checks admissibility and consistency over a small reachable graph using exact reverse-BFS distances. |
| `test_complexity.py` | Req 3 | Repeated runtime, peak-memory, visited-state and solution comparison for UCS/A* on `example_map.txt`. Currently fails when UCS reaches its cutoff while A* solves. |
| `core/competitive_state.py` | Req 6, 8 | Competitive state and simultaneous arbitration; tracks goal scoring owners separately from last-pusher box colors, keeps turn history, and computes scores. |
| `competitive/agent_player1.py` | Req 7-8 | Player 1 GBFS with reachable push-position heuristic, recent-position penalty, goal cooldown, deadline and legal fallback. |
| `competitive/agent_player2.py` | Req 7-8 | Player 2 BFS in a separate module, with recent-position/cooldown checks and legal fallback. |
| `competitive/controller_memory.py` | Req 7-8 | Per-agent short history used to suppress immediate movement loops and repeated goal recapture. |
| `test_competitive.py` | Req 6-8 | Focused regression tests for off-goal box ownership, goal cooldown and legal timeout progress. |
| `game_gui.py` | Req 5, 8 | Pygame single/competitive modes, background controller workers, post-Play in-game P1/P2 spawn placement/removal, scores/turns, owner-colored boxes and replay. |
| `requirements.txt` | Req 5 | Declares Pygame as the only third-party dependency. Current environment has Pygame 2.6.1. |
| `README.md` | Run instructions | Installation, controls, map symbols, validation commands, and environment caveats. |
| `REQ6_8_IMPLEMENTATION.md` | Req 6-8 | Focused explanation of competitive state, arbitration, controllers, and UI behavior. |
| `IMPLEMENTATION_PLAN_AGENT2.md` | Design history | Earlier proposal/plan; its original status text may not reflect the current implementation. |

## Requirement status

| Req | Status | Evidence and remaining work |
|---|---|---|
| 1. State-space formulation | **Pass with a map-validation caveat** | State is `(agent position, box positions)`; walls/goals are static; actions, push rules, goal test and unit cost are represented. Successor generation now rejects out-of-grid positions. The loader does not yet reject malformed maps such as missing `A` or unequal box/goal counts. |
| 2. UCS and A* | **Partial** | Both algorithms are implemented. On a small known map, both returned the same optimal cost, 2. A* solved `example_map.txt` at cost 42 after expanding 440,704 states. UCS stopped at 50,000 states and did not solve that supplied map. |
| 3. Time and space comparison | **Partial** | The experiment records runtime, `tracemalloc` peak memory and expanded states. `python -m unittest test_complexity.py` failed after about 308 seconds because the UCS/A* solve outcomes differed; the current run does not produce a valid same-map solution comparison. |
| 4. Heuristic properties | **Partial, improved** | A new exhaustive check passed for all 5 reachable/solvable states in a small fixture: admissible and consistent. This is evidence for that fixture, not a proof for every map. The assigned map is not exhaustively verified. |
| 5. Pygame single-agent UI | **Partial** | UCS/A* selection, action count, pause, forward/back, and OOP GUI exist. Headless draw/play checks passed. macOS 13.7.8 on Intel has not been tested; dependency compatibility on that target is therefore unconfirmed. |
| 6. Competitive model | **Pass for implemented rules** | Simultaneous snapshot, body/swap/push conflicts, blocked pushes, cascading cancellation, scoring ownership and box-color ownership are implemented. Focused collision and ownership checks passed. |
| 7. Decision controllers and 1,000 ms limit | **Implemented; worst-case timing not certified** | Separate GBFS/BFS modules expose `get_action`, capped at 950 ms. The GUI currently gives each controller 250 ms. Timeout returns a progress-preserving legal fallback when possible. No worst-case timing benchmark across large maps/platforms has been recorded. |
| 8. Competitive Pygame | **Pass in headless smoke test** | GUI runs a match to `n`, allows P1/P2 spawn selection from preview, displays scores/result, distinguishes box owners off-goal, and supports replay. Background workers keep the event loop from synchronously waiting for search. Desktop/macOS usability and physical FPS still need measurement. |

### Commands and observed checks

- `python -m py_compile ...`: all touched Python modules compile.
- `python experiment.py --heuristic-check-only`: **5 states, 5 solvable; admissible=True, consistent=True**.
- `python -m unittest test_competitive.py`: **3 competitive regression tests passed**.
- Small Sokoban fixture: UCS and A* both solved with cost **2**.
- `example_map.txt`: A* solved with cost **42** and **440,704 expanded states**.
- `test_complexity.py`: **failed** after roughly **308 seconds**; UCS hit its 50,000-state cutoff while A* solved.
- Competitive checks: body clash, swap, box dispute, jammed boxes, box-agent collision, cascade cancellation, score reset, box color ownership, GUI draw, match end, and replay navigation passed in focused/headless checks.
- Late-game stall regression: an 80-turn run on `example_map.txt` after the controller fallback/budget change had **0 unchanged board turns**, **0 `Wait/Wait` turns**, scores changed during play, and a maximum observed turn time of **0.463 seconds** with 250 ms budgets per controller. This is a local sample, not a worst-case guarantee.
- Controller loop regression: after adding push-position distance, recent-position avoidance and goal cooldowns, the first 50 turns on `example_map.txt` visited **7 distinct P1 positions in turns 31-40**, rather than the previously observed three-cell loop. Agent scores changed during the run. This measures this controller/map combination only.
- Development environment: Python **3.13.9**, Pygame **2.6.1**. macOS target not available in this validation environment.

## Presentation prep (5 minutes maximum)

Use a 4:3 slide canvas, white/light background, high-contrast text, and labels/patterns as well as colors so diagrams remain clear in grayscale. Do not place source code on slides. Replace the member placeholders with real IDs, names, emails, assigned tasks and verified completion percentages.

| Slide | Time | Content and visual |
|---|---:|---|
| 1. Problem and team | 0:00-0:35 | Sokoban objective, map symbols, member table. Show a small labeled board rather than a title-only slide. |
| 2. Single-agent search | 0:35-1:35 | State `(agent, boxes)`, four actions, push transition and goal test. Diagram UCS vs A*; describe wall-aware BFS distances plus Hungarian matching, not Manhattan/Euclidean distance. |
| 3. Measurement and heuristic | 1:35-2:25 | Show time, memory and expanded-state metrics. Report the verified small-graph result and honestly state that UCS hit its node cap on the supplied map while A* solved it. Explain the scope of the heuristic check. |
| 4. Competitive model | 2:25-3:45 | Joint action snapshot -> arbitration -> simultaneous update -> score. Name the GBFS and BFS controllers, separate modules, 950 ms controller cap, and `Wait` timeout behavior. |
| 5. GUI and conclusion | 3:45-5:00 | Demo turn input, two agents, box colors, live score, pause and replay. Close with verified items and remaining macOS/UCS validation work. |

For a demo video of at most three minutes: launch the GUI; show a short A* single-agent solve; switch to Two Agents, enter a small `n`, run the match, pause, step backward/forward, and show the final score. Use a compact map with an explicit `E` spawn and reachable boxes/goals. Avoid promising a score change unless it occurs during the recorded run.

## Before submission

1. Resolve the UCS cutoff on the assigned map or clearly select a benchmark map both algorithms can solve and report the cutoff as a separate result.
2. Run and save the complete Req 3 measurements; do not claim a comparison from the failed current test.
3. Keep heuristic claims scoped to experiments actually run; the exhaustive check covers the small fixture only.
4. Test installation, GUI controls and controller timing on macOS 13.7.8 / Intel as required by the assignment.
5. Update the old implementation plan's status, and fill in actual group/member data and task completion percentages for the presentation.
