"""The small shooter that the VS2 tutorial builds, chapter by chapter.

Fly the ship around the rim, shoot the enemies that come down the tunnel at
you, and don't let one touch the ship. See docs/vs2/tutorial/.
"""

from urandom import randrange

import vs2
from vs2.controls import *

SHOT_SPEED = 3       # depth units per tick, away from the ship
SHOT_RANGE = 170     # depth at which a shot has gone too far to matter
ENEMY_SPEED = 0.5    # depth units per tick, toward the ship
ENEMY_START = 160    # depth at which enemies appear
SPAWN_MS = 900       # time between enemies
BOOM_TICKS = 3       # ticks each explosion frame stays on screen
POINTS = 10


class Game(vs2.Scene):
    def build(self):
        self.world = self.layer("world", projection=vs2.TUNNEL)
        self.hud = self.layer("hud", projection=vs2.HUD)

        # An island of terrain; every other cell stays empty, so it is dark.
        self.ground = self.world.tilemap("terrain.png", columns=16, rows=16,
                                         view_width=256, view_height=128, y=16)
        self.draw_island()

        self.ship = self.world.sprite("ship.png", x=128, y=0)
        self.shots = self.world.sprite_pool("shots.png", count=8)
        self.enemies = self.world.sprite_pool("enemy.png", count=16)
        self.booms = self.world.sprite_pool("explosion.png", count=4,
                                            on_empty=vs2.RECYCLE)

        # Bottom of the disc, so the score reads upright.
        self.score_label = self.hud.label("numerals.png", columns=5, x=246, y=1)

        self.score = 0
        self.ticks = 0
        self.show_score()
        self.call_later(SPAWN_MS, self.spawn_enemy)

    def draw_island(self):
        GRASS, WATER, ROCK, SAND = 0, 1, 2, 3
        for row in range(1, 7):
            for col in range(3, 10):
                tile = GRASS
                if col == 6:
                    tile = WATER
                elif row in (1, 6):
                    tile = SAND
                elif (col + row) % 5 == 0:
                    tile = ROCK
                self.ground[col, row] = tile

    def show_score(self):
        self.score_label.set_number(self.score, width=5, pad="0")

    def update(self):
        self.ticks += 1

        if joy1.held(LEFT):
            self.ship.x = (self.ship.x - 1) % vs2.display.width
        if joy1.held(RIGHT):
            self.ship.x = (self.ship.x + 1) % vs2.display.width
        self.ship.frame = (self.ticks // 4) % self.ship.image.frames

        if joy1.just_pressed(A):
            self.fire()

        self.move_shots()
        if self.move_enemies():
            return self.switch(GameOver(self.score))
        self.animate_booms()

    def fire(self):
        # Centre the 6-column shot on the 18-column ship.
        shot = self.shots.spawn(x=self.ship.x + 6, y=self.ship.y + 4)
        if shot is not None:
            vs2.audio.sound("shoot")

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
                self.score += POINTS
                self.show_score()
                vs2.audio.sound("boom")

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
                self.booms.despawn(boom)
            else:
                boom.frame += 1

    def spawn_enemy(self):
        self.enemies.spawn(x=randrange(vs2.display.width), y=ENEMY_START)
        self.call_later(SPAWN_MS, self.spawn_enemy)


def centred_label(layer, text, y):
    """A label for ``text``, centred on the bottom of the disc, where it reads
    upright. rainbow437.png is a full CP437 font, 9 columns per character."""
    label = layer.label("rainbow437.png", columns=len(text), x=0, y=y, text=text)
    label.x = -(len(text) * label.image.width) // 2
    return label


class Title(vs2.Scene):
    def build(self):
        hud = self.layer("hud", projection=vs2.HUD)
        centred_label(hud, "TUNNEL SHOOTER", y=20)
        centred_label(hud, "PRESS A", y=1)

    def update(self):
        if joy1.just_pressed(A):
            self.switch(Game())


class GameOver(vs2.Scene):
    def __init__(self, score):
        vs2.Scene.__init__(self)
        self.score = score

    def build(self):
        hud = self.layer("hud", projection=vs2.HUD)
        centred_label(hud, "GAME OVER", y=30)
        score = hud.label("numerals.png", columns=5, x=246, y=20)
        score.set_number(self.score, width=5, pad="0")
        centred_label(hud, "PRESS A", y=1)

    def update(self):
        if joy1.just_pressed(A):
            self.switch(Game())


def main():
    return Title()
