# 4. Sprite pools

Enemies, bonuses and sparks come and go. You cannot create them on the fly —
the scene is {term}`sealed` — so you reserve a {term}`pool` of them up front and
cycle through it.

The reason is the hardware. Every new object takes memory from MicroPython's
heap, and when a sprite is thrown away, its memory stays in use until the
{term}`garbage collector <garbage collection>` finds it. The ESP32-S3 has a
modest CPU and little memory, so a collection is slow, and it stops your game
while it runs. A game that makes a sprite for every enemy would be producing
garbage all the time and would hit those pauses in the middle of play. A pool
makes the sprites once, in `build()`, and then lends them out and takes them
back, so spawning an enemy allocates nothing:

```python
def build(self):
    world = self.layer("world", projection=vs2.TUNNEL)
    self.enemies = world.sprite_pool("enemy.png", count=16)
```

That is 16 of your 100 sprites, spent in one number you can add up.

Every sprite starts hidden. Nothing after this allocates.

## Spawning

{term}`Spawning <spawn>` with {py:meth}`~vs2.SpritePool.spawn` takes a free
sprite, positions it, shows it, and hands it back:

```python
enemy = self.enemies.spawn(x=100, y=160)
```

When the pool is empty it returns `None`, because "no free enemy this time" is a
game rule, not an error:

```python
enemy = self.enemies.spawn(x=..., y=...)
if enemy is None:
    return          # the tunnel is already full; skip this one
```

For sparks and particles, dropping one looks worse than cutting another short,
so pass `on_empty=vs2.RECYCLE` when you create the pool, for example
`world.sprite_pool("spark.png", count=32, on_empty=vs2.RECYCLE)`, and an exhausted
pool will {term}`recycle` its oldest live sprite instead of returning `None`.

## Despawning and iterating

Iterating a pool yields only the live sprites, and despawning the current one
mid-loop is supported — which is exactly what the common loop needs:

```python
ENEMY_SPEED = 0.5

def update(self):
    for enemy in self.enemies:
        enemy.y -= ENEMY_SPEED                 # toward the player, at the rim
        if enemy.y < -enemy.image.height:
            self.enemies.despawn(enemy)        # gone past the rim: retire it
```

On a `TUNNEL` layer the rim is `y = 0`, so something coming toward the player
counts *down* in Y, and the cutoff is a depth you choose — see
[the circular display](display.md).

```{figure} ../images/pools.png
:alt: Seven enemies spread through the tunnel at different depths and angles, with a ship on the rim at the top
:width: 60%
:align: center

Seven enemies spawned from a pool, at different depths, heading for the ship.
```

{py:meth}`~vs2.SpritePool.despawn_all` clears a pool in one call, which is the
usual way to reset a level:

```python
def start_wave(self, n):
    self.enemies.despawn_all()
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

Time for something to dodge. Add a pool of enemies to `build()`, with a few of
them already spawned (a timer will spawn them properly in chapter 6):

```python
ENEMY_SPEED = 0.5    # depth units per tick, toward the ship
ENEMY_START = 160    # depth at which enemies appear


def build(self):
    # ... the layer and the ship, as before ...
    self.enemies = self.world.sprite_pool("enemy.png", count=16)
    for i in range(5):
        self.enemies.spawn(x=i * 51, y=ENEMY_START)
    self.ticks = 0                              # counts update() calls
```

Then `update()` moves them:

```python
def update(self):
    self.ticks += 1
    # ... steering, as before ...
    self.move_enemies()

def move_enemies(self):
    for enemy in self.enemies:
        enemy.y -= ENEMY_SPEED
        enemy.frame = (self.ticks // 6) % enemy.image.frames
        if enemy.y < -enemy.image.height:
            self.enemies.despawn(enemy)      # flew past the ship
```

Enemies move *toward* the ship by counting `y` **down**, because the ship is at
the rim. `update()` runs once per rotation, so to animate at a pace you can see,
count the calls and change frame every few of them instead of on every one:
`self.ticks // 6` stays the same for six ticks in a row, so the enemy changes frame
six times more slowly than `update()` runs. `enemy.image.frames` supplies the
number of frames, so the line keeps working if you add one to the PNG. Each enemy cycles through the six frames of `enemy.png`. For
now an enemy that reaches the ship simply flies through it; chapter 6 makes that
end the game, and chapter 5 scores the ones you avoid.

Next: [tilemaps and text](tilemaps-and-text.md).
