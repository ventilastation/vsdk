# Display, input, audio and base

Four module-level singletons, plus the button constants in `vs2.controls`.

## vs2.display

Display geometry and palette animation.

```{eval-rst}
.. autoattribute:: vs2.display.width
.. autoattribute:: vs2.display.height
```

On the rotor target `width` is 256 and `height` is 54, but read them rather than
hard-coding: both come from the same generated target definition the renderer
uses, so a future display variant gets them right for free.

`height` is the LED count, which is the Y range of a {py:data}`vs2.HUD` layer.
A {py:data}`vs2.TUNNEL` layer's Y is depth and runs to 255 — see
[the circular display](../tutorial/display.md).

```python
x = (x + 1) % vs2.display.width      # wrap the angle
hud_label.y = 1                      # near the rim, where text is legible
```

### Palette animation

Recolouring the loaded palette is the cheapest effect a POV display has: one
buffer write tints every sprite drawn from that palette group.

```{eval-rst}
.. py:attribute:: vs2.display.palettes

   The loaded palette block, as a mutable buffer, or ``None``.

   This is the same buffer the asset bank loaded, so recolouring in place
   allocates nothing. Call :meth:`vs2.display.apply_palettes` to publish the
   change. The buffer is replaced whenever a new asset pack loads, so resolve
   it in :meth:`vs2.Scene.build` like any other asset handle.

.. automethod:: vs2.display.apply_palettes
```

## vs2.controls

```{eval-rst}
.. automodule:: vs2.controls
   :no-members:
```

### Reading a controller

`joy1` and `joy2` are the two controllers, named after the wire protocol's
fields. Both have the same three methods; they are documented here on `joy1`.

```{eval-rst}
.. automethod:: vs2.controls.joy1.held
.. automethod:: vs2.controls.joy1.just_pressed
.. automethod:: vs2.controls.joy1.just_released
```

`held` is a level — the button is down right now. `just_pressed` and
`just_released` are edges, true for the single tick the transition happened on.
Movement usually reads levels; fire, confirm and menu-stepping read edges.

### Buttons

```{eval-rst}
.. autodata:: vs2.controls.LEFT
   :no-value:
.. autodata:: vs2.controls.RIGHT
   :no-value:
.. autodata:: vs2.controls.UP
   :no-value:
.. autodata:: vs2.controls.DOWN
   :no-value:
.. autodata:: vs2.controls.A
   :no-value:
.. autodata:: vs2.controls.B
   :no-value:
.. autodata:: vs2.controls.X
   :no-value:
.. autodata:: vs2.controls.Y
   :no-value:
.. autodata:: vs2.controls.START
   :no-value:
.. autodata:: vs2.controls.BACK
   :no-value:
```

### idle_ms

`vs2.controls.idle_ms` is milliseconds since any controller was last touched. It
re-evaluates on every use and behaves like an integer, so it compares and does
arithmetic directly:

```python
if vs2.controls.idle_ms > 5000:
    self.dim_the_hud()
```

It is deliberately left out of `__all__`, so a star import does not bring it in.
Most games want {py:attr}`Scene.idle_timeout <vs2.Scene.idle_timeout>` and
{py:meth}`Scene.on_idle <vs2.Scene.on_idle>` instead.

## vs2.audio

```{eval-rst}
.. automethod:: vs2.audio.sound
.. automethod:: vs2.audio.music
.. automethod:: vs2.audio.stop_music
.. automethod:: vs2.audio.notes
```

Names resolve against the current game's `sounds/` folder. A name containing `/`
is already qualified and used as-is, which is how a game borrows another's
audio:

```python
vs2.audio.sound("shoot")                  # this game's shoot.mp3
vs2.audio.sound("alecu.vyruss/shoot1")    # another game's
```

Music follows the app, not the scene: a track keeps playing across `push`,
`pop` and `switch` within the same game, and stops when the game returns to the
launcher.

## vs2.base

Console base hardware — the RGB strip, the servo and the lit buttons. Values are
range-checked and de-duplicated, so writing the same colour every tick costs one
comparison and sends nothing. All of it is safe on a console with no physical
base attached.

```python
vs2.base.leds.set_all(255, 0, 0)
vs2.base.servo.set(128)
vs2.base.buttons.set(vs2.base.BUTTON_LED_ALL, blink_ms=250)
```

```{eval-rst}
.. automethod:: vs2.base.leds.set_all
.. automethod:: vs2.base.leds.off
.. automethod:: vs2.base.servo.set
.. automethod:: vs2.base.buttons.set
.. automethod:: vs2.base.buttons.off
.. autoattribute:: vs2.base.BUTTON_LED_1
.. autoattribute:: vs2.base.BUTTON_LED_2
.. autoattribute:: vs2.base.BUTTON_LED_ALL
```

Base output follows the app, not the scene: LED, servo and button-light state
persists across scene transitions within a game and resets to safe defaults when
the game returns to the launcher.

## vs2.limits

The per-target resource budgets, readable at runtime.

```{eval-rst}
.. autoattribute:: vs2.limits.layers
.. autoattribute:: vs2.limits.sprites
.. autoattribute:: vs2.limits.tilemaps
.. autoattribute:: vs2.limits.image_strips
```

| Resource | Budget on the rotor |
|---|---|
| `layers` | 8 |
| `sprites` | 100 |
| `tilemaps` | 16 (a label counts as one) |
| `image_strips` | 100 |

Exceeding one raises {py:exc}`vs2.ResourceLimitError` during `build()`, the
first time the scene is entered.
