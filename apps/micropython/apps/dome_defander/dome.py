from ventilastation.director import director, stripes
from ventilastation.scene import Scene
from ventilastation.sprites import Sprite

class Dome:
    def __init__(self):
        domo = Sprite()
        domo.set_strip(stripes["domo.png"])
        domo.set_x(0)
        domo.set_y(255)
        domo.set_perspective(0)
        domo.set_frame(0)

        domo2 = Sprite()
        domo2.set_strip(stripes["domo2.png"])
        domo2.set_x(0)
        domo2.set_y(255)
        domo2.set_perspective(0)
        domo2.set_frame(0)
        domo2.disable()

        domo3 = Sprite()
        domo3.set_strip(stripes["domo3.png"])
        domo3.set_x(0)
        domo3.set_y(255)
        domo3.set_perspective(0)
        domo3.set_frame(0)
        domo3.disable()

        domo4 = Sprite()
        domo4.set_strip(stripes["domo4.png"])
        domo4.set_x(0)
        domo4.set_y(255)
        domo4.set_perspective(0)
        domo4.set_frame(0)
        domo4.disable()

        self.dome_sprites = [domo, domo2, domo3, domo4]
        self.sprite_index = 0

    def hit(self):
        self.dome_sprites[self.sprite_index].disable()
        self.sprite_index = self.sprite_index + 1
        self.dome_sprites[self.sprite_index].set_frame(0)

    def reset(self):
        self.dome_sprites[self.sprite_index].disable()
        self.sprite_index = 0
        self.dome_sprites[self.sprite_index].set_frame(0)