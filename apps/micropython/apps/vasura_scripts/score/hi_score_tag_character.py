from utime import ticks_ms, ticks_diff, ticks_add

from ventilastation.director import stripes
from ventilastation.sprites import Sprite

class HiScoreTagCharacter(Sprite):
    def __init__(self, x:int, y:int):
        super().__init__()
        
        #Setup
        self.allowed_characters : str = "ABCDEFGHIJKLMNOPQRSTUVWXYZ 0123456789"
        self.blink_delay : int = 200
        self.is_blinking : bool = False
        self.next_blink_update_time : int = -1

        self.set_strip(stripes["charset.png"])
        self.set_x(x)
        self.set_y(y)
        self.set_perspective(2)

        self.selected_index : int = 0

        self.set_frame(ord("_"))

    
    def step(self):        
        if (ticks_diff(self.next_blink_update_time, ticks_ms())) <= 0:
            self.is_blinking = not self.is_blinking
            self.next_blink_update_time = ticks_add(ticks_ms(), self.blink_delay)

            if self.is_blinking:
                self.disable()
            else:
                self.set_frame(ord(self.allowed_characters[self.selected_index]))
    
    def select(self):
        self.set_frame(ord(self.allowed_characters[0]))
        self.next_blink_update_time = ticks_add(ticks_ms(), self.blink_delay)
    
    def deselect(self):
        #TODO reproducir sonido
        self.is_blinking = False
        self.set_frame(ord(self.allowed_characters[self.selected_index]))

    def increase_index(self):
        #TODO reproducir sonido
        self.selected_index = (self.selected_index + 1) % len(self.allowed_characters)

        if not self.is_blinking:
            self.set_frame(ord(self.allowed_characters[self.selected_index]))

    def decrease_index(self):
        #TODO reproducir sonido
        self.selected_index = len(self.allowed_characters) - 1 if self.selected_index == 0 else self.selected_index - 1
        
        if not self.is_blinking:
            self.set_frame(ord(self.allowed_characters[self.selected_index]))

    def get_char(self):
        return self.allowed_characters[self.selected_index]
        