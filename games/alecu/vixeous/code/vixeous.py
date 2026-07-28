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


class ScoreBoard:
    def __init__(self, layer):
        self.label = layer.label("digits.png", columns=9, x=93, y=1)

    def set_score(self, value):
        self.label.set_number(max(0, min(value, 99999)), width=5, pad="0")

    def set_lives(self, lives):
        self.label.write(6, 0, "***"[:lives], pad=True)


class Vixeous(vs2.Scene):
    def __init__(self):
        vs2.Scene.__init__(self)
        seed(utime.ticks_ms())

    def build(self):
        self.state = STATE_READY
        self.frame = self.camera_theta = self.player_offset = self.depth = self.area = 0
        self.player_y, self.score, self.lives = PLAYER_START_Y, 0, 3
        self.invulnerable, self.scroll_tick, self.next_wave, self.next_target_row = 0, 0, 45, 8
        self.world = self.layer("world", projection=vs2.TUNNEL)
        self.hud = self.layer("hud", projection=vs2.HUD)
        self.scoreboard = ScoreBoard(self.hud)
        self.scoreboard.set_score(0)
        self.scoreboard.set_lives(self.lives)
        self.message = self.hud.sprite("messages.png", y=12)
        self.reticle = self.world.sprite("reticle.png")
        self.player = self.world.sprite("ship.png", y=self.player_y)
        self.shots = self.world.sprite_pool("shots.png", MAX_SHOTS)
        self.bombs = self.world.sprite_pool("shots.png", MAX_BOMBS)
        self.explosions = self.world.sprite_pool("explosion.png", MAX_EXPLOSIONS, on_empty=vs2.RECYCLE)
        self.enemies = self.world.sprite_pool("enemy.png", MAX_ENEMIES)
        self.targets = self.world.sprite_pool("targets.png", MAX_TARGETS)
        self.boss = self.world.sprite("boss.png", visible=False)
        self.terrain_data = bytearray(TERRAIN_COLS * TERRAIN_BUFFER_ROWS)
        self.terrain_base_row = self.terrain_area = None
        self.terrain = self.world.tilemap(
            "terrain.png", columns=TERRAIN_COLS, rows=TERRAIN_BUFFER_ROWS,
            cells=self.terrain_data, x=0, y=TERRAIN_NEAR_Y,
            view_width=vs2.display.width, view_height=TERRAIN_VIEW_H)
        self.update_terrain()
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

    def spawn_wave(self):
        base = (self.camera_theta + 44 + randrange(168)) % vs2.display.width
        for number in range(3 + self.area % 2):
            enemy = self.enemies.spawn(0, 170 + number * 7, frame=(self.area + number) % 3 * 2)
            if enemy is not None:
                enemy.theta, enemy.kind, enemy.phase, enemy.hp = (base + number * 22) % vs2.display.width, (self.area + number) % 3, randrange(64), 1
        self.next_wave = 70 + randrange(45)

    def process_input(self):
        turn = (1 if joy1.held(LEFT) else 0) - (1 if joy1.held(RIGHT) else 0)
        desired = self.player_offset + turn * PLAYER_SIDE_SPEED
        self.player_offset = max(-PLAYER_SIDE_LIMIT, min(PLAYER_SIDE_LIMIT, desired))
        if self.player_offset:
            self.camera_theta = (self.camera_theta + (1 if self.player_offset > 0 else -1)) % vs2.display.width
            if not turn:
                self.player_offset -= 1 if self.player_offset > 0 else -1
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
        for explosion in self.explosions:
            explosion.age += 1
            if explosion.age // 3 >= explosion.image.frames:
                self.explosions.despawn(explosion)
            else:
                explosion.x = screen_x(explosion.theta, self.camera_theta, explosion.width)
                explosion.frame = explosion.age // 3

    def check_hits(self):
        for shot in self.shots:
            for enemy in self.enemies:
                if abs(angle_delta(shot.theta, enemy.theta)) < 12 and abs(shot.y - enemy.y) < 12:
                    self.shots.despawn(shot)
                    self.enemies.despawn(enemy)
                    self.burst(enemy.theta, enemy.y)
                    self.add_score(40)
                    break

    def update(self):
        self.process_input()
        self.frame += 1
        self.scroll_tick += 1
        if self.state == STATE_PLAYING and self.scroll_tick >= TERRAIN_SCROLL_TICKS:
            self.scroll_tick = 0
            self.depth += 1
            self.next_wave -= 1
            if self.next_wave <= 0:
                self.spawn_wave()
        self.player.x = centered_x(self.player_offset, self.player.width)
        self.player.y = self.player_y
        self.reticle.x = centered_x(self.player_offset, self.reticle.width)
        self.reticle.y = self.aim_y()
        self.update_terrain()
        self.update_entities()
        self.check_hits()


def main():
    return Vixeous()
