# 7. Budgets and real hardware

The {term}`console` has on the order of 8 MB of RAM shared between MicroPython's
heap, image strips, audio and the interpreter, and a hard deadline every
{term}`column`. The {term}`budgets <budget>` exist so you find out at `build()`
rather than mid-game.

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

## Keep `update()` free of allocation

Creating a tuple, dict or formatted string every tick adds up to garbage the
console has to collect mid-game. Everything in this list is allocation-free, so
it is safe to call every tick (the reasons are in
[why VS2 works this way](../design-notes.md)):

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

The {term}`emulator` and the {term}`console` run the same renderer semantics, so a game that
looks right in the emulator generally looks right on the disc. Three things only
the real thing tells you:

**Timing.** The emulator does not enforce the per-column deadline. A scene near
the tilemap budget with several large maps is worth watching on hardware.

**Legibility.** The 256 angular steps are spread around a large circumference at
the rim and crammed into almost nothing at the centre, so the same glyph is
crisp near the rim and unreadable near the middle. Text belongs at **low Y** on
a `HUD` layer — the in-tree games put their scoreboards at `y=0` or `y=1`.
Nothing warns you about this; you have to look at it:

```{figure} ../images/budgets-legibility.png
:alt: The same score at y = 1, crisp at the bottom rim, and at y = 44, a tiny unreadable smudge near the centre
:width: 60%
:align: center

The same label at `y = 1` and at `y = 44`.
```

**Backgrounds.** Dark or black backgrounds work better on the real
Ventilastation than bright ones, and the emulator may not show you the
difference. Leave empty space empty — `EMPTY_TILE` cells and transparent pixels
draw nothing — and keep any backdrop you do draw dark. A tilemap that lights
the whole disc, like the `fill(GRASS)` call in chapter 5, is the exception.


## Packaging

`tools/package_game.py` builds a `.vs2` package — a zip of your `meta.json`,
code, ROM, icon and sounds — to share a game as a single file.

## Where to look next

- The [API reference](../reference/index.md) for the full surface, and the
  [glossary](../glossary.md) for any term you have forgotten.
- [Going further](../going-further.md) for features this tutorial skipped.
- Real games in the tree: `games/alecu/mapdemo` is the smallest complete VS2
  game, `games/demos/input_demo` shows every control, and
  `games/alecu/vixeous` uses pools, a scrolling terrain map and labels together.
- `games/demos/povstress` is the stress case, deliberately near the budgets.
