# 4. Sprite pools

Bullets, enemies and explosions come and go. You cannot create them on the fly —
the scene is sealed — so you reserve them up front and cycle them:

```python
def build(self):
    world = self.layer("world", projection=vs2.TUNNEL)
    self.shots   = world.sprite_pool("shot.png", count=8)
    self.enemies = world.sprite_pool("enemy.png", count=16)
    self.booms   = world.sprite_pool("boom.png", count=4, on_empty=vs2.RECYCLE)
```

That is 28 of your 100 sprites, spent visibly in three numbers a reviewer can
add up. The old way — a hand-rolled pool class, or a flat list per entity type —
hid the total until the renderer ran out.

Every sprite starts hidden. Nothing after this allocates.

## Spawning

{py:meth}`~vs2.SpritePool.spawn` takes a free sprite, positions it, shows it,
and hands it back:

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
short, so pass `on_empty=vs2.RECYCLE` and an exhausted pool reuses its oldest
live sprite instead of returning `None`.

## Despawning and iterating

Iterating a pool yields only the live sprites, and despawning the current one
mid-loop is supported — which is exactly what the common loop needs:

```python
SHOT_SPEED = 6
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

Remember Y is depth on a `TUNNEL` layer, running 0 at the rim to 255 at the
centre — so a shot fired away from the player counts *up*, and the cutoff is a
depth you choose, not `vs2.display.height`.

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

Next: [tilemaps and text](tilemaps-and-text.md).
