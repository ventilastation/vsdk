# 4. Sprite pools

Bullets, enemies and explosions come and go. You cannot create them on the fly —
the scene is {term}`sealed` — so you reserve a {term}`pool` of them up front and
cycle through it:

```python
def build(self):
    world = self.layer("world", projection=vs2.TUNNEL)
    self.shots   = world.sprite_pool("shots.png", count=8)
    self.enemies = world.sprite_pool("enemy.png", count=16)
    self.booms   = world.sprite_pool("explosion.png", count=4, on_empty=vs2.RECYCLE)
```

That is 28 of your 100 sprites, spent in three numbers you can add up.

Every sprite starts hidden. Nothing after this allocates.

## Spawning

{term}`Spawning <spawn>` with {py:meth}`~vs2.SpritePool.spawn` takes a free
sprite, positions it, shows it, and hands it back:

```python
if joy1.just_pressed(A):
    shot = self.shots.spawn(x=self.ship.x, y=self.ship.y + 4)
```

When the pool is empty it returns `None`, because "no free bullet this frame" is
a game rule, not an error:

```python
shot = self.shots.spawn(x=..., y=...)
if shot is None:
    return          # player is already firing as fast as they may
```

For explosions and particles, dropping one looks worse than cutting another
short, so pass `on_empty=vs2.RECYCLE` and an exhausted pool will {term}`recycle`
its oldest live sprite instead of returning `None`.

## Despawning and iterating

Iterating a pool yields only the live sprites, and despawning the current one
mid-loop is supported — which is exactly what the common loop needs:

```python
SHOT_SPEED = 3
SHOT_RANGE = 170          # depth at which a shot has gone too far to matter

def update(self):
    for shot in self.shots:
        shot.y += SHOT_SPEED          # away from the player, down the tunnel
        if shot.y > SHOT_RANGE:
            self.shots.despawn(shot)
            continue

        enemy = shot.first_overlap(self.enemies)
        if enemy:
            self.enemies.despawn(enemy)
            self.booms.spawn(x=enemy.x, y=enemy.y)
            self.shots.despawn(shot)
```

On a `TUNNEL` layer a shot fired away from the player counts *up* in Y, and the
cutoff is a depth you choose — see [the circular display](display.md).

```{figure} ../images/pools.png
:alt: A row of enemies near the centre, a shot flying toward them and a small explosion where one enemy was hit
:width: 60%
:align: center

Seven enemies spawned from a pool, a shot in flight, and the explosion left by a hit.
```

{py:meth}`~vs2.SpritePool.despawn_all` clears a pool in one call, which is the
usual way to reset a level:

```python
def start_wave(self, n):
    self.enemies.despawn_all()
    self.shots.despawn_all()
    ...
```

## Counting

```python
len(self.enemies)        # live count
self.enemies.free        # how many are left to spawn

if not len(self.enemies):
    self.next_wave()
```

Both are O(1).

## What the errors mean

Despawning a sprite twice, or handing a pool a sprite from a different pool,
raises:

```text
ValueError: sprite is not live in this pool
```

That is always a bookkeeping bug — usually a sprite despawned in two branches of
the same `if`. It is worth failing on, because the alternative is a sprite that
is quietly in both the free list and the live list.

## In the game

Time to shoot things. Add three pools to `build()`, and a few enemies to shoot
at (a timer will spawn them properly in chapter 6):

```python
SHOT_SPEED = 3       # depth units per tick, away from the ship
SHOT_RANGE = 170     # depth at which a shot has gone too far to matter
ENEMY_SPEED = 0.5    # depth units per tick, toward the ship
ENEMY_START = 160    # depth at which enemies appear
BOOM_TICKS = 3       # ticks each explosion frame stays on screen


def build(self):
    # ... the layer and the ship, as before ...
    self.shots = self.world.sprite_pool("shots.png", count=8)
    self.enemies = self.world.sprite_pool("enemy.png", count=16)
    self.booms = self.world.sprite_pool("explosion.png", count=4,
                                        on_empty=vs2.RECYCLE)
    for i in range(5):
        self.enemies.spawn(x=i * 51, y=ENEMY_START)
```

Then `update()` fires with the A button and moves everything:

```python
def update(self):
    # ... steering and the ship's animation, as before ...
    if joy1.just_pressed(A):
        self.fire()

    self.move_shots()
    self.move_enemies()
    self.animate_booms()

def fire(self):
    # Centre the 6-column shot on the 18-column ship.
    self.shots.spawn(x=self.ship.x + 6, y=self.ship.y + 4)

def move_shots(self):
    for shot in self.shots:
        shot.y += SHOT_SPEED
        if shot.y > SHOT_RANGE:
            self.shots.despawn(shot)
            continue

        enemy = shot.first_overlap(self.enemies)
        if enemy:
            self.enemies.despawn(enemy)
            boom = self.booms.spawn(x=enemy.x, y=enemy.y)
            boom.frame = 0
            self.shots.despawn(shot)

def move_enemies(self):
    """Advance the enemies. Returns True if one touched the ship."""
    for enemy in self.enemies:
        enemy.y -= ENEMY_SPEED
        enemy.frame = (self.ticks // 6) % enemy.image.frames
        if enemy.overlaps(self.ship):
            return True
        if enemy.y < -enemy.image.height:
            self.enemies.despawn(enemy)      # flew past the ship
    return False

def animate_booms(self):
    if self.ticks % BOOM_TICKS:
        return
    for boom in self.booms:
        if boom.frame >= boom.image.frames - 1:
            self.booms.despawn(boom)         # the animation has played out
        else:
            boom.frame += 1
```

Three things to notice. Enemies move *toward* the ship by counting `y` **down**,
because the ship is at the rim. `boom.frame = 0` restarts an explosion that was
recycled from an older one. And `move_enemies()` reports a hit by returning
`True`; nothing uses that yet, and chapter 6 ends the game with it.

Next: [tilemaps and text](tilemaps-and-text.md).
