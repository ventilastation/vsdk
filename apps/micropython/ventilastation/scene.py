import utime
import sys
import struct

from ventilastation import sprites
from ventilastation import povdisplay

class Scene:
    keep_music = False
    images_module = None
    stripes_rom = None

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

        if self.stripes_rom:            
            filename = "roms/" + self.stripes_rom + ".rom"
            self.romdata = memoryview(open(filename, "rb").read())
            self.stripes = {}
            num_stripes, num_palettes = struct.unpack("<HH", self.romdata)
            offsets = struct.unpack_from("<%dL%dL" % (num_stripes, num_palettes), self.romdata, 4)
            stripes_offsets = offsets[:num_stripes]
            palette_offsets = offsets[num_stripes:]
            
            povdisplay.set_palettes(self.romdata[palette_offsets[0]:])

            for n, off in enumerate(stripes_offsets):
                filename_len = struct.unpack_from("B", self.romdata, off)[0]
                filename, w, h, frames, pal = struct.unpack_from("%dsBBBB" % filename_len, self.romdata, off + 1)
                
                # special case
                if w == 255:
                    w = 256

                image_data = off + 1 + filename_len
                sprites.set_imagestrip(n, self.romdata[image_data:image_data + w*h*frames + 4])
                self.stripes[filename.decode('utf-8')] = n

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
