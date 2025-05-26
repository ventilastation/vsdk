from urandom import choice, randrange, seed
from ventilastation.director import director, stripes
from ventilastation.scene import Scene
from ventilastation.sprites import Sprite


class Tvnel(Scene):
    stripes_rom = "tvnel"

    def on_enter(self):
        super().on_enter()
        self.walls = []
        for n in range(12):
            wall = Sprite()
            wall.set_perspective(0)
            wall.set_x(0)
            wall.set_y(240-8*n)
            wall.set_strip(stripes["bricks.png"])
            wall.set_frame(0)
            self.walls.append(wall)

        self.step_counter = 0


    def step(self):
        self.step_counter = (self.step_counter + 1) % 2
    
        if self.step_counter == 0:
            for w in self.walls:
                new_y = w.y() + 1
                if new_y > 240:
                    new_y = 240 - 8 * 12
                w.set_y(new_y)

        if director.was_pressed(director.BUTTON_A):
            director.sound_play(b"vyruss/shoot1")
            
        if director.was_pressed(director.BUTTON_D):
            self.finished()

    def finished(self):
        director.pop()
        raise StopIteration()


def main():
    return Tvnel()