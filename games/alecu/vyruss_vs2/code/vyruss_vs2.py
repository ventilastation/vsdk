"""Vyruss on the sealed VS2 API."""

from urandom import choice, randrange, seed
import utime

import vs2
from vs2.controls import A, DOWN, LEFT, RIGHT, UP, joy1


LEVELS = (
    (2, "saturno.png", 3),
    (3, "jupiter.png", 4),
    (4, "marte.png", 6),
    (5, "tierra.png", 8),
)
MAX_BOMBS = max(level[2] for level in LEVELS)
MAX_GROUPS = max(level[0] for level in LEVELS)
BADDIES_PER_GROUP = 10
MAX_BADDIES = MAX_GROUPS * BADDIES_PER_GROUP
MAX_EXPLOSIONS = 8
X_SPEED = 3
Y_SPEED = 2

ENTERING = 0
ATTACKING = 1
DEFEATED = 2


def heading(up, down, left, right):
    """Return the angular heading selected by the eight-way controls."""
    if up:
        return 128 if not left and not right else (96 if left else 160)
    if down:
        return 0 if not left and not right else (32 if left else 224)
    if left:
        return 64
    if right:
        return 192
    return None


def angle_delta(destination, current):
    """Shortest signed distance from ``current`` to ``destination``."""
    half = vs2.display.width // 2
    return ((destination - current + half) % vs2.display.width) - half


def turn_toward(current, destination):
    delta = angle_delta(destination, current)
    return -1 if delta < 0 else (1 if delta > 0 else 0)


def move_toward_angle(current, destination, speed):
    delta = angle_delta(destination, current)
    if abs(delta) <= speed:
        return destination % vs2.display.width
    return (current + (-speed if delta < 0 else speed)) % vs2.display.width


def move_toward_depth(current, destination, speed):
    delta = destination - current
    if abs(delta) <= speed:
        return destination
    return current + (-speed if delta < 0 else speed)


class TravelTo:
    def __init__(self, x, y):
        self.dest_x = x
        self.dest_y = y

    def step(self, sprite):
        sprite.x = move_toward_angle(sprite.x, self.dest_x, X_SPEED)
        sprite.y = move_toward_depth(sprite.y, self.dest_y, Y_SPEED)

    def finished(self, sprite):
        return sprite.x == self.dest_x and sprite.y == self.dest_y


class TravelBy:
    def __init__(self, count):
        self.remaining = abs(count)
        self.direction = -1 if count < 0 else 1

    def finished(self, _sprite):
        return self.remaining <= 0


class TravelX(TravelBy):
    def step(self, sprite):
        distance = min(X_SPEED, self.remaining)
        sprite.x = (
            sprite.x + distance * self.direction
        ) % vs2.display.width
        self.remaining -= distance


class TravelCloser(TravelBy):
    def step(self, sprite):
        distance = min(Y_SPEED, self.remaining)
        sprite.y -= distance
        self.remaining -= distance


class TravelAway(TravelBy):
    def step(self, sprite):
        distance = min(Y_SPEED, self.remaining)
        sprite.y += distance
        self.remaining -= distance


class VyrusGame(vs2.Scene):
    BLINK_RATE = 45
    BLINK_FRAMES = {0: 0, 14: 1, 22: 2, 37: 3}

    def __init__(self):
        vs2.Scene.__init__(self)
        seed(utime.ticks_ms())

    def build(self):
        self.level = 0
        self.score = 0
        self.lives = 3
        self.fullscreen = self.layer("planet", projection=vs2.FULLSCREEN)
        self.world = self.layer("world", projection=vs2.TUNNEL)
        self.hud = self.layer("hud", projection=vs2.HUD)

        self.planet = self.fullscreen.sprite(
            LEVELS[0][1], x=0, y=62, visible=False)
        self.player = self.world.sprite(
            "ll9.png", x=vs2.display.width - 8, y=16)
        self.laser = self.world.sprite_pool("disparo.png", 1)
        self.bombs = self.world.sprite_pool("disparo.png", MAX_BOMBS)
        self.baddies = self.world.sprite_pool("galaga.png", MAX_BADDIES)
        self.explosions = self.world.sprite_pool(
            "explosion.png", MAX_EXPLOSIONS, on_empty=vs2.RECYCLE)
        self.player_explosion = self.world.sprite(
            "explosion_nave.png", visible=False)
        self.scoreboard = self.hud.label(
            "numerals.png", columns=9, x=110, y=0,
            flip_x=True, flip_y=True)
        self.game_over = self.hud.sprite(
            "gameover.png", x=vs2.display.width - 32, y=0,
            visible=False)
        self.start_level()

    def start_level(self):
        self.waves, planet, self.simultaneous_bombs = LEVELS[self.level]
        self.planet.image = planet
        self.planet.hide()
        self.game_over.hide()
        self.player_explosion.hide()
        self.player.show()
        self.player.x = vs2.display.width - self.player.width // 2
        self.player.y = 16
        self.player.frame = 0
        self.player_frame_clock = -1
        self.player_exploded = False
        self.baddies.despawn_all()
        self.bombs.despawn_all()
        self.laser.despawn_all()
        self.explosions.despawn_all()
        self.everyone = []
        self.groups = [[]]
        self.attacking = []
        self.max_attacking = 1
        self.group_steps = 0
        self.num_baddies = 0
        self.next_bomb = 37
        self.state = ENTERING
        self.planet_animating = False
        self.ship_warping = False
        self.update_scoreboard()
        vs2.audio.music("vy-main")

    def update_scoreboard(self):
        self.scoreboard.set_number(self.score, width=5, pad="0")
        self.scoreboard.write(
            6, 0, "***"[:self.lives], pad=True)

    def add_baddie(self):
        final_x_positions = (
            0, 128, 55, 183, 18, 73, 146,
            201, 37, 91, 238, 110, 165, 219,
        )
        final_y_positions = (128, 110, 92, 74)
        bases = (120, 216, 24, 248, 120)
        number = self.num_baddies
        final_x = final_x_positions[number % len(final_x_positions)]
        final_y = final_y_positions[number // len(final_x_positions)]
        self.num_baddies += 1
        frame = (self.num_baddies % 5) * 2 + 2
        base_x = bases[len(self.groups) - 1]
        odd = len(self.groups[-1]) % 2
        start_x = base_x + (16 if odd else -16)
        baddie = self.baddies.spawn(
            start_x, 160, frame=frame)
        if baddie is None:
            return
        baddie.base_frame = frame
        baddie.frame_clock = 0
        baddie.dead = False
        baddie.finished = False
        if odd:
            baddie.movements = [
                TravelCloser(80), TravelX(112),
                TravelCloser(32), TravelX(-96),
                TravelAway(42), TravelTo(final_x, final_y),
            ]
        else:
            baddie.movements = [
                TravelCloser(80), TravelX(-112),
                TravelCloser(32), TravelX(96),
                TravelAway(42), TravelTo(final_x, final_y),
            ]
        self.groups[-1].append(baddie)
        self.everyone.append(baddie)

    def update_one_baddie(self, baddie):
        if baddie.dead:
            return
        baddie.frame_clock += 1
        baddie.frame = (
            baddie.base_frame + (0 if baddie.frame_clock & 8 else 1)
        )
        if baddie.movements:
            baddie.finished = False
            movement = baddie.movements[0]
            movement.step(baddie)
            if movement.finished(baddie):
                baddie.movements.pop(0)
        elif not baddie.finished:
            baddie.finished = True

    def group_finished(self):
        group = self.groups[-1]
        return bool(group) and all(
            baddie.dead or baddie.finished for baddie in group)

    def update_entering(self):
        for baddie in self.everyone:
            self.update_one_baddie(baddie)
        self.group_steps += 1
        if (self.group_steps % 8 == 0
                and len(self.groups[-1]) < BADDIES_PER_GROUP):
            self.add_baddie()
        if self.group_finished():
            self.group_steps = 0
            if len(self.groups) < self.waves:
                self.groups.append([])
            else:
                self.state = ATTACKING
        self.next_bomb -= 1
        if self.next_bomb <= 0:
            self.drop_bomb()
            self.next_bomb = 20 + randrange(30)

    def update_attacking(self):
        for baddie in self.everyone:
            self.update_one_baddie(baddie)
            if baddie.finished and baddie in self.attacking:
                self.attacking.remove(baddie)
                self.max_attacking += 1
        if not self.everyone:
            self.start_defeated()
            return
        if len(self.attacking) < self.max_attacking:
            baddie = choice(self.everyone)
            if baddie not in self.attacking:
                distance = max(0, baddie.y - 16)
                baddie.movements = [
                    TravelCloser(distance), TravelAway(distance)]
                baddie.finished = False
                self.attacking.append(baddie)
                self.drop_bomb()

    def start_defeated(self):
        self.state = DEFEATED
        self.planet.y = 0
        self.planet.frame = 0
        self.planet.show()
        self.planet_animating = True
        self.ship_warping = False
        vs2.audio.music("vy-3warps")
        self.call_later(4000, self.warp_player)

    def warp_player(self):
        self.ship_warping = True

    def finish_level(self):
        self.level += 1
        if self.level >= len(LEVELS):
            self.pop()
        else:
            self.start_level()

    def update_defeated(self):
        if self.planet_animating:
            self.planet.y += 1
            if self.planet.y >= 255:
                self.planet.y = 255
                self.planet_animating = False
                self.call_later(1500, self.finish_level)
        if self.ship_warping:
            self.player.y += 2
            if self.player.y > 250:
                self.ship_warping = False

    def fire(self):
        if len(self.laser) or self.player_exploded:
            return
        laser = self.laser.spawn(
            self.player.x + 6, self.player.y + 11, frame=0)
        if laser is not None:
            vs2.audio.sound("shoot1")

    def drop_bomb(self):
        if not self.everyone or len(self.bombs) >= self.simultaneous_bombs:
            return
        source = choice(self.everyone)
        bomb = self.bombs.spawn(
            source.x + 6, source.y + 11, frame=1)
        if bomb is not None:
            vs2.audio.sound("shoot3")

    def update_input(self):
        if joy1.just_pressed(A):
            self.fire()
        target = heading(
            joy1.held(UP), joy1.held(DOWN),
            joy1.held(LEFT), joy1.held(RIGHT))
        if target is not None and not self.player_exploded:
            target = (
                target - self.player.width // 2
            ) % vs2.display.width
            self.player.x = move_toward_angle(
                self.player.x, target, 2)
        if not self.player_exploded and self.state != DEFEATED:
            # The original game keeps the fighter on the rim. The rework port
            # accidentally also treated DOWN as radial movement, so steering
            # down changed two axes at once. Once a wave is defeated, the warp
            # sequence owns Y and flies the fighter inward toward the planet.
            self.player.y = 16

    def animate_player(self):
        if self.player_exploded:
            return
        self.player_frame_clock = (
            self.player_frame_clock + 1
        ) % self.BLINK_RATE
        frame = self.BLINK_FRAMES.get(self.player_frame_clock)
        if frame is not None:
            self.player.frame = frame

    def kill_baddie(self, baddie):
        if baddie.dead:
            return
        x = baddie.x + baddie.width // 2 - 16
        y = baddie.y + baddie.height // 2 - 16
        baddie.dead = True
        baddie.hide()
        if baddie in self.everyone:
            self.everyone.remove(baddie)
        if baddie in self.attacking:
            self.attacking.remove(baddie)
            self.max_attacking += 1
        boom = self.explosions.spawn(x, y)
        if boom is not None:
            boom.age = 0
        self.score += randrange(10, 19)
        self.update_scoreboard()
        vs2.audio.sound("explosion2")

    def explode_player(self):
        if self.player_exploded:
            return
        self.player_exploded = True
        self.player.hide()
        self.player_explosion.x = (
            self.player.x + self.player.width // 2
            - self.player_explosion.width // 2
        )
        self.player_explosion.y = (
            self.player.y + self.player.height // 2
            - self.player_explosion.height // 2
        )
        self.player_explosion.frame = 0
        self.player_explosion.age = 0
        self.player_explosion.show()
        self.lives -= 1
        self.update_scoreboard()
        vs2.audio.sound("explosion3")
        if self.lives:
            self.call_later(1500, self.respawn_player)
        else:
            self.game_over.show()
            vs2.audio.music("vy-gameover")
            self.call_later(8333, self.pop)

    def respawn_player(self):
        self.player_explosion.hide()
        self.player_exploded = False
        self.player.x = vs2.display.width - self.player.width // 2
        self.player.y = 16
        self.player.frame = 0
        self.player_frame_clock = -1
        self.player.show()

    def update_projectiles(self):
        for laser in self.laser:
            laser.y += 6
            if laser.y > 170:
                self.laser.despawn(laser)
                continue
            hit = None
            for baddie in self.everyone:
                if laser.overlaps(baddie):
                    hit = baddie
                    break
            if hit is not None:
                self.laser.despawn(laser)
                self.kill_baddie(hit)
        for bomb in self.bombs:
            bomb.y -= 3
            if bomb.y < 6:
                self.bombs.despawn(bomb)
        for boom in self.explosions:
            boom.age += 1
            if boom.age >= boom.image.frames:
                self.explosions.despawn(boom)
            else:
                boom.frame = boom.age

    def update_player_collision(self):
        if self.player_exploded:
            return
        hit = self.player.first_overlap(self.bombs)
        if hit is not None:
            self.bombs.despawn(hit)
            self.explode_player()
            return
        for baddie in self.everyone:
            if self.player.overlaps(baddie):
                self.kill_baddie(baddie)
                self.explode_player()
                return

    def update_player_explosion(self):
        if not self.player_explosion.visible:
            return
        self.player_explosion.age += 1
        if self.player_explosion.age >= self.player_explosion.image.frames:
            self.player_explosion.hide()
        else:
            self.player_explosion.frame = self.player_explosion.age

    def update(self):
        self.update_input()
        if self.state == ENTERING:
            self.update_entering()
        elif self.state == ATTACKING:
            self.update_attacking()
        else:
            self.update_defeated()
        self.animate_player()
        self.update_projectiles()
        self.update_player_collision()
        self.update_player_explosion()


def main():
    return VyrusGame()
