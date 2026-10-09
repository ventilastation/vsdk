"""The small game that the VS2 tutorial builds, chapter by chapter.

Trench Run: fly the ship around the rim and dodge the enemies that come down the
tunnel at you. Every enemy that gets past scores; one that touches the ship ends
the game. The best score is kept between runs, and the game speeds up (and gets
busier, in turn) as the score rises. See docs/vs2/tutorial/.
"""

from urandom import randrange

import vs2
from vs2.controls import *

LEVEL, TURN_LEFT, TURN_RIGHT = range(3)      # the frames of ship.png
ENEMY_START = 160    # depth at which enemies appear
POINTS = 10

# How fast the wall scrolls past, in depth units per tick. Enemies sit still in
# the trench, so they come at the ship at the same speed.
START_SPEED = 0.75
MAX_SPEED = 1.5
SPEED_STEP = 0.125

# Milliseconds between enemies.
SPAWN_MS = 900
MIN_SPAWN_MS = 450
SPAWN_STEP = 75

# The game gets harder every STEP_POINTS points, alternately by speeding the
# trench up and by sending enemies more often.
STEP_POINTS = 50
BEST = "best"        # the name the best score is saved under

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

        # x = 0 is the bottom of the disc. A sprite's x is its edge, so back up
        # by half its width to put the ship's centre there.
        self.ship = self.world.sprite("ship.png", y=0)
        self.ship.x = -(self.ship.width // 2)
        self.enemies = self.world.sprite_pool("enemy.png", count=16)

        # Top of the disc, where x = 128. Text up there is upside-down unless it
        # is flipped both ways.
        self.score_label = self.hud.label("numerals.png", columns=5, x=118, y=1,
                                          flip_x=True, flip_y=True)

        self.score = 0
        self.scroll = 0                 # how far the wall has scrolled
        self.ticks = 0
        self.show_score()
        self.get_harder()
        self.call_later(self.spawn_ms, self.spawn_enemy)

    def draw_trench(self):
        for row in range(TRENCH_ROWS):
            for col in range(TRENCH_COLUMNS):
                self.ground[col, row] = trench_tile(col, row % PATTERN_ROWS)

    def show_score(self):
        self.score_label.set_number(self.score, width=5, pad="0")

    def update(self):
        self.ticks += 1

        # +1 for left, -1 for right, 0 for neither (or both held: they cancel).
        # At the bottom of the disc x counts up toward the left.
        steer = joy1.held(LEFT) - joy1.held(RIGHT)
        self.ship.x = (self.ship.x + steer) % vs2.display.width
        if steer > 0:
            self.ship.frame = TURN_LEFT
        elif steer < 0:
            self.ship.frame = TURN_RIGHT
        else:
            self.ship.frame = LEVEL

        # Scroll the wall toward the ship. After one whole pattern the picture
        # is the same again, so the view can wrap without rewriting any cells.
        pattern_height = PATTERN_ROWS * self.ground.tile_height
        self.scroll = (self.scroll + self.speed) % pattern_height
        self.ground.view_y = self.scroll

        if self.move_enemies():
            vs2.audio.sound("boom")
            return self.switch(GameOver(self.score))

    def move_enemies(self):
        """Advance the enemies. Returns True if one touched the ship."""
        for enemy in self.enemies:
            enemy.y -= self.speed
            enemy.frame = (self.ticks // 6) % enemy.image.frames
            if enemy.overlaps(self.ship):
                return True
            if enemy.y < -enemy.image.height:
                self.enemies.despawn(enemy)      # flew past the ship
                self.score += POINTS
                self.show_score()
                self.get_harder()
        return False

    def get_harder(self):
        """Set the pace from the score. The steps alternate: the first, third,
        fifth... make the trench faster, the second, fourth... make the enemies
        come more often, each up to a limit."""
        step = self.score // STEP_POINTS
        self.speed = min(MAX_SPEED, START_SPEED + SPEED_STEP * ((step + 1) // 2))
        self.spawn_ms = max(MIN_SPAWN_MS, SPAWN_MS - SPAWN_STEP * (step // 2))

    def spawn_enemy(self):
        self.enemies.spawn(x=randrange(vs2.display.width), y=ENEMY_START)
        self.call_later(self.spawn_ms, self.spawn_enemy)


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
        best = vs2.saves.load(BEST, 0)
        if best:
            centred_label(hud, "BEST %05d" % best, y=11)
        centred_label(hud, "PRESS A", y=20)

    def update(self):
        if joy1.just_pressed(A):
            self.switch(Game())


class GameOver(vs2.Scene):
    def __init__(self, score):
        vs2.Scene.__init__(self)
        self.score = score
        # Saved once, here, when the game ends. Writing flash is slow, so it is
        # done only when the record is beaten, never while playing.
        self.best = vs2.saves.load(BEST, 0)
        self.new_best = score > self.best
        if self.new_best:
            self.best = score
            vs2.saves.save(BEST, score)

    def build(self):
        hud = self.layer("hud", projection=vs2.HUD)
        centred_label(hud, "NEW BEST!" if self.new_best else "GAME OVER", y=1)
        score = hud.label("numerals.png", columns=5, x=246, y=11)
        score.set_number(self.score, width=5, pad="0")
        centred_label(hud, "PRESS A", y=20)

    def update(self):
        if joy1.just_pressed(A):
            self.switch(Game())


def main():
    return Title()
