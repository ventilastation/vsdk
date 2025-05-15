import utime

try:
    from ventilastation import wincomms as comms
except Exception as e:
    try:
        from ventilastation import serialcomms as comms
    except Exception:
        from ventilastation import comms
from ventilastation import sprites
import gc
import struct


DEBUG = False
INPUT_TIMEOUT = 15 * 1000  # 62 segundos de inactividad, volver al menu

from ventilastation import povdisplay
PIXELS = 54
povdisplay.init(PIXELS)
povdisplay.set_gamma_mode(1)

try:
    from ventilastation.povdisplay import update
except ImportError:
    update = lambda: None

stripes = {}

class Director:
    JOY_LEFT = 1
    JOY_RIGHT = 2
    JOY_UP = 4
    JOY_DOWN = 8
    BUTTON_A = 16
    BUTTON_B = 32
    BUTTON_C = 64
    BUTTON_D = 128

    def __init__(self):
        self.scene_stack = []
        self.buttons = 0
        self.last_buttons = 0
        self.last_player_action = utime.ticks_ms()
        self.timedout = False
        self.rom_data = None

        gc.disable()
        sprites.reset_sprites()


    def push(self, scene):
        self.scene_stack.append(scene)
        sprites.reset_sprites()
        gc.collect()
        scene.on_enter()

    def pop(self):
        scene = self.scene_stack.pop()
        scene.on_exit()
        if not scene.keep_music:
            self.music_off()
        sprites.reset_sprites()
        if self.scene_stack:
            self.scene_stack[-1].on_enter()
        return scene

    def is_pressed(self, button):
        return bool(button & self.buttons)

    def was_pressed(self, button):
        return bool(button & self.buttons) and not bool(button & self.last_buttons)

    def was_released(self, button):
        return not bool(button & self.buttons) and bool(button & self.last_buttons)

    def sound_play(self, track):
        comms.send(b"sound " + track)

    def music_play(self, track):
        comms.send(b"music " + track)

    def music_off(self):
        comms.send(b"music off")

    def report_traceback(self, content):
        comms.send(b"traceback %d"%len(content), content)

    def load_rom(self, filename):
        self.romdata = memoryview(open(filename, "rb").read())
        stripes.clear()
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
            stripes[filename.decode('utf-8')] = n



    def run(self):
        while True:
            scene = self.scene_stack[-1]
            now = utime.ticks_ms()
            next_loop = utime.ticks_add(now, 30)

            val = comms.receive(1)
            if val:
                self.buttons = val[0]

            try:
                scene.scene_step()
            except StopIteration:
                pass

            if self.last_buttons != self.buttons:
                self.last_player_action = now
                self.last_buttons = self.buttons

            self.timedout = utime.ticks_diff(now, self.last_player_action) > INPUT_TIMEOUT

            # Send the sprite positions to the emulator
            update()

            delay = utime.ticks_diff(next_loop, utime.ticks_ms())
            if delay > 0:
                utime.sleep_ms(delay)


director = Director()
