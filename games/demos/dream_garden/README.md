# Dream Garden

A small cooperative game for the Ventilastation talk at Overkill Festival 2026.
The festival's [Dream No Return theme](https://www.sickhouse.nl/festival/dream-no-return-2026)
inspired a garden whose players can choose a slower pace. This is an original
sample game, not a festival commission or an official festival game.

## Playing on the desktop

From the SDK root, after following the [desktop setup](../../../docs/guides/desktop.md):

```sh
./vs-emu.sh --game demos.dream_garden
```

Windows uses `vs-emu.bat --game demos.dream_garden`.

| Action | Controller | Player 1 keyboard | Player 2 keyboard |
| --- | --- | --- | --- |
| Begin / join | A | Space | Z |
| Drift around the rim | Left / Right | Left / Right arrows | H / L |
| Slow everyone's garden | Hold A | Hold Space | Hold Z |
| Rest and keep the flowers on screen | B | O | X |
| Toggle the quiet lullaby and bloom sound | X | P | C |
| Return to the launcher | Y / Back | Y / Page Down | V / End |

Catch a golden seed to plant a flower. Missing a seed has no penalty. A second
player joins by steering or pressing A, using an already reserved mint dreamer.
Either player can slow seed movement, the drifting background and flower
animation. New spawn intervals also lengthen, after the pending seed deadline.
Flowers gradually replace the oldest ones when the garden fills up.

There is no death, score, countdown or difficulty ramp. Garden and Rest scenes
have no idle timeout, so watching is welcome. Y/Back remains available. Sound
starts off. B stops the music and keeps the current flowers in a still garden.
A starts a new garden from the Rest scene.

## How the example works

`code/dream_garden.py` contains the whole game. `main()` returns Title, which
switches to Garden. Garden reserves its graph in `build()` and changes existing
objects in `update()`. A collision grows a flower instead of ending a run.
Pools cap seeds at 16 and flowers at 24, with explicit recycling for flowers.
The second player costs one reserved sprite even before joining.

The Garden graph uses **42 sprites, 2 tilemaps, 2 layers and 5 image strips**.
The flower pool counts toward that cost even when its slots are hidden. The
ground uses sparse, mostly transparent 16-pixel tiles. The HUD says DRIFT or
REST near the top rim, with both flips so the letters read upright.

The full CP437 font comes from the existing tutorial example. PNGs and YAML
compile into a generated image ROM. MP3s stay on the emulator host or console
base and never go into the rotor ROM. The sample follows the repository's GPLv3
license. [Artwork sources and rebuilding](art/README.md) record the new art and
original sound synthesis. The general SDK tutorial remains a separate example.

## Checks

From the SDK root:

```sh
python3 -m unittest discover -s tests -p test_dream_garden.py
mpy-cross games/demos/dream_garden/code/dream_garden.py -o /tmp/dream_garden.mpy
```

The tests exercise seam collisions, both controllers, shared slow time, safe
pool exhaustion, long play, opt-in audio, voluntary rest and the exit path.
