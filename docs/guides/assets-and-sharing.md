# Assets, menu and sharing

Use this after [your first game](../vs2/tutorial/first-game.md). It is the common
layout for current VS2 games, independent of which editor you use.

## One folder per game

```text
games/<group>/<name>/
  code/<name>.py          main() returns a vs2.Scene
  images/                PNGs and __images__.yaml
  sounds/                MP3 music and effects (optional)
  menu.png               64 × 30 pixel menu icon
  meta.json              API selection and menu metadata
```

The launcher discovers these folders. Do not edit launcher code to add a game.
Run directly with `./vs-emu.sh --game group.name`, or `vs-emu.bat --game group.name`
on Windows.

```json
{
  "api": "vs2",
  "api_revision": 2,
  "title": "My Game",
  "order": 50
}
```

Both API fields are required for VS2. `order` sorts menu entries; `hidden: true`
keeps an installed game off the menu. For an animated menu strip, use
`menu_frames` and `menu_frame`; each frame is 64 × 30 pixels.

## Images and audio

[Chapter 1](../vs2/tutorial/first-game.md#images) is the canonical guide to
`__images__.yaml`, frame counts and palette groups. The emulator generates ROMs
from changed assets; do not commit generated ROMs. The game defaults to its own
asset pack, so a new VS2 game does not need V1's `stripes_rom` attribute.

Audio is MP3 data in `sounds/`. Call `vs2.audio.sound("shoot")` for `shoot.mp3`
and `vs2.audio.music("theme", loop=True)` for `theme.mp3`.
The base or emulator host plays it; audio is not copied into the rotor's ROMs
or RAM. See the [audio reference](../vs2/reference/services.md#vs2audio).
Keep attribution and source/licence notes with any art or audio you reuse.

## Package or contribute

From the repository root:

```sh
python tools/package_game.py --help
python tools/package_game.py games/myname/mygame --output /tmp/vsdk-packages
```

A `.vs2` package contains runtime code, metadata, compiled ROM, icon and sounds.
Keep the source folder separately: a distribution package is not a substitute
for original PNGs and editable art. Installation details and hardware verification
limits are in the [package contract](../internals/game-packages.md).

To contribute a game, fork the SDK, commit its complete folder, and open a pull
request against `ventilastation/vsdk`. Preserve asset credits. If the game needs
an SDK change, discuss it in an issue or submit that change separately.

Current examples: `games/demos/tutorial_game` follows the tutorial;
`games/demos/input_demo` demonstrates controls; `games/alecu/vyruss_vs2` is a
larger game. The similarly named `games/alecu/vyruss` uses the obsolete V1 API.
