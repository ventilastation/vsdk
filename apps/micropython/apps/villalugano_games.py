from urandom import choice, randrange, seed
from ventilastation.director import director, stripes
from ventilastation.scene import Scene
from ventilastation.sprites import Sprite


class Skater(Sprite):
    def __init__(self, scene):
        super().__init__()
        self.scene = scene
        self.set_strip(stripes["skater.png"])
        self.stopped_at_left()
        self.skating_speed = 2
    
    def step(self):
        self.set_x(self.x() + self.vx)

        if self.vx != 0:
            # moviendo las manos
            nf = self.base_frame + ((self.scene.frame_count // 8) % 2)
            self.set_frame(nf)
                
            if 184-32 < self.x() < 192-32:
                self.stopped_at_right()

            if 64 < self.x() < 64 + 8:
                self.stopped_at_left()

    def set_base_frame(self, base):
        self.set_frame(base)
        self.base_frame = base

    def stopped_at_left(self):
        self.vx = 0
        self.set_x(64)
        self.set_y(4)
        self.set_frame(7)
        self.scene.call_later(500, self.turn_right)

    def turn_right(self):
        self.set_frame(6)
        self.set_y(16)
        self.scene.call_later(200, self.jump_right)

    def jump_right(self):
        self.set_x(64-16)
        self.set_y(24)
        self.set_base_frame(0)
        self.vx = -self.skating_speed

    def stopped_at_right(self):
        self.vx = 0
        self.set_x(192-32)
        self.set_y(4)
        self.set_frame(4)
        self.scene.call_later(500, self.turn_left)

    def turn_left(self):
        self.set_frame(5)
        self.set_y(16)
        self.scene.call_later(200, self.jump_left)

    def jump_left(self):
        self.set_x(192-16)
        self.set_y(24)
        self.set_base_frame(2)
        self.vx = self.skating_speed

class VillaluganoGames(Scene):
    stripes_rom = "villalugano_games"

    def on_enter(self):
        super(VillaluganoGames, self).on_enter()
        self.frame_count = 0
        self.skater = Skater(self)

        self.rampa = Sprite()
        self.rampa.set_strip(stripes["rampa.png"])
        self.rampa.set_x(- self.rampa.width() // 2)
        self.rampa.set_y(16)
        self.rampa.set_frame(0)

        self.cielo = Sprite()
        self.cielo.set_strip(stripes["bluesky.png"])
        self.cielo.set_x(0)
        self.cielo.set_y(255)
        self.cielo.set_perspective(0)
        self.cielo.set_frame(0)

    def step(self):
        self.frame_count += 1
        self.skater.step()

        if director.was_pressed(director.BUTTON_A):
            pass
            
        if director.was_pressed(director.BUTTON_D):
            self.finished()

    def finished(self):
        director.pop()
        raise StopIteration()


def main():
    return VillaluganoGames()