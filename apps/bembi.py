from director import director
from scene import Scene
from sprites import Sprite

def make_me_a_planet(n):
    planet = Sprite()
    planet.set_strip(n)
    planet.set_perspective(0)
    planet.set_x(0)
    planet.set_y(0)
    return planet

class Bembidiona(Scene):

    def on_enter(self):
        self.pollitos = Sprite()
        self.pollitos.set_x(-32)
        self.pollitos.set_y(0)
        self.pollitos.set_strip(43)
        self.pollitos.set_frame(0)
        self.pollitos.set_perspective(2)
        self.animation_frames = 0

        self.jere = make_me_a_planet(44)
        self.jere.set_y(255)
        self.jere.set_frame(0)
        director.music_play(b"piostart")

    def step(self):
        self.animation_frames += 1
        pf = (self.animation_frames // 4) % 5
        self.pollitos.set_frame(pf)

        if director.was_pressed(director.BUTTON_D) or director.timedout:
            self.finished()

    def finished(self):
        director.pop()
        raise StopIteration()
