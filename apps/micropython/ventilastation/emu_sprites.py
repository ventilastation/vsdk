from ventilastation.emu_spritelib import *
from ventilastation import romformat

DISABLED_FRAME = 255
sprite_num = 1


def new_sprite():
    global sprite_num
    sprite = get_sprite(sprite_num)
    sprite_num += 1
    return sprite

def reset_sprites():
    for n in range(0, 100):
        sp = get_sprite(n)
        sp.frame = DISABLED_FRAME
        sp.image_strip = 4
        sp.x = 0
        sp.y = 0
        sp.perspective = 1
    global sprite_num
    sprite_num = 1


class Sprite:
    def __init__(self, replacing=None):
        if replacing:
            self._sprite = replacing._sprite    
        else:
            self._sprite = new_sprite()
        self.set_frame(DISABLED_FRAME)
        self.set_x(0)
        self.set_y(0)
        self.set_perspective(True)

    def disable(self):
        self.set_frame(DISABLED_FRAME)

    def x(self):
        return self._sprite.x
    
    def set_x(self, value):
        self._sprite.x = value

    def y(self):
        return self._sprite.y
    
    def set_y(self, value):
        self._sprite.y = value

    def _size(self):
        strip = stripes.get(self._sprite.image_strip)
        if strip is None:
            return 0, 0
        width, height, _frames, _palette = romformat.decode_header(strip)
        return width, height

    def width(self):
        # V1 games have always been told a full-circle (256 wide) image is
        # 255 wide, as on the console (sprites.c), and lay out with that.
        return min(self._size()[0], 255)

    def height(self):
        return self._size()[1]

    def set_strip(self, strip_number):
        self._sprite.image_strip = strip_number
    
    def frame(self):
        return self._sprite.frame
    
    def set_frame(self, value):
        self._sprite.frame = value

    def set_perspective(self, value):
        self._sprite.perspective = value

    def perspective(self):
        return self._sprite.perspective

    def collision(self, targets):
        def intersects(x1, w1, x2, w2):
            delta = min(x1, x2)
            x1 = (x1 - delta + 128) % 256
            x2 = (x2 - delta + 128) % 256
            return x1 < x2 + w2 and x1 + w1 > x2

        for target in targets:
            other = target
            # Disabled sprites never collide, as on the console (sprites.c).
            if other.frame() == DISABLED_FRAME:
                continue
            width, height = self._size()
            other_width, other_height = other._size()
            if (intersects(self.x(), width, other.x(), other_width) and
                intersects(self.y(), height, other.y(), other_height)):
                return target
