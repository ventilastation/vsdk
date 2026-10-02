# Trench Run, chapter 5: a trench to fly down, and a score.
import vs2
from vs2.controls import *

LEVEL, TURN_LEFT, TURN_RIGHT = range(3)      # the frames of ship.png
ENEMY_SPEED = 0.5    # depth units per tick, toward the ship
ENEMY_START = 160    # depth at which enemies appear
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
        for i in range(5):
            self.enemies.spawn(x=i * 51, y=ENEMY_START)

        # Bottom of the disc, so the score reads upright.
        self.score_label = self.hud.label("numerals.png", columns=5, x=246, y=1)

        self.score = 0
        self.ticks = 0
        self.show_score()

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

    def move_enemies(self):
        for enemy in self.enemies:
            enemy.y -= ENEMY_SPEED
            enemy.frame = (self.ticks // 6) % enemy.image.frames
            if enemy.y < -enemy.image.height:
                self.enemies.despawn(enemy)      # flew past the ship
                self.score += POINTS
                self.show_score()


def main():
    return Game()
