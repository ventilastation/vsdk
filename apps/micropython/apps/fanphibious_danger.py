from urandom import choice, randrange, seed
from ventilastation.director import director, stripes
from ventilastation.scene import Scene
from ventilastation.sprites import Sprite

ON_GROUND = 0
ON_TRUNK = 1
JUMPING = 2
ON_GOAL = 3

class Frog(Sprite):

    def __init__(self, scene):
        super().__init__()
        self.scene = scene
        self.set_strip(stripes["bolas.png"])
        self.set_frame(0)
        self.state = ON_GROUND
        
    def step(self):
        if director.is_pressed(director.JOY_LEFT):
            self.set_x(self.x() + 1)
            self.set_frame(self.x() % 8)
        if director.is_pressed(director.JOY_RIGHT):
            self.set_x(self.x() - 1)
            self.set_frame(self.x() % 8)
        if director.is_pressed(director.JOY_UP):
            self.set_y(self.y() + 1)
        if director.is_pressed(director.JOY_DOWN):
            self.set_y(self.y() - 1)

class Trunk(Sprite):
    def __init__(self, scene, speed=1, flotability=1000):
        super().__init__()
        self.scene = scene
        self.set_strip(stripes["trunks.png"])
        self.set_frame(0)
        self.speed = speed
        self.flotability = flotability
        
    def step(self):
        self.set_x(self.x() + self.speed)
        self.flotability -= 1
        if (self.flotability == 0):
            self.disable()

class Enemy(Sprite):
    pass


class FanphibiousDanger(Scene):
    stripes_rom = "fanphibious_danger"

    def on_enter(self):
        super(FanphibiousDanger, self).on_enter()
        self.frame_count = 0
        


        self.frog = Frog(self)
        self.frog.set_x(-16)
        self.frog.set_y(12)

        self.trunk1 = Trunk(self, speed=3, flotability=200)
        self.trunk1.set_x(-16)
        self.trunk1.set_y(32)

        self.trunk2 = Trunk(self, speed=2, flotability=300)
        self.trunk2.set_x(-16)
        self.trunk2.set_y(52)
        
        self.trunk3 = Trunk(self, speed=1)
        self.trunk3.set_x(-16)
        self.trunk3.set_y(72)
        
        self.trunk4 = Trunk(self, speed=2, flotability=150)
        self.trunk4.set_x(-16)
        self.trunk4.set_y(92)
        
    def step(self):
        self.frame_count += 1
        self.frog.step()
 
        self.trunk1.step()
        self.trunk2.step()
        self.trunk3.step()
        self.trunk4.step()

        if director.was_pressed(director.BUTTON_A):
            pass
            
        if director.was_pressed(director.BUTTON_D):
            self.finished()

    def finished(self):
        director.pop()
        raise StopIteration()


def main():
    return FanphibiousDanger()