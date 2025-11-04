from urandom import choice, randrange, seed
from ventilastation.director import director, stripes
from ventilastation.scene import Scene
from ventilastation.sprites import Sprite

# Coordinate scaling constants (for fixed point calculations)
SCALE_FACTOR = 256
MAX_COORD = 256
MAX_SCALED_COORD = SCALE_FACTOR * MAX_COORD

# Frog states
ON_GROUND = 0
ON_RING = 1
JUMPING = 2
ON_GOAL = 4
ON_WATER = 8

# Frog's face orientation
DIR_FORWARD = 1
DIR_BACKWARD = -1

# Frog jumping constants
MAX_JUMPING_FRAME = 10

# Distance between rings
RINGS_DISTANCE = 20

class Ring:
    
    def __init__(self, y=0, speed=0):

        self.y = y
        self.speed = speed
        self.object_stack = []

    def insert(self, floating_object, x=None):
        self.object_stack.append(floating_object)
        floating_object.sprite.set_y(self.y)
        if x is not None:
            floating_object.sprite.set_x(x)

    def step(self):
        
        for object in self.object_stack:
            # Drag floating objects at ring's speed
            object.sprite.set_scaled_x(object.sprite.scaled_x() + self.speed)


class FloatingObject:

    def __init__(self, x=0, sprite=None, buoyancy=None):

        self.sprite = sprite
        self.sprite.set_scaled_x(x * SCALE_FACTOR)
        self.buoyancy = buoyancy
        self.carrying_stack = []
    
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
        self.set_strip(stripes["frog16d.png"])
        self.set_frame(0)
        self.state = ON_GROUND
        
        self.speed = 0
        self.orientation = DIR_FORWARD
        self.jumping_frame = 0
        self.jumping_speed = RINGS_DISTANCE // MAX_JUMPING_FRAME * SCALE_FACTOR
        self.ring = 0
        self.next_ring = 1

    def step(self):
        self.set_scaled_x(self._scaled_x + self.speed)

        
class Trunk(MySprite):
    def __init__(self, scene):
        super().__init__()
        self.scene = scene
        self.set_strip(stripes["trunk32.png"])
        self.set_frame(0)
        

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

        # Create Frog sprite
        self.frog = Frog(self)
        self.frog.set_scaled_x(-16*SCALE_FACTOR)
        self.frog.set_scaled_y(16*SCALE_FACTOR)

        # Create floating objects' sprites
        # TODO: programmatically generate more than one object per ring
        self.trunks = [Trunk(self) for i in range(6)]
        
        # Create background sprite ("swamp")
        self.swamp = Swamp(self)

        # Random ring's speeds
        # minimum = 0, maximum = 2 pixels per frame (512 / 256)
        rings_speed = [randrange(-256, 256, 16) for i in range(3)]

        # Create "rings" to contain floating objects
        self.rings = [Ring(y=36+i*RINGS_DISTANCE, 
                           speed=rings_speed[i]) for i in range(3)]
        
        # Put one floating object in each ring
        # TODO: put more than one object per ring
        for i in range(3):
            # Put a "trunk"
            floating_object = FloatingObject(x=randrange(16, 112, 16),
                                             sprite=self.trunks[2*i])
            self.rings[i].insert(floating_object)
            floating_object = FloatingObject(x=randrange(144, 240, 16),
                                             sprite=self.trunks[2*i + 1])
            self.rings[i].insert(floating_object)
            """ floating_object = FloatingObject(x=randrange(165, 235, 10),
                                             sprite=self.trunks[3*i + 2])
            self.rings[i].insert(floating_object) """
            

    def step(self):
        
        self.frame_count += 1

        # ======================== #
        #      PROCESS INPUTS      #
        # ======================== #
        
        # Button D EXITS the game
        if director.was_pressed(director.BUTTON_D):
            self.finished()

        # Joystick controls frog's MOVEMENT and ORIENTATION
        if director.is_pressed(director.JOY_LEFT):
            if self.frog.state == ON_GROUND:
                self.frog.set_scaled_x(self.frog.scaled_x() + SCALE_FACTOR)
                print("Moving LEFT on GROUND.")
            else:
                print("Moving LEFT on FLOATING OBJECT.")

        if director.is_pressed(director.JOY_RIGHT):
            if self.frog.state == ON_GROUND:
                self.frog.set_scaled_x(self.frog.scaled_x() - SCALE_FACTOR)
                print("Moving RIGHT on GROUND.")
            else:
                print("Moving RIGHT on FLOATING OBJECT.")

        if director.is_pressed(director.JOY_UP):
            self.frog.orientation = DIR_FORWARD
            self.frog.set_frame(0)
            print("Frog is facing FORWARD.")

        if director.is_pressed(director.JOY_DOWN):
            self.frog.orientation = DIR_BACKWARD
            self.frog.set_frame(2)
            print("Frog is facing BACKWARD.")

        # Button A makes the frog JUMP
        if director.was_pressed(director.BUTTON_A):
            if self.frog.state != JUMPING:
                if (self.frog.state != ON_GROUND) or (self.frog.orientation == DIR_FORWARD):
                    self.frog.state = JUMPING
                    print("Frog is JUMPING.")
                    self.frog.set_frame(self.frog.frame() + 1)
                    # Frog is aiming to next ring according to its current orientation
                    self.frog.next_ring = self.frog.ring + self.frog.orientation

        # ======================== #
        #       PROCESS STATES     #
        # ======================== #
        if self.frog.state == JUMPING:
            
            # Check if frog landed
            if self.frog.jumping_frame == MAX_JUMPING_FRAME:
                self.frog.jumping_frame = 0
                self.frog.set_frame(self.frog.frame()-1)
                # Decide where the frog has landed
                if self.frog.next_ring == 0:
                    self.frog.state = ON_GROUND
                    print("Frog landed ON GROUND.")
                elif self.frog.next_ring == 4:
                    self.frog.state = ON_GOAL
                    print("Frog landed ON GOAL.")
                else:
                    self.frog.state = ON_RING
                    print("Frog landed ON RING.")

                self.frog.ring = self.frog.next_ring

                if self.frog.state == ON_GROUND or self.frog.state == ON_GOAL:
                    self.frog.speed = 0
                else:
                    # Check if frog landed on a floating object or water
                    dummy_state = ON_WATER
                    
                    for floating_object in self.rings[self.frog.ring - 1].object_stack:
                        if self.frog.collision((floating_object.sprite,)) is not None:
                            dummy_state = ON_RING
                            break

                    self.frog.state = dummy_state

                    if dummy_state == ON_WATER:
                        print("Frog is ON WATER.")
                        self.frog.speed = 0
                    else:
                        self.frog.speed = self.rings[self.frog.ring - 1].speed
                        print("Frog is ON FLOATING OBJECT.")


            else:
                # Animate frog while jumping
                self.frog.set_scaled_y(self.frog.scaled_y() +
                                       self.frog.orientation * self.frog.jumping_speed)
                self.frog.jumping_frame += 1                

        # Animate frog
        self.frog.step()

        # Animate things on rings (except frog)
        for ring in self.rings:
            ring.step()
        

    def finished(self):
        director.pop()
        raise StopIteration()


def main():
    return FanphibiousDanger()