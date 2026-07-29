# vs2 API Guide — moved

This guide has been replaced by the VS2 documentation site in
[docs/vs2/](vs2/), which is built with Sphinx and published to Read the Docs.

It describes API **revision 2**, and everything that used to be on this page is
now either in the tutorial or generated from the source:

| Looking for | Now in |
|---|---|
| Basic scene, getting started | [Tutorial ch. 1 — Your first game](vs2/tutorial/first-game.md) |
| Coordinates, modes/projections | [ch. 2 — The circular display](vs2/tutorial/display.md) |
| Sprites, collisions | [ch. 3 — Sprites](vs2/tutorial/sprites.md) |
| Object pooling | [ch. 4 — Sprite pools](vs2/tutorial/pools.md) |
| Tilemaps, text | [ch. 5 — Tilemaps and text](vs2/tutorial/tilemaps-and-text.md) |
| Layers, scenes, input, sound | [ch. 6 — Scenes, input and sound](vs2/tutorial/scenes-and-input.md) |
| Memory and rendering contract | [ch. 7 — Budgets and real hardware](vs2/tutorial/budgets.md) |
| Starfield | `Scene.starfield`, see ch. 6 |
| Every class and method | [API reference](vs2/reference/index.md) |

## What changed in revision 2

The API this page used to document is gone, not deprecated. If you are porting
a game written against it:

| Was | Now |
|---|---|
| `Sprite("x.png")` then `layer.add(...)` | `layer.sprite("x.png")` — the layer creates and owns it |
| `mode=` on a drawable | `projection=` on the layer |
| `stripes_rom = "me.game"` | nothing; the asset pack defaults to your game |
| `on_enter` / `step` / `on_exit` | `build` / `update` / `teardown` |
| `super().on_enter()` | nothing to call |
| `director.is_pressed(director.JOY_LEFT)` | `joy1.held(LEFT)` |
| `director.pop()` + `raise StopIteration()` | `return self.pop()` |
| `viewport=(x, y, w, h)` tuple | scalar `view_x` / `view_y` |
| `Sprite(replacing=...)`, hand-rolled pools | `layer.sprite_pool(...)` |
| One sprite per character of text | `layer.label(...)` |
| `set_starfield(True)` | `starfield = True` on the scene |
| `PIXELS`, `% 256` | `vs2.display.height`, `vs2.display.width` |

Games must also declare `"api_revision": 2` in `meta.json`; the loader rejects a
`vs2` game without it.

## Building the docs locally

```sh
python3 -m venv .venv && .venv/bin/pip install -r docs/vs2/requirements.txt
.venv/bin/python -m sphinx -b html docs/vs2 docs/vs2/_build/html
```

Then open `docs/vs2/_build/html/index.html`.
