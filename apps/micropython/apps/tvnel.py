from urandom import choice, randrange, seed
from ventilastation.director import director, stripes
from ventilastation.scene import Scene
from ventilastation.sprites import Sprite


TUNNEL_COLS = 8
TUNNEL_ROWS = 11
# TUNNEL_ROWS = 5
TILE_WIDTH = 32
TILE_HEIGHT = 16
TUNNEL_START = 8

COLS_CENTERS = [
    int(TILE_WIDTH * (c - TUNNEL_COLS / 2 + 0.5)) for c in range(TUNNEL_COLS)
]


def make_me_a_planet(strip):
    planet = Sprite()
    planet.set_strip(strip)
    planet.set_perspective(0)
    planet.set_x(0)
    planet.set_y(255)
    return planet


class ScoreBoard:
    def __init__(self):
        self.chars = []
        for n in range(9):
            s = Sprite()
            s.set_strip(stripes["numerals.png"])
            s.set_x(110 + n * 4)
            s.set_y(0)
            s.set_frame(10)
            s.set_perspective(2)
            self.chars.append(s)

        self.setscore(0)

    def setscore(self, value):
        for n, l in enumerate("%05d" % value):
            v = ord(l) - 0x30
            self.chars[n].set_frame(v)


class TvnelGame(Scene):
    stripes_rom = "tvnel"

    def on_enter(self):
        super(TvnelGame, self).on_enter()
        self.scoreboard = ScoreBoard()
        self.hiscore = 0

        self.monchito = Sprite()
        self.monchito.set_x(0)
        self.monchito.set_y(24)
        self.monchito.set_strip(stripes["FallingTembac.png"])
        self.monchito.set_frame(0)
        self.monchito.set_perspective(1)
        self.running_frame = 0
        self.verSpeed = 2
        self.horSpeed = 4

        self.planet = make_me_a_planet(stripes["bottom.png"])
        self.planet.set_frame(0)

        self.fondos = {}
        for x in range(TUNNEL_COLS):
            for y in range(TUNNEL_ROWS):
                sf = Sprite()
                self.fondos[(x, y)] = sf
                sf.set_strip(stripes["moregrass.png"])
                # sf.set_strip(stripes["bricks.png"])
                # sf.set_x(COLS_CENTERS[x] - TILE_WIDTH // 2)"])
                sf.set_x(x * TILE_WIDTH)
                sf.set_y(y * TILE_HEIGHT)
                print(sf.y())
                sf.set_perspective(1)
                sf.set_frame(randrange(3))

        self.fallSpeed = 1
        self.intermediateFramesFallSpeed = 4
        self.intermediateFramesFallSpeedCounter = 0

    def animar_paisaje(self):
        for f in self.fondos.values():
            fy = f.y()
            fx = f.x()
            if fy > 0:
                f.set_y(fy - self.fallSpeed)
                # f.set_x(fx-1)
            else:
                f.set_y(TUNNEL_ROWS * (TILE_HEIGHT - 1))
                f.set_frame(randrange(3))

    def step(self):
        self.hiscore += 2
        if self.intermediateFramesFallSpeedCounter > self.intermediateFramesFallSpeed:
            self.animar_paisaje()
            self.scoreboard.setscore(self.hiscore)
            self.intermediateFramesFallSpeedCounter = 0
        else:
            self.intermediateFramesFallSpeedCounter += 1

        self.running_frame += 1
        pf = (self.running_frame // 4) % 4
        self.monchito.set_frame(pf)

        if director.is_pressed(director.JOY_UP):
            if self.intermediateFramesFallSpeed > -2:
                self.intermediateFramesFallSpeed -= 1
                self.hiscore += 5
                self.scoreboard.setscore(self.hiscore)
                print(self.intermediateFramesFallSpeed)

        if director.is_pressed(director.JOY_DOWN):
            if self.intermediateFramesFallSpeed < 4:
                self.intermediateFramesFallSpeed += 1
                self.hiscore += 1
                self.scoreboard.setscore(self.hiscore)
                print(self.intermediateFramesFallSpeed)

        """
        if director.is_pressed(director.JOY_UP):
            mony = self.monchito.y()
            #if(mony < 19):
            #if(mony < 40):
            self.monchito.set_y(mony + self.verSpeed);
            print(self.monchito.y() );

        if director.is_pressed(director.JOY_DOWN):
            #self.fallSpeed = 1
            mony = self.monchito.y()
            #if(mony > 0):
            self.monchito.set_y(mony - self.verSpeed);
            print(self.monchito.y() );
        """

        if director.is_pressed(director.JOY_LEFT):
            monx = self.monchito.x()
            self.monchito.set_x(monx + self.horSpeed)

        if director.is_pressed(director.JOY_RIGHT):
            monx = self.monchito.x()
            self.monchito.set_x(monx - self.horSpeed)

        # Quits the scene
        if director.was_pressed(director.BUTTON_D):
            self.finished()

    def finished(self):
        director.pop()
        raise StopIteration()


def main():
    return TvnelGame()
