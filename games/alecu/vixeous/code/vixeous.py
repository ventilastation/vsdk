"""Vixeous, migrated to sealed V2 layers, pools, labels and tilemaps."""

from urandom import randrange, seed
import utime

import vs2
from vs2.controls import A, B, DOWN, LEFT, RIGHT, UP, joy1


PLAYER_START_Y = 22
PLAYER_MIN_Y = 12
PLAYER_MAX_Y = 54
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
RETICLE_DISTANCE = 62
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
    def __init__(self, layer):
        # The label sits at the top of the disc. Flip the complete tilemap so
        # the source TinyFont strip stays reusable in its ordinary orientation.
        self.label = layer.label(
            "digits.png", columns=9, x=0, y=1,
            flip_x=True, flip_y=True)
        label_width = self.label.columns * self.label.image.width
        self.label.x = (
            vs2.display.width - label_width
        ) // 2

    def set_score(self, value):
        self.label.set_number(max(0, min(value, 99999)), width=5, pad="0")

    def set_lives(self, lives):
        self.label.write(6, 0, "***"[:max(0, min(lives, 3))], pad=True)


class Vixeous(vs2.Scene):
    def __init__(self):
        vs2.Scene.__init__(self)
        seed(utime.ticks_ms())

    def build(self):
        self.state = STATE_READY
        self.frame = self.camera_theta = self.player_offset = self.depth = self.area = 0
        self.player_y, self.score, self.lives = PLAYER_START_Y, 0, 3
        self.invulnerable, self.scroll_tick, self.next_wave, self.next_target_row = 0, 0, 45, 8
        self.boss_started = self.boss_defeated = False
        self.world = self.layer("world", projection=vs2.TUNNEL)
        self.hud = self.layer("hud", projection=vs2.HUD)

        # V2 paints a layer in creation order. Terrain is the ground, so it
        # must be declared before every object that travels over it.
        self.terrain_data = bytearray(TERRAIN_COLS * TERRAIN_BUFFER_ROWS)
        self.terrain_base_row = self.terrain_area = None
        self.terrain = self.world.tilemap(
            "terrain.png", columns=TERRAIN_COLS, rows=TERRAIN_BUFFER_ROWS,
            cells=self.terrain_data, x=0, y=TERRAIN_NEAR_Y,
            view_width=vs2.display.width, view_height=TERRAIN_VIEW_H)

        self.reticle = self.world.sprite("reticle.png")
        self.player = self.world.sprite("ship.png", y=self.player_y)
        self.shots = self.world.sprite_pool("shots.png", MAX_SHOTS)
        self.bombs = self.world.sprite_pool("shots.png", MAX_BOMBS)
        self.explosions = self.world.sprite_pool(
            "explosion.png", MAX_EXPLOSIONS, on_empty=vs2.RECYCLE)
        self.enemies = self.world.sprite_pool("enemy.png", MAX_ENEMIES)
        self.targets = self.world.sprite_pool("targets.png", MAX_TARGETS)
        self.boss = self.world.sprite("boss.png", visible=False)

        self.scoreboard = ScoreBoard(self.hud)
        self.scoreboard.set_score(0)
        self.scoreboard.set_lives(self.lives)
        self.message = self.hud.sprite(
            "messages.png", x=0, y=12, frame=0)
        self.message.x = centered_x(0, self.message.width)

        self.update_terrain()
        self.animate_player()
        vs2.audio.music("flight", loop=True)
        self.call_later(1200, self.start_playing)

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
        sprite = self.explosions.spawn(screen_x(theta, self.camera_theta, 20), y, frame=start_frame)
        if sprite is not None:
            sprite.theta, sprite.age = theta % vs2.display.width, start_frame * 3
        vs2.audio.sound("boom")

    def target_burst(self, theta, y):
        self.burst(theta, y)
        for offset in (-7, 7):
            sprite = self.explosions.spawn(
                screen_x(theta + offset, self.camera_theta, 20),
                y + (-3 if offset > 0 else 3), frame=1)
            if sprite is not None:
                sprite.theta = (theta + offset) % vs2.display.width
                sprite.age = 3

    def spawn_wave(self):
        base = (self.camera_theta + 44 + randrange(168)) % vs2.display.width
        for number in range(3 + self.area % 2):
            enemy = self.enemies.spawn(0, 170 + number * 7, frame=(self.area + number) % 3 * 2)
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
            screen_x(theta, self.camera_theta, 14), 164, frame=kind)
        if target is not None:
            target.theta, target.kind = theta, kind
        self.next_target_row = row + 5 + randrange(4)

    def maybe_start_boss(self):
        if self.boss_started or self.depth <= 900 or self.score < 120:
            return
        self.boss_started = True
        self.boss.theta = self.camera_theta
        self.boss.y = 150
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
            if target.y < 5:
                self.targets.despawn(target)
            else:
                target.x = screen_x(
                    target.theta, self.camera_theta, target.width)

    def update_entities(self):
        for shot in self.shots:
            shot.y += SHOT_SPEED
            if shot.y > 184:
                self.shots.despawn(shot)
            else:
                shot.x = screen_x(shot.theta, self.camera_theta, shot.width)
        for bomb in self.bombs:
            bomb.y += BOMB_SPEED
            bomb.x = screen_x(bomb.theta, self.camera_theta, bomb.width)
        for enemy in self.enemies:
            enemy.phase = (enemy.phase + 1) % 128
            enemy.theta = (enemy.theta + (2 if enemy.phase < 64 else -2)) % vs2.display.width
            enemy.y -= ENEMY_SPEED
            if enemy.y < 8:
                self.enemies.despawn(enemy)
            else:
                enemy.x = screen_x(enemy.theta, self.camera_theta, enemy.width)
                enemy.frame = enemy.kind * 2 + ((enemy.phase // 8) & 1)
        if self.boss.visible:
            self.boss.phase = (self.boss.phase + 1) % 192
            self.boss.theta = (
                self.boss.theta
                + (2 if self.boss.phase < 96 else -2)
            ) % vs2.display.width
            if self.boss.y > 116:
                self.boss.y -= 1
            self.boss.x = screen_x(
                self.boss.theta, self.camera_theta, self.boss.width)
            self.boss.frame = (self.boss.phase // 8) & 1
        for explosion in self.explosions:
            explosion.age += 1
            if explosion.age // 3 >= explosion.image.frames:
                self.explosions.despawn(explosion)
            else:
                explosion.x = screen_x(explosion.theta, self.camera_theta, explosion.width)
                explosion.frame = explosion.age // 3

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
                self.burst(bomb.theta, aim_y, start_frame=2)

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
