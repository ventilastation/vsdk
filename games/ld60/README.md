# LD60 Circular Arcade

Five small games for the disc, based on the concept prototypes in the Ludum Dare
60 entry "Circular Arcade" (<https://tmtg.nl/ludumdare/ld60/>, built with the JGame
engine). The original plays on a screen that is bent into a circle; here the same
five levels are written with the VS2 API, so the bending is done by the display.

All five share a design:

- The world is 32 tiles of 8 pixels, so it is exactly one trip round the disc.
  Tile row 0 is the rim and the rows count toward the centre, on a `TUNNEL`
  layer, so the rows near the rim are big and the middle of the disc is where
  the ground, or the rest of the tunnel, is too small to play on.
- The camera turns with you. You are always at the top of the disc (x = 128),
  except in Rim Runner, where you run on the rim at the bottom, so the picture
  never leaves your end of the display.
- Rim Runner also scrolls inward with you, keeping your feet about four LEDs from
  the rim, since things near the middle of the disc are hard to read. It only
  stops following where the level runs out above you.
- Everything is made once in `build()` and moved afterwards: tiles come from one
  `bytearray` shared with the tilemap, sprites are fixed lists, and the walls get
  their outline from an autotile pass at build time. (Spiral Tunnel's edges are
  slanted tiles instead, like the prototype's, since the tunnel moves sideways as
  it goes down.)
- You are scored on the time you take to finish. Faster than your best saves a
  new best (`vs2.saves`, under the name `best`).

| Game | You... | Controls |
|---|---|---|
| Spiral Tunnel | dive down a tunnel that winds round the disc, bombing the UFOs that patrol it | arrows steer (left/right change your speed round the disc), A bombs |
| Catch the Robots | run through a random maze, catching all 20 wall-hugging robots | arrows |
| Rim Runner | run and jump round the inside of the rim, collecting eggs, landing on birds | left/right run, up or A jumps |
| Dodge 'Em | drive a five-lane track, eating pills while red cars come the other way | up/down change lane (only at the gaps in the walls), right speeds up, left slows |
| Defender | fly over a planet, shooting the aliens before they shoot you | arrows fly, A fires |

## What changed from the prototypes

- Controls are the controller's, not W A S D and L.
- Rim Runner's platforms are four tiles above each other instead of five. A jump
  rises about 4.6 tiles, so the originals could not be reached from below.
- The tunnel and the maze are shorter, and the numbers (speeds, gravity) are
  scaled from the prototype's 60 frames a second to the console's 33 ticks.
- The prototype ends a level; here every game ends with its time and starts again
  on A.

## Art and sound

Art is generated, not drawn by hand: run `python3 tools/ld60_assets/make_art.py`
to rewrite every `images/tiles.png`, `images/sprites.png` and `menu.png`, and
`python3 tools/ld60_assets/make_sounds.py` (needs ffmpeg) for the MP3s in
`sounds/`. The font is the tutorial's `steel8x8.png`.
