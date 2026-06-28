try:
    import utime as _time
except ImportError:
    import time as _time

try:
    import ustruct as struct
except ImportError:
    import struct

try:
    import urandom as random
except ImportError:
    import random

from ventilastation.runtime import get_platform

COLUMNS = 256
PIXELS = 54
SHIP_ROW = 6
SHIP_HALF_WIDTH = 6
FRAME_US = 33333
MOVE_SPEED = 5
STEP_INTERVALS_US = (
    280000,
    240000,
    210000,
    180000,
    155000,
    135000,
)
SECTION_LENGTH_US = 12000000
BG_COLORS = (
    0x00000000,
    0x000022FF,
    0x001100FF,
    0x222200FF,
    0x002222FF,
    0x220022FF,
    0x220000FF,
)
WALL_COLORS = (
    0x000066FF,
    0x006600FF,
    0x444400FF,
    0x004444FF,
    0x440044FF,
    0x660000FF,
)
SHIP_COLOR = 0xFF0000FF
SHIP_GLOW = 0xFF6666FF
SECTION_SOUNDS = (
    b"sound ventilagon/audio/es/linea",
    b"sound ventilagon/audio/es/triangulo",
    b"sound ventilagon/audio/es/cuadrado",
    b"sound ventilagon/audio/es/pentagono",
    b"sound ventilagon/audio/es/ventilagono",
)

BUTTON_LEFT = 1
BUTTON_RIGHT = 2
BUTTON_ANY = 16

_BYTES_PER_FRAME = COLUMNS * PIXELS * 4
_COLOR_BYTES = {}
_BACKGROUND_FRAMES = {}
_COLUMN_BASE_OFFSETS = tuple(column * PIXELS * 4 for column in range(COLUMNS))


def _packed_color(color):
    cached = _COLOR_BYTES.get(color)
    if cached is None:
        cached = struct.pack(">I", color)
        _COLOR_BYTES[color] = cached
    return cached


def _background_frame(color):
    cached = _BACKGROUND_FRAMES.get(color)
    if cached is None:
        cached = _packed_color(color) * (COLUMNS * PIXELS)
        _BACKGROUND_FRAMES[color] = cached
    return cached


def _ticks_us():
    ticks_us = getattr(_time, "ticks_us", None)
    if ticks_us is not None:
        return ticks_us()
    perf_counter = getattr(_time, "perf_counter", None)
    if perf_counter is not None:
        return int(perf_counter() * 1000000)
    return 0


def _ticks_diff(end, start):
    ticks_diff = getattr(_time, "ticks_diff", None)
    if ticks_diff is not None:
        return ticks_diff(end, start)
    return end - start


def _randrange(start, stop=None):
    if stop is None:
        return random.randrange(start)
    return random.randrange(start, stop)


class VentilagonEmulator:
    def __init__(self):
        self.queue = []
        self.active = False
        self.idle = True
        self.buttons = 0
        self.ship_angle = COLUMNS // 2
        self.last_frame_at = 0
        self.last_step_at = 0
        self.started_at = 0
        self.section = 0
        self.section_started_at = 0
        self.step_interval_us = STEP_INTERVALS_US[0]
        self.obstacles = []
        self.game_over = False
        self.frame_bytes = bytearray(_BYTES_PER_FRAME)
        self.frame_dirty = False

    def _set_led(self, column, row, color):
        offset = _COLUMN_BASE_OFFSETS[column] + row * 4
        self.frame_bytes[offset:offset + 4] = _packed_color(color)

    def _fill_frame(self, color):
        self.frame_bytes[:] = _background_frame(color)

    def enter(self):
        self.active = True
        self.idle = False
        now = _ticks_us()
        self.last_frame_at = now
        self.last_step_at = now
        self.started_at = now
        self.section_started_at = now
        self.section = 0
        self.step_interval_us = STEP_INTERVALS_US[0]
        self.ship_angle = COLUMNS // 2
        self.buttons = 0
        self.game_over = False
        self.obstacles = []
        self.frame_dirty = True
        self._seed_board()
        self.queue = [
            b"sound ventilagon/audio/es/empeza",
            b"music ventilagon/music/superventilagon-track",
            b"arduino start",
        ]
        self._queue_frame()

    def exit(self):
        self.active = False
        self._clear_native_frame()
        self.queue = [
            b"musicstop",
            b"arduino stop",
        ]

    def received(self, buttons):
        self.buttons = int(buttons) & 0xFF
        if self.game_over and (self.buttons & BUTTON_ANY):
            self.enter()

    def is_idle(self):
        return self.idle

    def sending(self):
        if self.queue:
            return self.queue.pop(0)
        if not self.active:
            return None
        self._tick()
        if self.queue:
            return self.queue.pop(0)
        return None

    def _seed_board(self):
        self.obstacles = []
        for idx in range(8):
            self.obstacles.append(self._make_obstacle(PIXELS - 4 - idx * 6))

    def _make_obstacle(self, row):
        width = max(24, 64 - self.section * 5)
        safe_start = _randrange(COLUMNS)
        return {
            "row": row,
            "safe_start": safe_start,
            "safe_end": (safe_start + width) % COLUMNS,
        }

    def _angle_in_gap(self, angle, obstacle):
        start = obstacle["safe_start"]
        end = obstacle["safe_end"]
        if start <= end:
            return start <= angle <= end
        return angle >= start or angle <= end

    def _tick(self):
        now = _ticks_us()
        if self.game_over:
            return

        moved = False
        if self.buttons & BUTTON_LEFT:
            self.ship_angle = (self.ship_angle - MOVE_SPEED) % COLUMNS
            moved = True
        if self.buttons & BUTTON_RIGHT:
            self.ship_angle = (self.ship_angle + MOVE_SPEED) % COLUMNS
            moved = True
        if moved:
            self.idle = False
            self.frame_dirty = True

        section_elapsed = _ticks_diff(now, self.section_started_at)
        if section_elapsed >= SECTION_LENGTH_US:
            if self.section < len(STEP_INTERVALS_US) - 1:
                self.section += 1
                self.step_interval_us = STEP_INTERVALS_US[self.section]
                self.section_started_at = now
                self.queue.append(SECTION_SOUNDS[min(self.section - 1, len(SECTION_SOUNDS) - 1)])
                self.frame_dirty = True

        if _ticks_diff(now, self.last_step_at) >= self.step_interval_us:
            self.last_step_at = now
            self._advance_board()
            self.frame_dirty = True

        if self.frame_dirty:
            self.last_frame_at = now
            self._queue_frame()
            self.frame_dirty = False

    def _advance_board(self):
        new_obstacles = []
        collided = False
        for obstacle in self.obstacles:
            next_row = obstacle["row"] - 1
            if next_row == SHIP_ROW and not self._angle_in_gap(self.ship_angle, obstacle):
                collided = True
            if next_row >= 0:
                obstacle["row"] = next_row
                new_obstacles.append(obstacle)
        self.obstacles = new_obstacles
        while len(self.obstacles) < 8:
            highest = max([ob["row"] for ob in self.obstacles] + [SHIP_ROW + 12])
            self.obstacles.append(self._make_obstacle(min(PIXELS - 1, highest + 6)))
        if collided:
            self._trigger_game_over()

    def _trigger_game_over(self):
        self.game_over = True
        self.idle = True
        self.queue.extend([
            b"musicstop",
            b"sound ventilagon/audio/die",
            b"sound ventilagon/audio/es/perdiste",
            b"arduino attract",
        ])
        self._queue_frame()

    def _queue_frame(self):
        self._fill_frame(BG_COLORS[self.section + 1])

        for obstacle in self.obstacles:
            row = obstacle["row"]
            if row < 0 or row >= PIXELS:
                continue
            color = WALL_COLORS[self.section]
            for column in range(COLUMNS):
                if self._angle_in_gap(column, obstacle):
                    continue
                self._set_led(column, row, color)

        for offset in range(-SHIP_HALF_WIDTH * 2, SHIP_HALF_WIDTH * 2 + 1):
            column = (self.ship_angle + offset) % COLUMNS
            if abs(offset) <= SHIP_HALF_WIDTH:
                color = SHIP_COLOR
            else:
                color = SHIP_GLOW
            self._set_led(column, SHIP_ROW, color)
            if self.game_over and SHIP_ROW + 1 < PIXELS:
                self._set_led(column, SHIP_ROW + 1, color)

        if not self._set_native_frame(self.frame_bytes):
            self.queue.append((b"nativeframe %d" % _BYTES_PER_FRAME, self.frame_bytes))

    def _display(self):
        try:
            return get_platform().display
        except Exception:
            return None

    def _set_native_frame(self, frame_bytes):
        display = self._display()
        setter = getattr(display, "set_native_frame", None)
        if setter is None:
            return False
        try:
            setter(frame_bytes)
            return True
        except Exception:
            return False

    def _clear_native_frame(self):
        display = self._display()
        clearer = getattr(display, "clear_native_frame", None)
        if clearer is None:
            return False
        try:
            clearer()
            return True
        except Exception:
            return False


_emu = VentilagonEmulator()


def enter():
    _emu.enter()


def exit():
    _emu.exit()


def received(buttons):
    _emu.received(buttons)


def sending():
    return _emu.sending()


def is_idle():
    return _emu.is_idle()
