# LD60 Circular Arcade

## Credits

**The ideas for all five games are by
[@borisvanschooten](https://github.com/borisvanschooten).** Together they are
the Ludum Dare 60 entry "Circular Arcade", originally published at
<https://tmtg.nl/ludumdare/ld60/jgame.html?game=jgame-games/ld60/>.

Spiral Tunnel, Catch the Robots, Rim Runner, Dodge 'Em and Defender, their
levels, rules, enemies and the idea of playing an arcade game on a circle all
come from that entry. What this folder adds is only the port to Ventilastation:
the VS2 code, the generated art and sound, and the changes listed under "What
changed from the prototypes" below.

## The games

Five small games for the disc. The original plays on a screen that is bent into
a circle; here the same five levels are written with the VS2 API, so the bending
is done by the display.

All five share a design:

- The world is 32 tiles of 8 pixels, so it is exactly one trip round the disc.
  Tile row 0 is the rim and the rows count toward the centre, on a `TUNNEL`
  layer, so the rows near the rim are big and the middle of the disc is where
  the ground, or the rest of the tunnel, is too small to play on.
- The camera turns with you. You are always near the top of the disc (x = 128),
  except in Rim Runner, where you run on the rim at the bottom, so the picture
  never leaves your end of the display.
- As in the prototype, you move at once and the camera follows a moment behind.
  Round the disc it closes a share of the gap that grows with the gap, so while
  you move you are drawn a few columns ahead (about 5 at cruising speed, never
  more than a twentieth of a turn) and when you stop it drifts back onto you. In
  and out, in the three games that scroll that way, it closes 12% of the gap
  each tick, the pace of the prototype's 7% a frame at 60 frames a second.
- Things near the middle of the disc are hard to read, so the games with a deep
  level scroll inward with you and keep you toward the rim: Rim Runner keeps your
  feet about eight LEDs from the rim (but never shows more than 4 pixels of
  ground below the lowest floor), Spiral Tunnel flies a quarter of the way in, and
  Catch the Robots no deeper than halfway. They follow you to the very end of the
  level instead of stopping where the map runs out.
- Everything is made once in `build()` and moved afterwards: tiles come from one
  `bytearray` shared with the tilemap, sprites are fixed lists, and the walls get
  their outline from an autotile pass at build time. (Spiral Tunnel's edges are
  slanted tiles instead, like the prototype's, since the tunnel moves sideways as
  it goes down, and rocks are scattered through its walls at random so you can
  see them move.)
- Catch the Robots draws its maze as two tilemaps over the same cells, moved
  together: the dark fill, then the bright outlines over it. A `TUNNEL` layer
  can land several rows of a tile on one LED, and the last row drawn wins, so in
  a single tilemap the fill could hide a one-pixel outline.
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

- Controls are the controller's, not W A S D and L, and either controller plays:
  every game reads joy1 and joy2 alike.
- Rim Runner's platforms are four tiles above each other instead of five. A jump
  rises about 4.6 tiles, so the originals could not be reached from below.
- The tunnel and the maze are shorter, and the numbers (speeds, gravity) are
  scaled from the prototype's 60 frames a second to the console's 33 ticks.
- The prototype ends a level; here every game ends with its time and starts again
  on A.

## Art and sound

Art is generated, not drawn by hand: run `python3 tools/ld60_assets/make_art.py`
to rewrite every `images/tiles.png` and `images/sprites.png` (and Catch the
Robots' `images/outlines.png`), and
`python3 tools/ld60_assets/make_sounds.py` (needs ffmpeg) for the MP3s in
`sounds/`. In-game text is in the tutorial's `steel8x8.png`. The title and end
screens put their heading in the system's `rainbow8x8.png` and the lines below
it in the 4x6 `tinyfont_white.png`, with PRESS A in `tinyfont_red.png`.

Each `menu.png` is a moment of the game itself:
`python3 tools/ld60_assets/capture_menu_icons.py` plays every game headless from
a fixed seed and saves the 64 x 30 window round the player, drawn with the
game's own tiles and sprites. Spiral Tunnel's walls are further apart than the
icon is wide, so rows of empty tunnel are cut from between them. Run it again
after changing the art.
