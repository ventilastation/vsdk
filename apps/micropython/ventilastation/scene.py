import utime
import sys

from ventilastation.director import director
from ventilastation import povdisplay

class Scene:
    keep_music = False
    stripes_rom = None

    def __init__(self):
        self.pending_calls = []

    def load_images(self):
        if self.stripes_rom:            
            filename = "roms/" + self.stripes_rom + ".rom"
            director.load_rom(filename)

    def on_enter(self):
        self.load_images()

    def on_exit(self):
        pass

    def call_later(self, delay, callable):
        when = utime.ticks_add(utime.ticks_ms(), delay)
        self.pending_calls.append((when, callable))
        self.pending_calls.sort(key=lambda t: t[0])

    def scene_step(self):
        self.step()
        now = utime.ticks_ms()
        while self.pending_calls:
            when, callable = self.pending_calls[0]
            if utime.ticks_diff(when, now) <= 0:
                self.pending_calls.pop(0)
                callable()
            else:
                break

    def step(self):
        pass
