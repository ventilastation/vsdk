from urandom import randrange, seed
import utime

from ventilastation.director import director, stripes
from ventilastation.scene import Scene
from ventilastation.sprites import Sprite


FULLSCREEN = 0
TUNNEL = 1
HUD = 2

COLUMNS = 256
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
TERRAIN_SPRITES = TERRAIN_COLS * TERRAIN_ROWS

MAX_SHOTS = 4
MAX_BOMBS = 3
MAX_ENEMIES = 6
MAX_TARGETS = 5
MAX_EXPLOSIONS = 5

SHOT_SPEED = 8
BOMB_SPEED = 4
ENEMY_SPEED = 1
RETICLE_DISTANCE = 62
TOP_SCORE_X = 93
TOP_LIVES_X = 140

STATE_READY = 0
STATE_PLAYING = 1
STATE_AREA_CLEAR = 2
STATE_GAME_OVER = 3


def angle_delta(a, b):
    return ((a - b + 128) % COLUMNS) - 128


def centered_x(theta, width):
    return (theta - (width // 2)) % COLUMNS


def screen_x(world_theta, camera_theta, width):
    return centered_x(world_theta - camera_theta, width)


def clamp(value, low, high):
    return max(low, min(high, value))


def terrain_river_center(row, area):
    return (row // 3 + area * 2) % TERRAIN_COLS


def terrain_frame_for(col, row, area):
    river = terrain_river_center(row, area)
    delta = abs(col - river)
    delta = min(delta, TERRAIN_COLS - delta)
    next_river = terrain_river_center(row + 3, area)
    next_delta = abs(col - next_river)
    next_delta = min(next_delta, TERRAIN_COLS - next_delta)
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
    delta = abs(col - river)
    delta = min(delta, TERRAIN_COLS - delta)
    return delta == 0


def terrain_is_shore(col, row, area):
    river = terrain_river_center(row, area)
    delta = abs(col - river)
    delta = min(delta, TERRAIN_COLS - delta)
    return delta in (1, 2)


def terrain_is_pad(col, row):
    return (row % 13 == 0 and col in (0, 4)) or (row % 17 == 4 and col in (3, 7))


def terrain_theta_for(col, row, area):
    return (col * TERRAIN_TILE_W + row * 5 + area * 13) % COLUMNS


def is_targetable_terrain(col, row, area):
    return not terrain_is_water(col, row, area) and (terrain_is_shore(col, row, area) or terrain_is_pad(col, row))


class ScoreBoard:
    def __init__(self):
        self.score_digits = []
        for n in range(5):
            s = Sprite()
            s.set_strip(stripes["digits.png"])
            s.set_perspective(HUD)
            s.set_x(TOP_SCORE_X + n * 5)
            s.set_y(1)
            s.set_frame(0)
            self.score_digits.append(s)

        self.life_icons = []
        for n in range(3):
            s = Sprite()
            s.set_strip(stripes["digits.png"])
            s.set_perspective(HUD)
            s.set_x(TOP_LIVES_X + n * 6)
            s.set_y(1)
            s.set_frame(11)
            self.life_icons.append(s)

    def set_score(self, value):
        text = "%05d" % clamp(value, 0, 99999)
        for n, digit in enumerate(text):
            self.score_digits[n].set_frame(ord(digit) - 48)

    def set_lives(self, lives):
        for n, icon in enumerate(self.life_icons):
            icon.set_frame(11 if n < lives else 10)


class PooledSprite:
    def __init__(self, strip_name, perspective=TUNNEL):
        self.sprite = Sprite()
        self.sprite.set_strip(stripes[strip_name])
        self.sprite.set_perspective(perspective)
        self.active = False
        self.disable()

    def disable(self):
        self.active = False
        self.sprite.disable()


class Shot(PooledSprite):
    def __init__(self):
        PooledSprite.__init__(self, "shots.png", TUNNEL)
        self.theta = 0
        self.y = 0

    def fire(self, theta, y):
        self.theta = theta % COLUMNS
        self.y = y + 12
        self.active = True
        self.sprite.set_frame(0)
        director.sound_play("alecu.vixeous/shoot")

    def step(self, camera_theta):
        if not self.active:
            return
        self.y += SHOT_SPEED
        if self.y > 184:
            self.disable()
            return
        self.sprite.set_x(screen_x(self.theta, camera_theta, self.sprite.width()))
        self.sprite.set_y(self.y)


class Bomb(PooledSprite):
    def __init__(self):
        PooledSprite.__init__(self, "shots.png", TUNNEL)
        self.theta = 0
        self.y = 0

    def drop(self, theta, y):
        self.theta = theta % COLUMNS
        self.y = y + 6
        self.active = True
        self.sprite.set_frame(1)
        director.sound_play("alecu.vixeous/bomb")

    def step(self, camera_theta):
        if not self.active:
            return
        self.y += BOMB_SPEED
        self.sprite.set_x(screen_x(self.theta, camera_theta, self.sprite.width()))
        self.sprite.set_y(self.y)


class Explosion(PooledSprite):
    def __init__(self):
        PooledSprite.__init__(self, "explosion.png", TUNNEL)
        self.frame_tick = 0

    def burst(self, theta, y, camera_theta, start_frame=0):
        self.theta = theta % COLUMNS
        self.y = y
        self.frame_tick = start_frame * 3
        self.active = True
        self.sprite.set_x(screen_x(self.theta, camera_theta, self.sprite.width()))
        self.sprite.set_y(self.y)
        self.sprite.set_frame(start_frame)

    def step(self, camera_theta):
        if not self.active:
            return
        self.frame_tick += 1
        frame = self.frame_tick // 3
        if frame >= 6:
            self.disable()
            return
        self.sprite.set_x(screen_x(self.theta, camera_theta, self.sprite.width()))
        self.sprite.set_frame(frame)


class Enemy(PooledSprite):
    def __init__(self):
        PooledSprite.__init__(self, "enemy.png", TUNNEL)
        self.theta = 0
        self.y = 0
        self.kind = 0
        self.phase = 0
        self.hp = 1

    def spawn(self, theta, y, kind):
        self.theta = theta % COLUMNS
        self.y = y
        self.kind = kind
        self.phase = randrange(64)
        self.hp = 1 + (1 if kind == 2 else 0)
        self.active = True
        self.sprite.set_frame(kind * 2)

    def step(self, camera_theta):
        if not self.active:
            return
        self.phase = (self.phase + 1) % 128
        drift = 2 if self.phase < 64 else -2
        self.theta = (self.theta + drift) % COLUMNS
        self.y -= ENEMY_SPEED
        if self.y < 8:
            self.disable()
            return
        self.sprite.set_x(screen_x(self.theta, camera_theta, self.sprite.width()))
        self.sprite.set_y(self.y)
        self.sprite.set_frame(self.kind * 2 + ((self.phase // 8) & 1))


class GroundTarget(PooledSprite):
    def __init__(self):
        PooledSprite.__init__(self, "targets.png", TUNNEL)
        self.theta = 0
        self.y = 0
        self.kind = 0

    def spawn(self, theta, y, kind):
        self.theta = theta % COLUMNS
        self.y = y
        self.kind = kind
        self.active = True
        self.sprite.set_frame(kind)

    def step(self, camera_theta, dy):
        if not self.active:
            return
        self.y -= dy
        if self.y < 5:
            self.disable()
            return
        self.sprite.set_x(screen_x(self.theta, camera_theta, self.sprite.width()))
        self.sprite.set_y(self.y)


class Boss:
    def __init__(self):
        self.sprite = Sprite()
        self.sprite.set_strip(stripes["boss.png"])
        self.sprite.set_perspective(TUNNEL)
        self.active = False
        self.theta = 0
        self.y = 150
        self.hp = 0
        self.phase = 0
        self.sprite.disable()

    def spawn(self, camera_theta):
        self.active = True
        self.theta = camera_theta % COLUMNS
        self.y = 150
        self.hp = 18
        self.phase = 0
        self.sprite.set_frame(0)
        director.sound_play("alecu.vixeous/boss")

    def disable(self):
        self.active = False
        self.sprite.disable()

    def step(self, camera_theta):
        if not self.active:
            return
        self.phase = (self.phase + 1) % 192
        self.theta = (self.theta + (2 if self.phase < 96 else -2)) % COLUMNS
        if self.y > 116:
            self.y -= 1
        self.sprite.set_x(screen_x(self.theta, camera_theta, self.sprite.width()))
        self.sprite.set_y(self.y)
        self.sprite.set_frame((self.phase // 8) & 1)


class TerrainTile:
    def __init__(self, col, row):
        self.sprite = Sprite()
        self.sprite.set_strip(stripes["terrain.png"])
        self.sprite.set_perspective(TUNNEL)
        self.col = col
        self.world_row = row
        self.y = TERRAIN_NEAR_Y + row * TERRAIN_TILE_H
        self.sprite.set_frame(0)

    def terrain_frame(self, area):
        return terrain_frame_for(self.col, self.world_row, area)

    def step(self, camera_theta, area, dy):
        self.y -= dy
        if self.y < TERRAIN_NEAR_Y - TERRAIN_TILE_H:
            self.y += TERRAIN_ROWS * TERRAIN_TILE_H
            self.world_row += TERRAIN_ROWS
        theta = terrain_theta_for(self.col, self.world_row, area)
        self.sprite.set_x(screen_x(theta, camera_theta, TERRAIN_TILE_W))
        self.sprite.set_y(self.y)
        self.sprite.set_frame(self.terrain_frame(area))


class Vixeous(Scene):
    stripes_rom = "alecu.vixeous"
    keep_music = False

    def __init__(self):
        Scene.__init__(self)
        seed(utime.ticks_ms())

    def on_enter(self):
        Scene.on_enter(self)
        director.music_play("alecu.vixeous/flight", loop=True)

        self.state = STATE_READY
        self.frame = 0
        self.camera_theta = 0
        self.player_offset = 0
        self.player_y = PLAYER_START_Y
        self.depth = 0
        self.area = 0
        self.score = 0
        self.lives = 3
        self.invulnerable = 0
        self.scroll_tick = 0
        self.next_wave = 45
        self.next_target_row = 8
        self.boss_started = False
        self.boss_defeated = False

        self.scoreboard = ScoreBoard()
        self.scoreboard.set_score(self.score)
        self.scoreboard.set_lives(self.lives)

        self.message = Sprite()
        self.message.set_strip(stripes["messages.png"])
        self.message.set_perspective(HUD)
        self.message.set_x(centered_x(0, self.message.width()))
        self.message.set_y(12)
        self.message.set_frame(0)

        self.reticle = Sprite()
        self.reticle.set_strip(stripes["reticle.png"])
        self.reticle.set_perspective(TUNNEL)
        self.reticle.set_x(centered_x(0, self.reticle.width()))
        self.reticle.set_y(self.aim_y())
        self.reticle.set_frame(0)

        self.player = Sprite()
        self.player.set_strip(stripes["ship.png"])
        self.player.set_perspective(TUNNEL)
        self.player.set_x(centered_x(0, self.player.width()))
        self.player.set_y(self.player_y)
        self.player.set_frame(0)

        self.shots = [Shot() for _ in range(MAX_SHOTS)]
        self.bombs = [Bomb() for _ in range(MAX_BOMBS)]
        self.explosions = [Explosion() for _ in range(MAX_EXPLOSIONS)]
        self.enemies = [Enemy() for _ in range(MAX_ENEMIES)]
        self.targets = [GroundTarget() for _ in range(MAX_TARGETS)]
        self.boss = Boss()

        self.terrain = [
            TerrainTile(col, row)
            for row in range(TERRAIN_ROWS)
            for col in range(TERRAIN_COLS)
        ]

        self.call_later(1200, self.start_playing)

    def start_playing(self):
        if self.state == STATE_READY:
            self.message.disable()
            self.state = STATE_PLAYING

    def first_free(self, pool):
        for item in pool:
            if not item.active:
                return item
        return None

    def add_score(self, amount):
        self.score += amount
        self.scoreboard.set_score(self.score)

    def aim_y(self):
        return self.player_y + RETICLE_DISTANCE

    def burst(self, theta, y, loud=True):
        explosion = self.first_free(self.explosions)
        if explosion:
            explosion.burst(theta, y, self.camera_theta, 0 if loud else 2)
        director.sound_play("alecu.vixeous/boom" if loud else "alecu.vixeous/hit")

    def target_burst(self, theta, y):
        self.burst(theta, y, True)
        extra = self.first_free(self.explosions)
        if extra:
            extra.burst(theta - 7, y + 3, self.camera_theta, 1)
        extra = self.first_free(self.explosions)
        if extra:
            extra.burst(theta + 7, y - 3, self.camera_theta, 1)

    def spawn_wave(self):
        base = (self.camera_theta + 44 + randrange(168)) % COLUMNS
        count = 3 + (self.area % 2)
        for n in range(count):
            enemy = self.first_free(self.enemies)
            if enemy:
                enemy.spawn(base + n * 22, 170 + n * 7, (self.area + n) % 3)
        self.next_wave = 70 + randrange(45)

    def spawn_target_if_needed(self):
        row = self.depth // TERRAIN_TILE_H
        if row < self.next_target_row:
            return
        target = self.first_free(self.targets)
        if target:
            target_row = row + TERRAIN_ROWS + 1
            pad_cols = [col for col in range(TERRAIN_COLS) if terrain_is_pad(col, target_row)]
            cols = pad_cols or [col for col in range(TERRAIN_COLS) if is_targetable_terrain(col, target_row, self.area)]
            col = cols[randrange(len(cols))] if cols else randrange(TERRAIN_COLS)
            kind = 3 if col in pad_cols else randrange(3)
            target.spawn(terrain_theta_for(col, target_row, self.area), 164, kind)
        self.next_target_row = row + 5 + randrange(4)

    def maybe_start_boss(self):
        if self.boss_started:
            return
        if self.depth > 900 and self.score >= 120:
            self.boss_started = True
            self.boss.spawn(self.camera_theta)

    def player_theta(self):
        return (self.camera_theta + self.player_offset) % COLUMNS

    def update_turning(self, turn):
        if turn:
            desired_offset = self.player_offset + turn * PLAYER_SIDE_SPEED
            if desired_offset > PLAYER_SIDE_LIMIT:
                self.camera_theta = (self.camera_theta + desired_offset - PLAYER_SIDE_LIMIT) % COLUMNS
                desired_offset = PLAYER_SIDE_LIMIT
            elif desired_offset < -PLAYER_SIDE_LIMIT:
                self.camera_theta = (self.camera_theta + desired_offset + PLAYER_SIDE_LIMIT) % COLUMNS
                desired_offset = -PLAYER_SIDE_LIMIT
            self.player_offset = desired_offset

        if self.player_offset:
            abs_offset = abs(self.player_offset)
            if turn:
                follow = 1
                if abs_offset > PLAYER_SIDE_LIMIT * 3 // 4:
                    follow = 4
                elif abs_offset > PLAYER_SIDE_LIMIT // 2:
                    follow = 2
            else:
                follow = 1
            if follow > abs_offset:
                follow = abs_offset
            direction = 1 if self.player_offset > 0 else -1
            self.camera_theta = (self.camera_theta + direction * follow) % COLUMNS
            self.player_offset -= direction * follow

    def process_input(self):
        left = director.is_pressed(director.JOY_LEFT)
        right = director.is_pressed(director.JOY_RIGHT)
        self.update_turning(left - right)

        up = director.is_pressed(director.JOY_UP)
        down = director.is_pressed(director.JOY_DOWN)
        if up:
            self.player_y = min(PLAYER_MAX_Y, self.player_y + PLAYER_Y_SPEED)
        if down:
            self.player_y = max(PLAYER_MIN_Y, self.player_y - PLAYER_Y_SPEED)

        if director.was_pressed(director.BUTTON_A):
            shot = self.first_free(self.shots)
            if shot:
                shot.fire(self.player_theta(), self.player_y)

        if director.was_pressed(director.BUTTON_B):
            bomb = self.first_free(self.bombs)
            if bomb:
                bomb.drop(self.player_theta(), self.player_y)

        if director.was_pressed(director.BUTTON_D) or director.timedout:
            self.finished()

    def damage_player(self):
        if self.invulnerable:
            return
        self.lives -= 1
        self.scoreboard.set_lives(self.lives)
        self.invulnerable = 60
        director.sound_play("alecu.vixeous/hit")
        if self.lives <= 0:
            self.game_over()

    def game_over(self):
        self.state = STATE_GAME_OVER
        self.message.set_frame(2)
        self.message.set_y(12)
        director.music_play("alecu.vixeous/gameover")
        self.call_later(3500, self.finished)

    def area_clear(self):
        self.state = STATE_AREA_CLEAR
        self.area += 1
        self.boss_defeated = True
        self.message.set_frame(1)
        self.message.set_y(12)
        director.sound_play("alecu.vixeous/area")
        self.call_later(2500, self.resume_next_area)

    def resume_next_area(self):
        if self.state == STATE_AREA_CLEAR:
            self.message.disable()
            self.next_wave = 35
            self.next_target_row = (self.depth // TERRAIN_TILE_H) + 4
            self.state = STATE_PLAYING

    def check_shot_hits(self):
        for shot in self.shots:
            if not shot.active:
                continue
            if self.boss.active:
                if abs(angle_delta(shot.theta, self.boss.theta)) < 22 and abs(shot.y - self.boss.y) < 18:
                    shot.disable()
                    self.boss.hp -= 1
                    director.sound_play("alecu.vixeous/hit")
                    if self.boss.hp <= 0:
                        self.burst(self.boss.theta, self.boss.y)
                        self.boss.disable()
                        self.add_score(500)
                        self.area_clear()
                    continue
            for enemy in self.enemies:
                if not enemy.active:
                    continue
                if abs(angle_delta(shot.theta, enemy.theta)) < 12 and abs(shot.y - enemy.y) < 12:
                    shot.disable()
                    enemy.hp -= 1
                    if enemy.hp <= 0:
                        self.burst(enemy.theta, enemy.y)
                        enemy.disable()
                        self.add_score(40)
                    break

    def check_bomb_hits(self):
        aim_y = self.aim_y()
        for bomb in self.bombs:
            if not bomb.active:
                continue
            if bomb.y < aim_y:
                continue
            hit = False
            for target in self.targets:
                if not target.active:
                    continue
                if abs(angle_delta(bomb.theta, target.theta)) < 20 and abs(target.y - aim_y) < 24:
                    bomb.disable()
                    self.target_burst(target.theta, target.y)
                    score = 120 if target.kind == 3 else 70
                    target.disable()
                    self.add_score(score)
                    hit = True
                    break
            if not hit:
                bomb.disable()
                self.burst(bomb.theta, aim_y, False)

    def check_player_hits(self):
        if self.state != STATE_PLAYING:
            return
        player_theta = self.player_theta()
        for enemy in self.enemies:
            if enemy.active and enemy.y < self.player_y + 18:
                if abs(angle_delta(enemy.theta, player_theta)) < 15:
                    enemy.disable()
                    self.burst(enemy.theta, enemy.y)
                    self.damage_player()
                    return
        if self.boss.active and self.boss.y < self.player_y + 42:
            if abs(angle_delta(self.boss.theta, player_theta)) < 24:
                self.damage_player()

    def animate_player(self):
        if self.invulnerable:
            self.invulnerable -= 1
            if self.invulnerable & 2:
                self.player.disable()
                return
        self.player.set_x(centered_x(self.player_offset, self.player.width()))
        self.player.set_y(self.player_y)
        self.player.set_frame((self.frame // 5) % 4)

    def step(self):
        self.frame = (self.frame + 1) % 10000
        dy = 0

        if self.state in (STATE_READY, STATE_PLAYING):
            self.process_input()

        if self.state == STATE_PLAYING:
            self.scroll_tick = (self.scroll_tick + 1) % TERRAIN_SCROLL_TICKS
            if self.scroll_tick == 0:
                dy = 1
            self.depth += dy
            self.spawn_target_if_needed()
            self.next_wave -= 1
            if self.next_wave <= 0 and not self.boss.active:
                self.spawn_wave()
            self.maybe_start_boss()

        aim_y = self.aim_y()
        reticle_frame = 1 if any(b.active and b.y >= aim_y - 12 for b in self.bombs) else 0
        self.reticle.set_frame(reticle_frame + (self.area % 2))
        self.reticle.set_x(centered_x(self.player_offset, self.reticle.width()))
        self.reticle.set_y(aim_y)

        for tile in self.terrain:
            tile.step(self.camera_theta, self.area, dy)

        for target in self.targets:
            target.step(self.camera_theta, dy)

        for enemy in self.enemies:
            enemy.step(self.camera_theta)

        self.boss.step(self.camera_theta)

        for shot in self.shots:
            shot.step(self.camera_theta)

        for bomb in self.bombs:
            bomb.step(self.camera_theta)

        for explosion in self.explosions:
            explosion.step(self.camera_theta)

        self.check_shot_hits()
        self.check_bomb_hits()
        self.check_player_hits()
        self.animate_player()

    def finished(self):
        director.pop()
        raise StopIteration()


def main():
    return Vixeous()
