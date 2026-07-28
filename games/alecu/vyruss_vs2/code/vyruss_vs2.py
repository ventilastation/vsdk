"""Vyruss, ported from direct Sprite subclasses to V2-owned pools."""

from urandom import choice, randrange, seed
import utime

import vs2
from vs2.controls import A, B, DOWN, LEFT, RIGHT, UP, joy1


LEVELS = ((2, "saturno.png", 3), (3, "jupiter.png", 4),
          (4, "marte.png", 6), (5, "tierra.png", 8))
MAX_BOMBS = 8
MAX_BADDIES = 50


def heading(up, down, left, right):
    if up:
        return 128 if not left and not right else (96 if left else 160)
    if down:
        return 0 if not left and not right else (32 if left else 224)
    if left:
        return 64
    if right:
        return 192
    return None


def turn_toward(current, destination):
    destination = (destination + 128 - current) % vs2.display.width
    return -1 if destination < 128 else (1 if destination > 128 else 0)


class VyrusGame(vs2.Scene):
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
        self.planet = self.fullscreen.sprite(LEVELS[0][1], x=0, y=62, visible=False)
        self.player = self.world.sprite("ll9.png", x=vs2.display.width - 8, y=16)
        self.laser = self.world.sprite_pool("disparo.png", 1)
        self.bombs = self.world.sprite_pool("disparo.png", MAX_BOMBS)
        self.baddies = self.world.sprite_pool("galaga.png", MAX_BADDIES)
        self.explosions = self.world.sprite_pool("explosion.png", 8, on_empty=vs2.RECYCLE)
        self.scoreboard = self.hud.label("numerals.png", columns=9, x=110, y=0)
        self.game_over = self.hud.sprite("gameover.png", x=vs2.display.width - 32,
                                        y=0, visible=False)
        self.start_level()

    def start_level(self):
        self.waves, planet, simultaneous_bombs = LEVELS[self.level]
        self.simultaneous_bombs = simultaneous_bombs
        self.planet.image = planet
        self.planet.hide()
        self.wave = 0
        self.spawn_clock = 0
        self.baddies.despawn_all()
        self.bombs.despawn_all()
        self.laser.despawn_all()
        self.explosions.despawn_all()
        self.update_scoreboard()
        vs2.audio.music("vy-main")

    def update_scoreboard(self):
        self.scoreboard.set_number(self.score, width=5, pad="0")
        self.scoreboard.write(6, 0, "***"[:self.lives])

    def spawn_wave(self):
        self.wave += 1
        base = randrange(vs2.display.width)
        for index in range(10):
            baddie = self.baddies.spawn(base + index * 23, 150 + (index % 4) * 14,
                                        frame=2 + (index % 5) * 2)
            if baddie is not None:
                baddie.destination = (index * 18 + self.wave * 17) % vs2.display.width
                baddie.base_frame = baddie.frame
                baddie.phase = index * 7

    def fire(self):
        if len(self.laser):
            return
        laser = self.laser.spawn(self.player.x + 6, self.player.y + 11)
        if laser is not None:
            vs2.audio.sound("shoot1")

    def update_input(self):
        if joy1.just_pressed(A):
            self.fire()
        target = heading(joy1.held(UP), joy1.held(DOWN), joy1.held(LEFT), joy1.held(RIGHT))
        if target is not None:
            self.player.x = (self.player.x + turn_toward(self.player.x, target) * 2) % vs2.display.width
        if joy1.held(B):
            self.player.y -= 1
        elif joy1.held(DOWN):
            self.player.y += 1
        else:
            self.player.y = 16

    def update_baddies(self):
        for baddie in self.baddies:
            baddie.phase = (baddie.phase + 1) % 64
            baddie.x = (baddie.x + turn_toward(baddie.x, baddie.destination) * 3) % vs2.display.width
            baddie.y += -1 if baddie.y > 30 else 1
            baddie.frame = baddie.base_frame + ((baddie.phase // 8) & 1)

    def update_projectiles(self):
        for laser in self.laser:
            laser.y += 6
            if laser.y > 170:
                self.laser.despawn(laser)
                continue
            hit = laser.first_overlap(self.baddies)
            if hit is not None:
                self.laser.despawn(laser)
                self.baddies.despawn(hit)
                boom = self.explosions.spawn(hit.x, hit.y)
                if boom is not None:
                    boom.age = 0
                self.score += randrange(10, 19)
                self.update_scoreboard()
                vs2.audio.sound("explosion2")
        for boom in self.explosions:
            boom.age += 1
            if boom.age >= boom.image.frames:
                self.explosions.despawn(boom)
            else:
                boom.frame = boom.age

    def update(self):
        self.update_input()
        self.spawn_clock += 1
        if not len(self.baddies) and self.spawn_clock > 30:
            self.spawn_clock = 0
            if self.wave >= self.waves:
                self.level += 1
                if self.level >= len(LEVELS):
                    self.planet.show()
                    self.planet.frame = 0
                    self.call_later(4000, self.pop)
                    return
                self.start_level()
            else:
                self.spawn_wave()
        self.update_baddies()
        self.update_projectiles()


def main():
    return VyrusGame()
