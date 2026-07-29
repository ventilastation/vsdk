# API reference

Generated from the source in `apps/micropython/vs2`. If you are new to VS2,
read the [tutorial](../tutorial/index.md) first — this section assumes you know
what a layer and a sealed scene are.

Everything lives in two modules:

`vs2`
: Scenes, layers, drawables, and the `display`, `audio`, `base` and `limits`
  services.

`vs2.controls`
: The two controllers and the button constants, designed for
  `from vs2.controls import *`.

```{toctree}
:maxdepth: 2

scene
drawables
services
errors
```

## Cheat sheet

```python
import vs2
from vs2.controls import *

class MyGame(vs2.Scene):
    idle_timeout = 30          # seconds; None disables
    back_button = True         # Y / BACK pops the scene
    starfield = False          # drifting stars behind the scene

    def build(self):
        layer  = self.layer("world", projection=vs2.TUNNEL)
        sprite = layer.sprite("ship.png", x=128, y=16)
        pool   = layer.sprite_pool("shot.png", count=8, on_empty=vs2.RECYCLE)
        ground = layer.tilemap("terrain.png", columns=8, rows=17)
        score  = layer.label("digits.png", columns=5)

    def update(self):
        if joy1.held(LEFT):        ...   # level
        if joy1.just_pressed(A):   ...   # edge
        if joy1.just_released(B):  ...   # edge

    def teardown(self):
        ...                              # optional
```

| I want to | Use |
|---|---|
| Move something | `sprite.x` (angle, wraps), `sprite.y` (inward from the rim) |
| Animate | `sprite.frame` — independent of `visible` |
| Show or hide | `sprite.show()`, `sprite.hide()`, or a whole `layer.visible` |
| Fire a bullet | `pool.spawn(x, y)` → sprite or `None` |
| Retire a bullet | `pool.despawn(sprite)`, `pool.despawn_all()` |
| Hit-test | `a.overlaps(b)`, `a.first_overlap(pool)` |
| Scroll a map | `tilemap.view_x`, `tilemap.view_y` |
| Edit a map | `tilemap[col, row] = tile`, `tilemap.fill(tile)` |
| Show text | `label.text = "GAME OVER"`, `label.write(col, row, text)` |
| Show a score | `label.set_number(value, width=5)` |
| Leave a scene | `self.pop()`, `self.push(other)`, `self.switch(other)` |
| Run something later | `self.call_later(ms, callback, *args)` |
| Play audio | `vs2.audio.sound(name)`, `vs2.audio.music(name, loop=True)` |
| Know the display size | `vs2.display.width` (256), `vs2.display.height` (54) |
