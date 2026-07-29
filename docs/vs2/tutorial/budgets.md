# 7. Budgets and real hardware

The console has on the order of 8 MB of RAM shared between MicroPython's heap,
image strips, audio and the interpreter, and a hard deadline every column. The
budgets exist so you find out at `build()` rather than mid-game.

| Resource | Budget | Notes |
|---|---|---|
| Layers | 8 | Most games use two or three |
| Sprites | 100 | Pools count in full, up front |
| Tilemaps | 16 | **A label counts as one** |
| Image strips | 100 | Per asset pack |

Read them at runtime from `vs2.limits` — see
{py:attr}`vs2.limits.sprites` and its neighbours in the
[reference](../reference/services.md).

## Reading the errors

Every one of these is raised the first time the scene is entered, never later:

```text
ResourceLimitError: sprite 101/100 in Vixeous (world: 62, hud: 39);
  reduce the sprite budget
```

The census names every layer holding sprites, so the oversized one is visible
without counting by hand.

```text
ResourceLimitError: tilemap 17/16 in MapDemo (world: 14, hud: 3);
  reduce the tilemap budget
```

Remember labels land here, not in the sprite budget.

```text
AssetLimitError: myname.mygame defines 103 images; this target supports 100
```

Too many strips in `__images__.yaml`. Combine related art into one strip with
more frames.

## Staying inside them

**Text belongs in labels.** Three lines of text as one sprite per character cost
54 of 100 slots. As three labels they cost three tilemap records, and the cost
does not grow with the text.

**Pools, not lists.** A `sprite_pool(count=16)` states its cost in one number
that shows up in the census. Sixteen individually created sprites do not.

**Cell data, not sprites.** Anything on a grid — terrain, a starfield, a
tile-based background — is one tilemap record however many cells it has.

## The rule that makes it hold

Nothing in the running game may allocate. That is why the scene is sealed after
`build()`, why pools exist, why `view_x`/`view_y` are scalars rather than a
viewport tuple, and why {py:meth}`~vs2.Label.set_number` exists instead of
`"%05d" %`.

A per-frame tuple, dict or formatted string is not "a little garbage" here: over
a session it is the difference between a stable heap and a GC pause landing on a
visible frame. These all allocate nothing:

```python
sprite.x += 0.5
sprite.frame = 3
pool.spawn(x, y)
pool.despawn(shot)
tilemap.view_y = depth % tilemap.tile_height
tilemap[col, row] = ROCK
label.set_number(score, width=5)
joy1.held(LEFT)
```

## Moving to the console

The emulator and the hardware run the same renderer semantics, so a game that
looks right in the emulator generally looks right on the disc. Two things only
the real thing tells you:

**Timing.** The emulator does not enforce the per-column deadline. A scene near
the tilemap budget with several large maps is worth watching on hardware.

**Legibility.** The 256 angular steps are spread around a large circumference at
the rim and crammed into almost nothing at the centre, so the same glyph is
crisp near the rim and unreadable near the middle. Text belongs at **low Y** on
a `HUD` layer — the in-tree games put their scoreboards at `y=0` or `y=1`.
Nothing warns you about this; you have to look at it.

## Packaging

`tools/package_game.py` builds a `.vs2` package — a zip of your `meta.json`,
code, ROM, icon and sounds — and stamps `api_revision` into the metadata so the
loader can reject a package built against an older API.

## Where to look next

- The [API reference](../reference/index.md) for the full surface.
- Real games in the tree: `games/alecu/mapdemo` is the smallest complete VS2
  game, `games/demos/input_demo` shows every control, and
  `games/alecu/vixeous` uses pools, a scrolling terrain map and labels together.
- `games/demos/povstress` is the stress case, deliberately near the budgets.
