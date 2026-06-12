from ventilastation.director import stripes
from ventilastation.sprites import Sprite

class Label:
    def __init__(self, text:str, x:int=0, y:int=0, font:str="steel8x8"):
        self.chars = []

        total_len : int = len(text)

        for n in range(total_len):
            s = Sprite()
            s.set_strip(stripes[font+".png"])
            s.set_x(x + (256 - n * 9 + (total_len * 9) // 2) % 256)
            s.set_y(y)
            s.set_frame(10)
            s.set_perspective(2)
            self.chars.append(s)

        self.set_value(text)

    def set_value(self, value):
        for n in range(len(self.chars)):
            self.chars[n].set_frame(0)
        
        for n, l in enumerate(value):
            self.chars[n].set_frame(ord(l))