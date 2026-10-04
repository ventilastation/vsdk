# Migrating older games

New games should begin with [the current tutorial](tutorial/first-game.md).
There are two different older APIs; distinguish them before porting.

## Original sprites API (V1)

Games importing `ventilastation.sprites` are legacy games. They still run,
but this API is obsolete for new development. Keep a working V1 game intact
until you intentionally port it; never mix V1 and VS2 imports in one game.

A port uses `vs2.Scene`, creates layers/drawables in `build()`, moves them in
`update()`, and declares both `"api": "vs2"` and `"api_revision": 2`.
Use the tutorial and generated reference to port one scene at a time.
The [V1 maintenance guide](../legacy/sprites-api.md) explains the old lifecycle.

## Removed VS2 prototype (revision 1)


The early VS2 prototype API is gone, not deprecated. If you are porting
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
