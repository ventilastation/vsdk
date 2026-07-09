import gc
import io
import struct
import sys
import uos
import utime

from ventilastation import settings
from ventilastation import api_guard
from ventilastation.platforms import create_platform
from ventilastation.runtime import (
    RuntimeContext,
    clear_runtime,
    get_director,
    get_platform,
    peek_runtime,
    set_runtime,
)

DEBUG = False
INPUT_TIMEOUT = 30 * 1000  # after 30s without input, show the how-to-play attract screens
PIXELS = 54
stripes = {}
TRACE_AUTO_GC_FRAME = 32


class _DirectorProxy:
    """Module-level handle that always resolves to the configured Director.

    Lets app code do `from ventilastation.director import director` once,
    even though the Director itself is created later by configure_runtime().
    """

    def __getattr__(self, name):
        return getattr(get_director(), name)


class _CommsProxy:
    def receive(self, bufsize):
        return get_platform().comms.receive(bufsize)

    def send(self, line, data=b""):
        return get_platform().comms.send(line, data)

    def was_new_connection(self):
        c = get_platform().comms
        if hasattr(c, 'was_new_connection'):
            return c.was_new_connection()
        return False


director = _DirectorProxy()
comms = _CommsProxy()


class Director:
    # joy1 bit layout (matches wire protocol and config.h):
    JOY_LEFT  = 0x01
    JOY_RIGHT = 0x02
    JOY_UP    = 0x04
    JOY_DOWN  = 0x08
    BUTTON_A  = 0x10
    BUTTON_B  = 0x20
    BUTTON_C  = 0x40
    BUTTON_D  = 0x80   # mirrored from extra bit 0; backward-compat for existing games

    # joy2 — same bit layout as joy1
    JOY2_LEFT  = 0x01
    JOY2_RIGHT = 0x02
    JOY2_UP    = 0x04
    JOY2_DOWN  = 0x08
    BUTTON2_A  = 0x10
    BUTTON2_B  = 0x20
    BUTTON2_C  = 0x40

    # extra buttons (7 available; bit 0 is the physical BUTTON_D)
    EXTRA_BTN_0 = 0x01
    EXTRA_BTN_1 = 0x02
    EXTRA_BTN_2 = 0x04
    EXTRA_BTN_3 = 0x08
    EXTRA_BTN_4 = 0x10
    EXTRA_BTN_5 = 0x20
    EXTRA_BTN_6 = 0x40

    def __init__(self, platform):
        self.platform = platform
        self.scene_stack = []
        self.buttons = 0
        self.last_buttons = 0
        self.buttons2 = 0
        self.last_buttons2 = 0
        self.extra_buttons = 0
        self.last_extra_buttons = 0
        self.last_player_action = utime.ticks_ms()
        self.timedout = False
        self.romdata = None
        self.palette_data = None

        if getattr(platform, "disable_gc", False):
            gc.disable()
        else:
            gc.enable()
            gc.collect()
        self.platform.sprites.reset_sprites()

    def _report_exception(self, error, phase=None, scene=None):
        try:
            buf = io.StringIO()
            sys.print_exception(error, buf)
            details = buf.getvalue()
        except Exception:
            details = str(error) + "\n"
        if phase or scene is not None:
            scene_name = scene.__class__.__name__ if scene is not None else "UnknownScene"
            details = "Scene.%s failed in %s\n\n%s" % (phase or "lifecycle", scene_name, details)
        content = details.encode("utf-8")
        self.report_traceback(content)

    def _dispatch_control(self, cmd_line):
        """Handle a text control command received on the control port (port 5006)."""
        parts = cmd_line.split()
        if not parts:
            return
        cmd = parts[0]
        if cmd == "ota_start":
            base_url = parts[1] if len(parts) > 1 else ""
            if not base_url:
                print("director: ota_start missing URL")
                return
            print("director: OTA requested from", base_url, "— rebooting into OTA mode")
            # Write the request and reboot so OTA runs before the GPU task starts.
            # Running WiFi while the GPU task holds the SPI bus causes a core crash.
            try:
                with open("/ota_request", "w") as _f:
                    _f.write(base_url)
            except Exception as _e:
                print("director: failed to write ota_request:", _e)
                return
            import machine
            machine.reset()
        else:
            print("director: unknown control command:", cmd_line)

    def _enter_scene(self, scene):
        api_guard.begin_app(
            getattr(scene, "_vs_api_slug", None),
            getattr(scene, "_vs_declared_api", None),
        )
        scene._vs_entered = False
        try:
            scene.on_enter()
        except Exception as error:
            self._report_exception(error, "on_enter", scene)
            raise
        scene._vs_entered = True

    def _exit_scene(self, scene):
        try:
            scene.on_exit()
        except Exception as error:
            self._report_exception(error, "on_exit", scene)
            raise

    def _enter_top_scene(self):
        """Enter the scene on top of the stack; on failure pop it and try to
        re-enter the scene below (popping that one too if it also fails),
        then re-raise."""
        scene = self.scene_stack[-1]
        self.platform.sprites.reset_sprites()
        gc.collect()
        try:
            self._enter_scene(scene)
        except Exception:
            self.scene_stack.pop()
            self.platform.sprites.reset_sprites()
            if self.scene_stack:
                try:
                    gc.collect()
                    self._enter_scene(self.scene_stack[-1])
                except Exception:
                    self.scene_stack.pop()
            raise

    def push(self, scene):
        previous = self.scene_stack[-1] if self.scene_stack else None
        if previous:
            self._exit_scene(previous)
        self.scene_stack.append(scene)
        self._enter_top_scene()

    def pop(self):
        scene = self.scene_stack.pop()
        self._exit_scene(scene)
        if not scene.keep_music:
            self.music_off()
        self.platform.sprites.reset_sprites()
        gc.collect()
        if self.scene_stack:
            self._enter_scene(self.scene_stack[-1])
        return scene

    def is_pressed(self, button):
        return bool(button & self.buttons)

    def was_pressed(self, button):
        return bool(button & self.buttons) and not bool(button & self.last_buttons)

    def was_released(self, button):
        return not bool(button & self.buttons) and bool(button & self.last_buttons)

    def is_pressed2(self, button):
        return bool(button & self.buttons2)

    def was_pressed2(self, button):
        return bool(button & self.buttons2) and not bool(button & self.last_buttons2)

    def was_released2(self, button):
        return not bool(button & self.buttons2) and bool(button & self.last_buttons2)

    def is_extra(self, button):
        return bool(button & self.extra_buttons)

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

    def music_play(self, track, loop=False):
        if isinstance(track, str):
            track = track.encode("utf-8")
        line = b"music " + track
        if loop:
            # Host loops the track until stopped/changed; e.g. "music vyruss/track loop".
            line += b" loop"
        self.platform.comms.send(line)

    def music_off(self):
        self.platform.comms.send(b"music off")

    def report_traceback(self, content):
        self.platform.comms.send(b"traceback %d" % len(content), content)

    def _set_streaming_rom_compat(self, romlength, header, offsets_raw, palette_offset, palette_data):
        compat_length = palette_offset + len(palette_data)
        if compat_length > romlength:
            compat_length = romlength
        compat = bytearray(compat_length)
        compat[0:4] = header
        compat[4:4 + len(offsets_raw)] = offsets_raw
        compat[palette_offset:palette_offset + len(palette_data)] = palette_data
        self.romdata = memoryview(compat)

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
            self.palette_data = romfile.read(romlength - palette_offset)
            self._set_streaming_rom_compat(romlength, header, offsets_raw, palette_offset, self.palette_data)
            self.platform.display.set_palettes(self.palette_data)

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

    def _parse_rom_memory(self):
        # Parse a fully-loaded ROM held in self.romdata (a bytes/bytearray
        # memoryview), wiring its palettes and image strips into the display.
        stripes.clear()
        num_stripes, num_palettes = struct.unpack("<HH", self.romdata)
        offsets = struct.unpack_from("<%dL%dL" % (num_stripes, num_palettes), self.romdata, 4)
        stripes_offsets = offsets[:num_stripes]
        palette_offsets = offsets[num_stripes:]

        self.palette_data = self.romdata[palette_offsets[0]:]
        self.platform.display.set_palettes(self.palette_data)

        for n, off in enumerate(stripes_offsets):
            filename_len = struct.unpack_from("B", self.romdata, off)[0]
            filename, w, h, frames, pal = struct.unpack_from("%dsBBBB" % filename_len, self.romdata, off + 1)

            if w == 255:
                w = 256

            image_data = off + 1 + filename_len
            self.platform.sprites.set_imagestrip(n, self.romdata[image_data:image_data + w * h * frames + 4])
            stripes[filename.decode("utf-8")] = n

    def load_rom(self, filename):
        # On the board, ROMs are stored gzip-compressed as "<name>.rom.gz" in the
        # LittleFS image to save flash (see build_micropython_fs.py). If that file
        # exists, inflate the whole ROM into RAM via the `deflate` module and parse
        # it in memory. Otherwise fall through to loading the uncompressed
        # "<name>.rom" (e.g. the desktop emulator reading straight from the repo).
        gz_filename = filename + ".gz"
        try:
            uos.stat(gz_filename)
        except OSError:
            pass
        else:
            import deflate
            romfile = open(gz_filename, "rb")
            try:
                stream = deflate.DeflateIO(romfile, deflate.GZIP)
                try:
                    self.romdata = memoryview(stream.read())
                finally:
                    stream.close()
            finally:
                romfile.close()
            self._parse_rom_memory()
            return

        romlength = uos.stat(filename)[6]
        if not getattr(self.platform, "disable_gc", False):
            self.romdata = None
            self.palette_data = None
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
        self._parse_rom_memory()

    def reset_timeout(self):
        self.last_player_action = utime.ticks_ms()
        self.timedout = False

    def step_once(self):
        if not self.scene_stack:
            return

        scene = self.scene_stack[-1]
        now = utime.ticks_ms()

        if not getattr(scene, "_vs_entered", False):
            self._enter_top_scene()

        val = self.platform.comms.receive(1)
        if val:
            self.buttons = val[0]

        if hasattr(self.platform.comms, "next_joy2"):
            self.buttons2      = self.platform.comms.next_joy2()
            self.extra_buttons = self.platform.comms.next_extra()
            # Mirror EXTRA_BTN_0 → BUTTON_D so existing games work unchanged.
            if self.extra_buttons & self.EXTRA_BTN_0:
                self.buttons |= self.BUTTON_D
            else:
                self.buttons &= ~self.BUTTON_D & 0xFF

        if hasattr(self.platform.comms, "next_command"):
            cmd_line = self.platform.comms.next_command()
            if cmd_line:
                self._dispatch_control(cmd_line)

        try:
            scene.scene_step()
        except StopIteration:
            pass
        except Exception as error:
            self._report_exception(error, "step", scene)
            raise

        if self.last_buttons != self.buttons:
            self.last_player_action = now
            self.last_buttons = self.buttons
        self.last_buttons2      = self.buttons2
        self.last_extra_buttons = self.extra_buttons

        self.timedout = utime.ticks_diff(now, self.last_player_action) > INPUT_TIMEOUT
        self.platform.display.update()
        trace_flags = getattr(self.platform, "trace_flags", 0)
        if trace_flags & TRACE_AUTO_GC_FRAME:
            gc.collect()

    def run(self, should_continue=None):
        while True:
            if should_continue is not None and not should_continue():
                utime.sleep_ms(10)
                continue
            now = utime.ticks_ms()
            next_loop = utime.ticks_add(now, 30)
            self.step_once()

            delay = utime.ticks_diff(next_loop, utime.ticks_ms())
            if delay > 0:
                utime.sleep_ms(delay)


def configure_runtime(platform_name=None, argv=None, environ=None):
    platform = create_platform(platform_name, argv, environ)
    context = RuntimeContext(platform)
    set_runtime(context)
    platform.initialize(settings)
    context.director = Director(platform)
    return context.director


def ensure_runtime(platform_name=None, argv=None, environ=None):
    context = peek_runtime()
    if context is not None and context.director is not None:
        return context.director
    return configure_runtime(platform_name, argv, environ)


def reset_runtime():
    clear_runtime()
