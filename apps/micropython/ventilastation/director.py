import gc
import struct
import uos
import utime

from ventilastation import settings
from ventilastation.platforms import create_platform
from ventilastation.runtime import RuntimeContext, clear_runtime, get_platform, set_runtime

DEBUG = False
INPUT_TIMEOUT = 30 * 1000  # 30 segundos de inactividad, mostrar las instrucciones para empezar a jugar
PIXELS = 54
stripes = {}


class _DirectorProxy:
    def __getattr__(self, name):
        return getattr(_director_instance(), name)


class _CommsProxy:
    def receive(self, bufsize):
        return get_platform().comms.receive(bufsize)

    def send(self, line, data=b""):
        return get_platform().comms.send(line, data)


director = _DirectorProxy()
comms = _CommsProxy()


class Director:
    JOY_LEFT = 1
    JOY_RIGHT = 2
    JOY_UP = 4
    JOY_DOWN = 8
    BUTTON_A = 16
    BUTTON_B = 32
    BUTTON_C = 64
    BUTTON_D = 128

    def __init__(self, platform):
        self.platform = platform
        self.scene_stack = []
        self.buttons = 0
        self.last_buttons = 0
        self.last_player_action = utime.ticks_ms()
        self.timedout = False
        self.romdata = None

        if getattr(platform, "disable_gc", False):
            gc.disable()
        else:
            gc.enable()
            gc.collect()
        self.platform.sprites.reset_sprites()

    def push(self, scene):
        if self.scene_stack:
            self.scene_stack[-1].on_exit()
        self.scene_stack.append(scene)
        self.platform.sprites.reset_sprites()
        gc.collect()
        scene.on_enter()

    def pop(self):
        scene = self.scene_stack.pop()
        scene.on_exit()
        if not scene.keep_music:
            self.music_off()
        self.platform.sprites.reset_sprites()
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
        if isinstance(track, str):
            track = track.encode("utf-8")
        self.platform.comms.send(b"sound " + track)

    def notes_play(self, folder, notes):
        if isinstance(folder, str):
            folder = folder.encode("utf-8")
        normalized = []
        for note in notes:
            normalized.append(note.encode("utf-8") if isinstance(note, str) else note)
        self.platform.comms.send(b"notes " + folder + b" " + b";".join(normalized))

    def music_play(self, track):
        if isinstance(track, str):
            track = track.encode("utf-8")
        self.platform.comms.send(b"music " + track)

    def music_off(self):
        self.platform.comms.send(b"music off")

    def report_traceback(self, content):
        self.platform.comms.send(b"traceback %d" % len(content), content)

    def _load_rom_streaming(self, filename, romlength):
        stripes.clear()
        romfile = open(filename, "rb")
        try:
            header = romfile.read(4)
            num_stripes, num_palettes = struct.unpack("<HH", header)
            offsets_size = (num_stripes + num_palettes) * 4
            offsets_raw = romfile.read(offsets_size)
            offsets = struct.unpack("<%dL%dL" % (num_stripes, num_palettes), offsets_raw)
            stripes_offsets = offsets[:num_stripes]
            palette_offsets = offsets[num_stripes:]

            palette_offset = palette_offsets[0]
            romfile.seek(palette_offset)
            self.platform.display.set_palettes(romfile.read(romlength - palette_offset))

            for n, off in enumerate(stripes_offsets):
                romfile.seek(off)
                filename_len = struct.unpack("B", romfile.read(1))[0]
                metadata = romfile.read(filename_len + 4)
                filename_bytes = metadata[:filename_len]
                w = metadata[filename_len]
                h = metadata[filename_len + 1]
                frames = metadata[filename_len + 2]
                width = 256 if w == 255 else w
                stripmap = metadata[filename_len:] + romfile.read(width * h * frames)
                self.platform.sprites.set_imagestrip(n, stripmap)
                stripes[filename_bytes.decode("utf-8")] = n
        finally:
            romfile.close()

    def load_rom(self, filename):
        romlength = uos.stat(filename)[6]
        if not getattr(self.platform, "disable_gc", False):
            self.romdata = None
            self._load_rom_streaming(filename, romlength)
            return

        rombuffer = bytearray(romlength)
        romview = memoryview(rombuffer)
        romfile = open(filename, "rb")
        try:
            try:
                romfile.readinto(romview)
            except (AttributeError, OSError):
                data = romfile.read()
                rombuffer[:len(data)] = data
        finally:
            romfile.close()
        self.romdata = romview
        stripes.clear()
        num_stripes, num_palettes = struct.unpack("<HH", self.romdata)
        offsets = struct.unpack_from("<%dL%dL" % (num_stripes, num_palettes), self.romdata, 4)
        stripes_offsets = offsets[:num_stripes]
        palette_offsets = offsets[num_stripes:]

        self.platform.display.set_palettes(self.romdata[palette_offsets[0]:])

        for n, off in enumerate(stripes_offsets):
            filename_len = struct.unpack_from("B", self.romdata, off)[0]
            filename, w, h, frames, pal = struct.unpack_from("%dsBBBB" % filename_len, self.romdata, off + 1)

            if w == 255:
                w = 256

            image_data = off + 1 + filename_len
            self.platform.sprites.set_imagestrip(n, self.romdata[image_data:image_data + w * h * frames + 4])
            stripes[filename.decode("utf-8")] = n

    def reset_timeout(self):
        self.last_player_action = utime.ticks_ms()
        self.timedout = False

    def step_once(self):
        if not self.scene_stack:
            return

        scene = self.scene_stack[-1]
        now = utime.ticks_ms()

        val = self.platform.comms.receive(1)
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
        self.platform.display.update()

    def run(self):
        while True:
            now = utime.ticks_ms()
            next_loop = utime.ticks_add(now, 30)
            self.step_once()

            delay = utime.ticks_diff(next_loop, utime.ticks_ms())
            if delay > 0:
                utime.sleep_ms(delay)


def _director_instance():
    runtime = director.__dict__.get("_runtime")
    if runtime is None:
        raise RuntimeError("Ventilastation runtime has not been configured")
    return runtime


def configure_runtime(platform_name=None, argv=None, environ=None):
    platform = create_platform(platform_name, argv, environ)
    set_runtime(RuntimeContext(platform))
    platform.initialize(settings)
    runtime_director = Director(platform)
    director._runtime = runtime_director
    return runtime_director


def ensure_runtime(platform_name=None, argv=None, environ=None):
    runtime_director = director.__dict__.get("_runtime")
    if runtime_director is not None:
        return runtime_director
    return configure_runtime(platform_name, argv, environ)


def reset_runtime():
    if "_runtime" in director.__dict__:
        del director._runtime
    clear_runtime()
