"""The small game that the VS2 tutorial builds, chapter by chapter.

Trench Run: fly the ship around the rim and dodge the drones that come down the
tunnel at you. Every drone that gets past scores; one that touches the ship ends
the game. See docs/vs2/tutorial/.
"""

from urandom import randrange

import vs2
from vs2.controls import *

LEVEL, TURN_LEFT, TURN_RIGHT = range(3)      # the frames of ship.png
ENEMY_SPEED = 0.5    # depth units per tick, toward the ship
ENEMY_START = 160    # depth at which enemies appear
SPAWN_MS = 900       # time between enemies
POINTS = 10

# The trench's tiles, in the order they appear in trench.png.
PLATE, SEAM, PIPE, WINDOWS, VENT, HAZARD, LIGHTS, CONDUIT = range(8)
TRENCH_COLUMNS = 16  # around the tunnel
TRENCH_ROWS = 16     # along it
PATTERN_ROWS = 6     # the wall repeats every 6 rows, so it can scroll forever


def trench_tile(col, band):
    """Which tile goes at ``col`` in row ``band`` of the repeating pattern."""
    if band == 0:
        return PIPE
    if band == 4:
        return CONDUIT
    if band == 2:
        if col % 4 == 1:
            return WINDOWS
        if col % 4 == 3:
            return VENT
    if band == 5:
        if col % 8 == 2:
            return LIGHTS
        if col % 8 == 6:
            return HAZARD
    return SEAM if col % 2 else PLATE


class Game(vs2.Scene):
    def build(self):
        self.world = self.layer("world", projection=vs2.TUNNEL)
        self.hud = self.layer("hud", projection=vs2.HUD)

        # The trench wall: dark plating all the way round, with a few lit
        # structures. Its pattern repeats every PATTERN_ROWS rows.
        self.ground = self.world.tilemap(
            "trench.png", columns=TRENCH_COLUMNS, rows=TRENCH_ROWS,
            view_width=256, view_height=160)
        self.draw_trench()

        self.ship = self.world.sprite("ship.png", x=128, y=0)
        self.enemies = self.world.sprite_pool("enemy.png", count=16)

        # Bottom of the disc, so the score reads upright.
        self.score_label = self.hud.label("numerals.png", columns=5, x=246, y=1)

        self.score = 0
        self.ticks = 0
        self.show_score()
        self.call_later(SPAWN_MS, self.spawn_enemy)

    def draw_trench(self):
        for row in range(TRENCH_ROWS):
            for col in range(TRENCH_COLUMNS):
                self.ground[col, row] = trench_tile(col, row % PATTERN_ROWS)

    def show_score(self):
        self.score_label.set_number(self.score, width=5, pad="0")

    def update(self):
        self.ticks += 1

        if joy1.held(LEFT):
            self.ship.x = (self.ship.x - 1) % vs2.display.width
            self.ship.frame = TURN_LEFT
        elif joy1.held(RIGHT):
            self.ship.x = (self.ship.x + 1) % vs2.display.width
            self.ship.frame = TURN_RIGHT
        else:
            self.ship.frame = LEVEL

        # Scroll the wall toward the ship. After one whole pattern the picture
        # is the same again, so the view can wrap without rewriting any cells.
        pattern_height = PATTERN_ROWS * self.ground.tile_height
        self.ground.view_y = (self.ticks // 2) % pattern_height

        self.move_enemies()
        if self.ship.first_overlap(self.enemies):
            vs2.audio.sound("boom")
            return self.switch(GameOver(self.score))

    def move_enemies(self):
        for enemy in self.enemies:
            enemy.y -= ENEMY_SPEED
            enemy.frame = (self.ticks // 6) % enemy.image.frames
            if enemy.y < -enemy.image.height:
                self.enemies.despawn(enemy)      # flew past the ship
                self.score += POINTS
                self.show_score()

    def spawn_enemy(self):
        self.enemies.spawn(x=randrange(vs2.display.width), y=ENEMY_START)
        self.call_later(SPAWN_MS, self.spawn_enemy)


def centred_label(layer, text, y):
    """A label for ``text``, centred on the bottom of the disc, where it reads
    upright. steel8x8.png is a full CP437 font, 8 columns per character."""
    label = layer.label("steel8x8.png", columns=len(text), x=0, y=y, text=text)
    label.x = -(len(text) * label.image.width) // 2
    return label


class Title(vs2.Scene):
    def build(self):
        hud = self.layer("hud", projection=vs2.HUD)
        centred_label(hud, "TRENCH RUN", y=1)
        centred_label(hud, "PRESS A", y=20)

    def update(self):
        if joy1.just_pressed(A):
            self.switch(Game())


class GameOver(vs2.Scene):
    def __init__(self, score):
        vs2.Scene.__init__(self)
        self.score = score

    def build(self):
        hud = self.layer("hud", projection=vs2.HUD)
        centred_label(hud, "GAME OVER", y=1)
        score = hud.label("numerals.png", columns=5, x=246, y=20)
        score.set_number(self.score, width=5, pad="0")
        centred_label(hud, "PRESS A", y=28)

    def update(self):
        if joy1.just_pressed(A):
            self.switch(Game())


def main():
    return Title()
