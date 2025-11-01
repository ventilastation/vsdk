from random import choice, randrange, seed
from ventilastation.director import director, stripes
from ventilastation.scene import Scene
from ventilastation.sprites import Sprite

# Coordinate scaling constants (for fixed point calculations)
SCALE_FACTOR = 256
MAX_COORD = 256
MAX_SCALED_COORD = SCALE_FACTOR * MAX_COORD

# Frog states
ON_GROUND = 0
ON_TRUNK = 1
JUMPING = 2
ON_GOAL = 3
ON_WATER = 4

# Frog's face direction
DIR_FORWARD = 1
DIR_BACKWARD = -1

# Frog jumping constants
MAX_JUMPING_FRAME = 10

# Distance between rings
RINGS_DISTANCE = 20


class MySprite(Sprite):
    
    def __init__(self):
        super().__init__()
        self._scaled_x = (self.x() * SCALE_FACTOR) % MAX_SCALED_COORD
        self._scaled_y = (self.y() * SCALE_FACTOR) % MAX_SCALED_COORD

    def set_scaled_x(self, scaled_x):
        self._scaled_x = scaled_x % MAX_SCALED_COORD
        new_x = self._scaled_x // SCALE_FACTOR
        if new_x != self.x():
            self.set_x(new_x)
    
    def set_scaled_y(self, scaled_y):
        self._scaled_y = scaled_y % MAX_SCALED_COORD
        new_y = self._scaled_y // SCALE_FACTOR
        if new_y != self.y():
            self.set_y(new_y)

    #@property
    def scaled_x(self):
        return self._scaled_x
    
    #@property
    def scaled_y(self):
        return self._scaled_y


class Frog(MySprite):

    def __init__(self, scene):
        super().__init__()
        self.scene = scene
        self.set_strip(stripes["bolas.png"])
        self.set_frame(0)
        self.state = ON_GROUND
        self.trunk = None
        self.speed = 0
        self.direction = DIR_FORWARD
        self.jumping_frame = 0
        self.jumping_speed = RINGS_DISTANCE // MAX_JUMPING_FRAME * SCALE_FACTOR
        self.ring = 0

    def step(self):
        self.set_scaled_x(self._scaled_x + self.speed)

        
class Trunk(MySprite):
    def __init__(self, scene, speed=100, flotability=1000):
        super().__init__()
        self.scene = scene
        self.set_strip(stripes["trunks.png"])
        self.set_frame(0)
        self.speed = speed
        self.flotability = flotability

        
    def step(self):
        self.set_scaled_x(self._scaled_x + self.speed)

        # self.flotability -= 1
        # if (self.flotability == 0):
        #   self.disable()


class Enemy(Sprite):
    pass

class Swamp(Sprite):
    def __init__(self, scene):
        super().__init__()
        self.scene = scene
        self.set_strip(stripes["estanque.png"])
        self.set_frame(0)

class FanphibiousDanger(Scene):
    stripes_rom = "fanphibious_danger"

    def on_enter(self):
        super(FanphibiousDanger, self).on_enter()
        self.frame_count = 0

        self.frog = Frog(self)
        self.frog.set_scaled_x(-16*SCALE_FACTOR)
        self.frog.set_scaled_y(8*SCALE_FACTOR)


        vel1 = randrange(32, 512, 8)
        
        
        self.trunk1 = Trunk(self, speed=vel1, flotability=2750)
        self.trunk1.set_scaled_x(-16*SCALE_FACTOR)
        self.trunk1.set_scaled_y(32*SCALE_FACTOR)

        vel2 = randrange(32, 512, 8)
        self.trunk2 = Trunk(self, speed=vel2, flotability=3500)
        self.trunk2.set_scaled_x(-16*SCALE_FACTOR)
        self.trunk2.set_scaled_y(52*SCALE_FACTOR)
        
        vel3 = randrange(32, 512, 8)
        self.trunk3 = Trunk(self, speed=vel3)
        self.trunk3.set_scaled_x(-16*SCALE_FACTOR)
        self.trunk3.set_scaled_y(72*SCALE_FACTOR)

        self.trunks = [self.trunk1, self.trunk2, self.trunk3]
        
        self.swamp = Swamp(self)


    def step(self):
        
        self.frame_count += 1

        self.frog.step()

        for trunk in self.trunks:
            trunk.step()
        
        if director.is_pressed(director.JOY_LEFT):
            self.frog.set_scaled_x(self.frog.scaled_x() + SCALE_FACTOR)

        if director.is_pressed(director.JOY_RIGHT):
            self.frog.set_scaled_x(self.frog.scaled_x() - SCALE_FACTOR)

        if director.is_pressed(director.JOY_UP):
            self.frog.direction = DIR_FORWARD
            print("Frog is facing FORWARD.")

        if director.is_pressed(director.JOY_DOWN):
            self.frog.direction = DIR_BACKWARD
            print("Frog is facing BACKWARD.")

        if director.was_pressed(director.BUTTON_A):
            if self.frog.state != JUMPING:
                if self.frog.state != ON_GROUND: 
                    self.frog.state = JUMPING
                    print("Frog is JUMPING.")
                elif self.frog.direction == DIR_FORWARD:
                    self.frog.state = JUMPING
                    print("Frog is JUMPING.")

        if self.frog.state == JUMPING:
            if self.frog.jumping_frame == MAX_JUMPING_FRAME:
                
                self.frog.jumping_frame = 0
                print("Frog is NOT JUMPING")
                print(self.frog.scaled_y() / SCALE_FACTOR)
                
                # TODO: Check if frog is on trunk or water
                target = self.frog.collision([self.trunks[self.frog.ring + self.frog.direction - 1]]) 
                if target is not None:
                    self.frog.state = ON_TRUNK
                    self.frog.speed = target.speed
                    self.frog.trunk = target
                    self.frog.ring += self.frog.direction
                else:
                    self.frog.state = ON_WATER
                    self.frog.speed = 0
                    self.frog.trunk = None
                    self.frog.ring += self.frog.direction
            else:
                # Move frog
                self.frog.set_scaled_y(self.frog.scaled_y() +
                                       self.frog.direction * self.frog.jumping_speed)
                # TODO: Animate jump
                self.frog.jumping_frame += 1
            
        if director.was_pressed(director.BUTTON_D):
            self.finished()

    def finished(self):
        director.pop()
        raise StopIteration()


def main():
    return FanphibiousDanger()