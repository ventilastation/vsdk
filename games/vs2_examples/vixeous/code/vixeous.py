"""Vixeous: hand-written game logic.

Created once by tools/vs2_scene_gen.regenerate.ensure_companion_stub --
never touched by a later regenerate_all() pass. Edit this file freely;
it is yours from the moment it is created.

This is the T15 "scene editor / build() generator" proving case: a port of
games/alecu/vixeous/code/vixeous.py where the declarative object graph
(the sprites, pools and behaviors created in build()) now lives in
vixeous_scene.vs2model.json and is generated into vixeous_scene.py by
tools/vs2_scene_gen. Everything with control flow -- input, collision,
scoring, terrain scroll, the boss fight -- stays hand-written here, exactly
as vixeous.py's own update() always was; see this task's report for the
handful of Behavior-catalog mismatches this port ran into (Patrolling's
bipolar wave doesn't match the enemy phase ramp, Animated.bank rejects a
Var binding, Projectile despawns unconditionally on any overlap) and why
each one stayed hand-written instead.

**Updated 2026-09-14**: the boss's own theta/phase orbit motion and its
bounded approach toward BOSS_STOP_Y is now BossOrbit, a real generated
Behavior (build_boss_orbit.py). See that module's own docstring for two
more real, previously-undiscovered Behavior-catalog mismatches found
while scoping this: the enemies pool's own near-identical phase/theta
oscillation turns out not to be portable at all (a SpritePool.var()/
Behavior-state name collision), and boss.frame's own banking couldn't
move either (Animate's shared clock never advances for a lone-sprite
subject). update_entities() still drives camera-dependent x reprojection
and frame banking for everything (enemies/boss alike), plus the enemies
pool's own phase/theta motion, all hand-written as before.

**Updated 2026-09-14 (again)**: BossOrbit is now attached declaratively
in vixeous_scene.vs2model.json itself (the "boss" drawable's own
``behaviors``, naming a ``module`` outside ``vs2.behaviors``) instead of
by hand in an ``on_build_9`` override -- tools/vs2_scene_gen's generator
used to hardcode ``from vs2.behaviors import <classes>``, the one real
gap that forced every game-local generated Behavior through a hook. This
file no longer overrides any ``on_build_N`` hook at all.
"""

from urandom import randrange, seed
import utime

import vs2
from vs2.controls import A, B, DOWN, LEFT, RIGHT, UP, joy1

from games.vs2_examples.vixeous.code import vixeous_scene

PLAYER_START_Y = 6
PLAYER_MIN_Y = 0
PLAYER_MAX_Y = 40
PLAYER_Y_SPEED = 2
PLAYER_SIDE_LIMIT = 32
PLAYER_SIDE_SPEED = 4
TERRAIN_COLS = 8
TERRAIN_ROWS = 8
TERRAIN_TILE_W = 32
TERRAIN_TILE_H = 16
TERRAIN_NEAR_Y = 0
TERRAIN_SCROLL_TICKS = 3
TERRAIN_BUFFER_ROWS = TERRAIN_ROWS + 1
TERRAIN_VIEW_H = TERRAIN_ROWS * TERRAIN_TILE_H
MAX_SHOTS, MAX_BOMBS, MAX_ENEMIES, MAX_TARGETS, MAX_EXPLOSIONS = 4, 3, 6, 5, 5
SHOT_SPEED, BOMB_SPEED, ENEMY_SPEED = 8, 4, 1
RETICLE_DISTANCE = 66
ENEMY_START_Y = 164
TARGET_START_Y = 158
BOSS_START_Y = 143
BOSS_STOP_Y = 107
SHOT_FAR_Y = 179
STATE_READY, STATE_PLAYING, STATE_AREA_CLEAR, STATE_GAME_OVER = range(4)


def angle_delta(left, right):
    return ((left - right + vs2.display.width // 2) % vs2.display.width) - vs2.display.width // 2


def centered_x(theta, width):
    return (theta - width // 2) % vs2.display.width


def screen_x(world_theta, camera_theta, width):
    return centered_x(world_theta - camera_theta, width)


def terrain_river_center(row, area):
    return (row // 3 + area * 2) % TERRAIN_COLS


def terrain_frame_for(col, row, area):
    river = terrain_river_center(row, area)
    delta = min(abs(col - river), TERRAIN_COLS - abs(col - river))
    next_river = terrain_river_center(row + 3, area)
    next_delta = min(abs(col - next_river), TERRAIN_COLS - abs(col - next_river))
    if delta == 0:
        return (row + col) & 1
    if delta == 1 and next_delta == 0:
        return 8 + ((row + col) & 1)
    if delta == 1:
        return 2 + ((row + col) & 1)
    if delta == 2 and next_delta <= 1:
        return 10 + ((row + col) & 1)
    if delta == 2:
        return 4 + ((row + col) & 1)
    if delta == 3 and next_delta == 2:
        return 12
    if delta == 3:
        return 6 + ((row + col + area) & 1)
    if row % 13 == 0 and col in (0, 4):
        return 14
    if row % 17 == 4 and col in (3, 7):
        return 15
    return 6 + ((row + col + area) & 1)


def terrain_is_water(col, row, area):
    river = terrain_river_center(row, area)
    delta = min(abs(col - river), TERRAIN_COLS - abs(col - river))
    return delta == 0


def terrain_is_shore(col, row, area):
    river = terrain_river_center(row, area)
    delta = min(abs(col - river), TERRAIN_COLS - abs(col - river))
    return delta in (1, 2)


def terrain_is_pad(col, row):
    return ((row % 13 == 0 and col in (0, 4))
            or (row % 17 == 4 and col in (3, 7)))


def terrain_theta_for(col, row, area):
    return (col * TERRAIN_TILE_W + area * 13) % vs2.display.width


def is_targetable_terrain(col, row, area):
    return (not terrain_is_water(col, row, area)
            and (terrain_is_shore(col, row, area)
                 or terrain_is_pad(col, row)))


class ScoreBoard:
    """Thin wrapper around the model-declared ``score_label`` -- unlike the
    original, this does not create the label itself (the generator's
    build() already did, per the model), it only centers it and exposes
    the digit-writing helpers."""

    def __init__(self, label):
        self.label = label
        label_width = self.label.columns * self.label.image.width
        self.label.x = (vs2.display.width - label_width) // 2

    def set_score(self, value):
        self.label.set_number(max(0, min(value, 99999)), width=5, pad="0")

    def set_lives(self, lives):
        self.label.write(6, 0, "***"[:max(0, min(lives, 3))], pad=True)


class Vixeous(vixeous_scene.VixeousScene):
    def __init__(self):
        vixeous_scene.VixeousScene.__init__(self)
        seed(utime.ticks_ms())

    # -- build()-time hooks -------------------------------------------------
    # build() itself (layers, pools, sprites, behaviors) is entirely
    # generated from vixeous_scene.vs2model.json; these numbered hooks are
    # where this hand-written subclass does the post-construction work that
    # format can't express -- initial scene state, and the two labels/
    # sprites whose position depends on their own just-built width.

    def on_build_0(self):
        # Right after the layers exist, before the first drawable -- same
        # place the original build() set this bookkeeping, before it went
        # on to create the terrain tilemap.
        self.state = STATE_READY
        self.frame = self.camera_theta = self.player_offset = self.depth = self.area = 0
        self.player_y, self.score, self.lives = PLAYER_START_Y, 0, 3
        self.invulnerable, self.scroll_tick, self.next_wave, self.next_target_row = 0, 0, 45, 8
        self.boss_started = self.boss_defeated = False
        self.terrain_base_row = self.terrain_area = None

    def on_build_10(self):
        # Right after score_label, before message.
        self.scoreboard = ScoreBoard(self.score_label)
        self.scoreboard.set_score(0)
        self.scoreboard.set_lives(self.lives)

    def on_build_11(self):
        # The last hook: right after message, before build() returns.
        self.message.x = centered_x(0, self.message.width)
        self.update_terrain()
        self.animate_player()
        vs2.audio.music("flight", loop=True)
        self.call_later(1200, self.start_playing)

    # -- game logic (unchanged from the original, adapted to read the
    # generated build()'s attributes instead of constructing them) --------

    def start_playing(self):
        if self.state == STATE_READY:
            self.message.hide()
            self.state = STATE_PLAYING

    def update_terrain(self):
        base_row = self.depth // TERRAIN_TILE_H
        if base_row != self.terrain_base_row or self.area != self.terrain_area:
            self.terrain_base_row, self.terrain_area = base_row, self.area
            for row in range(TERRAIN_BUFFER_ROWS):
                for col in range(TERRAIN_COLS):
                    self.terrain[col, row] = terrain_frame_for(col, base_row + row, self.area)
        self.terrain.x = (self.area * 13 - self.camera_theta - TERRAIN_TILE_W // 2) % vs2.display.width
        self.terrain.view_y = self.depth % TERRAIN_TILE_H

    def player_theta(self):
        return (self.camera_theta + self.player_offset) % vs2.display.width

    def aim_y(self):
        return self.player_y + RETICLE_DISTANCE

    def add_score(self, amount):
        self.score += amount
        self.scoreboard.set_score(self.score)

    def burst(self, theta, y, start_frame=0):
        # Transient(animate=True, ticks=18) now drives explosion.frame for
        # its whole lifetime once spawned, so this no longer sets a frame
        # or an "age" counter itself -- see this task's report: Transient's
        # own state (transient_elapsed) is not reset by spawn() on a
        # RECYCLE pool (a known upstream gap in vs2/behaviors.py, not
        # something this port works around), and Transient exposes no
        # per-spawn "start partway through" hook the way the original's
        # own start_frame/age trick did. The satellite bursts in
        # target_burst() below are therefore visually plainer than the
        # original (all three start from frame 0) -- a real, noted,
        # divergence, not an oversight.
        sprite = self.explosions.spawn(screen_x(theta, self.camera_theta, 20), y)
        if sprite is not None:
            sprite.theta = theta % vs2.display.width
        vs2.audio.sound("boom")

    def target_burst(self, theta, y):
        self.burst(theta, y)
        for offset in (-7, 7):
            sprite = self.explosions.spawn(
                screen_x(theta + offset, self.camera_theta, 20),
                y + (-3 if offset > 0 else 3))
            if sprite is not None:
                sprite.theta = (theta + offset) % vs2.display.width

    def spawn_wave(self):
        base = (self.camera_theta + 44 + randrange(168)) % vs2.display.width
        for number in range(3 + self.area % 2):
            enemy = self.enemies.spawn(
                0, ENEMY_START_Y + number * 7,
                frame=(self.area + number) % 3 * 2,
            )
            if enemy is not None:
                enemy.theta = (base + number * 22) % vs2.display.width
                enemy.kind = (self.area + number) % 3
                enemy.phase = randrange(64)
                enemy.hp = 1 + (1 if enemy.kind == 2 else 0)
        self.next_wave = 70 + randrange(45)

    def spawn_target_if_needed(self):
        row = self.depth // TERRAIN_TILE_H
        if row < self.next_target_row:
            return
        target_row = row + TERRAIN_ROWS + 1
        pad_cols = [
            col for col in range(TERRAIN_COLS)
            if terrain_is_pad(col, target_row)
        ]
        columns = pad_cols or [
            col for col in range(TERRAIN_COLS)
            if is_targetable_terrain(col, target_row, self.area)
        ]
        col = columns[randrange(len(columns))] if columns else randrange(TERRAIN_COLS)
        theta = terrain_theta_for(col, target_row, self.area)
        kind = 3 if col in pad_cols else randrange(3)
        target = self.targets.spawn(
            screen_x(theta, self.camera_theta, 14), TARGET_START_Y, frame=kind)
        if target is not None:
            target.theta, target.kind = theta, kind
        self.next_target_row = row + 5 + randrange(4)

    def maybe_start_boss(self):
        if self.boss_started or self.depth <= 900 or self.score < 120:
            return
        self.boss_started = True
        self.boss.theta = self.camera_theta
        self.boss.y = BOSS_START_Y
        self.boss.hp = 18
        self.boss.phase = 0
        self.boss.frame = 0
        self.boss.show()
        vs2.audio.music("boss")

    def update_turning(self, turn):
        if turn:
            desired = self.player_offset + turn * PLAYER_SIDE_SPEED
            if desired > PLAYER_SIDE_LIMIT:
                self.camera_theta = (
                    self.camera_theta + desired - PLAYER_SIDE_LIMIT
                ) % vs2.display.width
                desired = PLAYER_SIDE_LIMIT
            elif desired < -PLAYER_SIDE_LIMIT:
                self.camera_theta = (
                    self.camera_theta + desired + PLAYER_SIDE_LIMIT
                ) % vs2.display.width
                desired = -PLAYER_SIDE_LIMIT
            self.player_offset = desired

        if self.player_offset:
            distance = abs(self.player_offset)
            if turn and distance > PLAYER_SIDE_LIMIT * 3 // 4:
                follow = 4
            elif turn and distance > PLAYER_SIDE_LIMIT // 2:
                follow = 2
            else:
                follow = 1
            follow = min(follow, distance)
            direction = 1 if self.player_offset > 0 else -1
            self.camera_theta = (
                self.camera_theta + direction * follow
            ) % vs2.display.width
            self.player_offset -= direction * follow

    def process_input(self):
        turn = (1 if joy1.held(LEFT) else 0) - (1 if joy1.held(RIGHT) else 0)
        self.update_turning(turn)
        if joy1.held(UP):
            self.player_y = min(PLAYER_MAX_Y, self.player_y + PLAYER_Y_SPEED)
        if joy1.held(DOWN):
            self.player_y = max(PLAYER_MIN_Y, self.player_y - PLAYER_Y_SPEED)
        if joy1.just_pressed(A):
            shot = self.shots.spawn(0, self.player_y + 12, frame=0)
            if shot is not None:
                shot.theta = self.player_theta()
                vs2.audio.sound("shoot")
        if joy1.just_pressed(B):
            bomb = self.bombs.spawn(0, self.player_y + 6, frame=1)
            if bomb is not None:
                bomb.theta = self.player_theta()
                vs2.audio.sound("bomb")

    def update_targets(self, dy):
        for target in self.targets:
            target.y -= dy
            if target.y < 0:
                self.targets.despawn(target)
            else:
                target.x = screen_x(
                    target.theta, self.camera_theta, target.width)

    def update_entities(self):
        # shots/bombs/enemies' y now moves via the model's Moving behaviors
        # (committed once, scene-wide, after this update() returns -- see
        # vs2.Scene._run_behaviors), and DespawnBeyond retires shots/enemies
        # that cross their bound. Both check the position as of the start
        # of this tick, one tick behind the original's "move then check"
        # order in the same pass -- a real, minor timing difference from a
        # hand-inlined loop, not a bug. This method now only reprojects
        # each still-live sprite's screen x from its own theta (the camera
        # rotates every tick; nothing in the Behavior catalog knows about
        # that reprojection) and drives the parts a Behavior genuinely
        # cannot: enemy theta motion/frame banking (see this module's own
        # docstring for why the enemies pool itself isn't similarly
        # ported -- a real SpritePool.var()/Behavior-state collision, not
        # attempted), and the boss's own frame banking.
        #
        # The boss's theta/phase motion and its bounded approach toward
        # BOSS_STOP_Y are BossOrbit now (attached declaratively in
        # vixeous_scene.vs2model.json) -- it
        # ticks unconditionally every scene tick, including while
        # self.boss is still hidden, harmlessly: maybe_start_boss() resets
        # theta/phase/y fresh the moment the boss actually activates, so
        # whatever it accumulated while hidden is always overwritten
        # before anything reads it. See boss_orbit.py's own module
        # docstring for why frame banking couldn't move too (a second,
        # different Behavior-catalog mismatch: Animate's clock never
        # advances for a lone-sprite subject).
        for shot in self.shots:
            shot.x = screen_x(shot.theta, self.camera_theta, shot.width)
        for bomb in self.bombs:
            bomb.x = screen_x(bomb.theta, self.camera_theta, bomb.width)
        for enemy in self.enemies:
            enemy.phase = (enemy.phase + 1) % 128
            enemy.theta = (enemy.theta + (2 if enemy.phase < 64 else -2)) % vs2.display.width
            enemy.x = screen_x(enemy.theta, self.camera_theta, enemy.width)
            enemy.frame = enemy.kind * 2 + ((enemy.phase // 8) & 1)
        if self.boss.visible:
            self.boss.x = screen_x(
                self.boss.theta, self.camera_theta, self.boss.width)
            self.boss.frame = (self.boss.phase // 8) & 1
        for explosion in self.explosions:
            explosion.x = screen_x(explosion.theta, self.camera_theta, explosion.width)

    def damage_player(self):
        if self.invulnerable:
            return
        self.lives -= 1
        self.scoreboard.set_lives(self.lives)
        self.invulnerable = 60
        vs2.audio.sound("hit")
        if self.lives <= 0:
            self.game_over()

    def game_over(self):
        self.state = STATE_GAME_OVER
        self.message.frame = 2
        self.message.y = 12
        self.message.show()
        vs2.audio.music("gameover")
        self.call_later(3500, self.pop)

    def area_clear(self):
        self.state = STATE_AREA_CLEAR
        self.area += 1
        self.boss_defeated = True
        self.message.frame = 1
        self.message.y = 12
        self.message.show()
        vs2.audio.sound("area")
        self.call_later(2500, self.resume_next_area)

    def resume_next_area(self):
        if self.state != STATE_AREA_CLEAR:
            return
        self.message.hide()
        self.next_wave = 35
        self.next_target_row = self.depth // TERRAIN_TILE_H + 4
        self.boss_started = self.boss_defeated = False
        self.state = STATE_PLAYING
        vs2.audio.music("flight", loop=True)

    def check_shot_hits(self):
        for shot in self.shots:
            if self.boss.visible and (
                    abs(angle_delta(shot.theta, self.boss.theta)) < 22
                    and abs(shot.y - self.boss.y) < 18):
                self.shots.despawn(shot)
                self.boss.hp -= 1
                vs2.audio.sound("hit")
                if self.boss.hp <= 0:
                    theta, y = self.boss.theta, self.boss.y
                    self.boss.hide()
                    self.burst(theta, y)
                    self.add_score(500)
                    self.area_clear()
                continue
            for enemy in self.enemies:
                if (abs(angle_delta(shot.theta, enemy.theta)) < 12
                        and abs(shot.y - enemy.y) < 12):
                    self.shots.despawn(shot)
                    enemy.hp -= 1
                    if enemy.hp <= 0:
                        self.enemies.despawn(enemy)
                        self.burst(enemy.theta, enemy.y)
                        self.add_score(40)
                    break

    def check_bomb_hits(self):
        aim_y = self.aim_y()
        for bomb in self.bombs:
            if bomb.y < aim_y:
                continue
            hit = None
            for target in self.targets:
                if (abs(angle_delta(bomb.theta, target.theta)) < 20
                        and abs(target.y - aim_y) < 24):
                    hit = target
                    break
            self.bombs.despawn(bomb)
            if hit is not None:
                theta, y, kind = hit.theta, hit.y, hit.kind
                self.targets.despawn(hit)
                self.target_burst(theta, y)
                self.add_score(120 if kind == 3 else 70)
            else:
                self.burst(bomb.theta, aim_y)

    def check_player_hits(self):
        if self.state != STATE_PLAYING:
            return
        theta = self.player_theta()
        for enemy in self.enemies:
            if (enemy.y < self.player_y + 18
                    and abs(angle_delta(enemy.theta, theta)) < 15):
                enemy_theta, enemy_y = enemy.theta, enemy.y
                self.enemies.despawn(enemy)
                self.burst(enemy_theta, enemy_y)
                self.damage_player()
                return
        if (self.boss.visible and self.boss.y < self.player_y + 42
                and abs(angle_delta(self.boss.theta, theta)) < 24):
            self.damage_player()

    def animate_player(self):
        self.player.x = centered_x(self.player_offset, self.player.width)
        self.player.y = self.player_y
        self.player.frame = (self.frame // 5) % self.player.image.frames
        if self.invulnerable:
            self.invulnerable -= 1
            if self.invulnerable & 2:
                self.player.hide()
                return
        self.player.show()

    def update(self):
        self.frame = (self.frame + 1) % 10000
        dy = 0
        if self.state in (STATE_READY, STATE_PLAYING):
            self.process_input()
        if self.state == STATE_PLAYING:
            self.scroll_tick = (
                self.scroll_tick + 1
            ) % TERRAIN_SCROLL_TICKS
            if self.scroll_tick == 0:
                dy = 1
            self.depth += dy
            self.next_wave -= 1
            self.spawn_target_if_needed()
            if self.next_wave <= 0 and not self.boss.visible:
                self.spawn_wave()
            self.maybe_start_boss()

        aim_y = self.aim_y()
        bomb_near_target = any(
            bomb.y >= aim_y - 12 for bomb in self.bombs)
        self.reticle.frame = (
            (1 if bomb_near_target else 0) + self.area % 2)
        self.reticle.x = centered_x(self.player_offset, self.reticle.width)
        self.reticle.y = aim_y
        self.update_terrain()
        self.update_targets(dy)
        self.update_entities()
        self.check_shot_hits()
        self.check_bomb_hits()
        self.check_player_hits()
        self.animate_player()


def main():
    return Vixeous()
