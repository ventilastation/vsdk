# Scenes

A scene is one screen of a game. Subclass {py:class}`vs2.Scene`, build the
display graph in {py:meth}`~vs2.Scene.build`, and drive it in
{py:meth}`~vs2.Scene.update`.

## Lifecycle

`build()` runs on every entry, and when it returns the scene is **sealed**:

```text
   scene entered
        │
        ▼
   ┌──────────┐  build() returns   ┌────────┐
   │ building │ ─────────────────▶ │ sealed │ ◀─┐ update() and timers,
   └──────────┘                    └────────┘ ──┘ every tick
        ▲                               │
        │ entered again                 │ pop / push / switch / home
        │ (fresh build)                 ▼
        └───────────────────────── ┌────────┐
                                   │ closed │
                                   └────────┘
```

While *building*, layers and drawables may be created. Once *sealed*, they may
only be moved, re-framed, shown and hidden — any structural call raises
{py:exc}`vs2.SceneSealedError`. Once *closed*, drawables are released and
pending timers discarded, so a scene shown again always starts from a fresh
`build()`.

Persistent state can live in `__init__`, which runs once for the life of the
object. Drawable handles cannot: rebuild them in `build()`.

## Transitions

All three queue and commit at the end of the tick, and all three return `None`,
so `return self.pop()` reads as "handle this input, then stop":

```python
self.push(PauseMenu())        # suspend this scene, run another on top
self.pop()                    # resume the scene below, or exit the app
self.switch(GameOver(score))  # replace this scene outright
```

Once a transition is queued, no further game callbacks run that tick: if
`update()` queued it the timer drain is skipped, and if a timer callback queued
it the drain stops there. A timer coming due on the same tick as a game-over can
therefore never poke a scene that has already decided to leave. Only one
transition may be queued per tick; a second raises.

## Class reference

```{eval-rst}
.. autoclass:: vs2.Scene
   :members: idle_timeout, back_button, starfield, asset_pack,
             build, update, teardown, layer, image, call_later,
             push, pop, switch, on_idle
   :member-order: bysource
```
