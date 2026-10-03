# Sokoban Project

## Run

Python 3.10+ and Pygame are required. Install dependencies and launch from the
project folder:

```bash
python -m pip install -r requirements.txt
python game_gui.py
```

The default layout is `example_map.txt`. Use **Choose map** on the title screen
or **Change Map** in the sidebar to load another text map.

## Modes

- **One Agent** solves the map with UCS or A* and plays back the action sequence.
- **Two Agents** runs player 1's GBFS controller and player 2's BFS controller.
	Press **Play** to open the match setup. Neither agent is placed automatically:
	select P1 or P2 in the sidebar and click an empty floor tile on the game board.
	Click an agent's marker to remove it; place both before starting the match and
	enter the turn limit `n`. `E` is parsed as optional map metadata but does not
	override the manual spawn choice.

In either mode, Space pauses/resumes, Left and Right move backward/forward, `R`
resets, and Tab toggles the sidebar. Competitive mode displays the current turn,
score, and result and supports replay navigation through completed turns.
Controller searches run in background workers so the Pygame event loop can keep
rendering and processing input. Recent-position memory and short goal cooldowns
discourage endless back-and-forth plans.

## Validation

Run a fast exhaustive heuristic property check on a small reachable state graph:

```bash
python experiment.py --heuristic-check-only
```

Run the focused competitive regression tests:

```bash
python -m unittest test_competitive.py
```

Run the UCS/A* timing and memory experiment on the provided map with:

```bash
python experiment.py
```

The supplied map currently exceeds the UCS implementation's 50,000-state
search limit, so the existing complexity comparison test does not complete with
matching UCS/A* solve outcomes. See `PROJECT_VALIDATION_AND_PRESENTATION.md` for
the verified results and remaining gaps.

The current development environment was Python 3.13.9 with Pygame 2.6.1.
Execution on macOS 13.7.8 / Intel Core i5 has not yet been verified.

## Assets

Optional PNGs in `assets/` are loaded automatically. Supported names are
`wall.png`, `floor.png`, `goal.png`, `box.png`, `box_agent1.png`,
`box_agent2.png`, `agent.png`, and `agent2.png`. Missing images use built-in
graphics; images are scaled to fit each map tile.