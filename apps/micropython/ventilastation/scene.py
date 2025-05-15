import utime
import sys

from ventilastation import sprites
from ventilastation import povdisplay

class Scene:
    keep_music = False
    images_module = None

    def __init__(self):
        self.pending_calls = []

    def load_images(self):
        if self.images_module:
            full_modulename = "apps.images." + self.images_module
            module = __import__(full_modulename, globals, locals, [self.images_module])
            self.strips = module.strips.__dict__[self.images_module]

            povdisplay.set_palettes(module.palette_pal)
            for n, strip in enumerate(module.all_strips):
                sprites.set_imagestrip(n, strip)

            if full_modulename in sys.modules:
                del sys.modules[full_modulename]


    def on_enter(self):
        self.load_images()

    def on_exit(self):
        pass

    def call_later(self, delay, callable):
        when = utime.ticks_add(utime.ticks_ms(), delay)
        self.pending_calls.append((when, callable))
        self.pending_calls.sort()

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
