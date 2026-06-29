"""Super Ventilagon, ported to MicroPython for the desktop + web emulators.

On the spinning rotor the game is C (hardware/rotor/modules/povdisplay/ventilagon/),
driven by the fan's rotation timing and drawing one LED column at a time. The emulators
have no fan, so this module reimplements the same simulation and (in the render section)
paints the whole 256-column polar frame each tick instead of one column per rotation.

This file is the game *logic* — board, patterns, drift, the state machine, input and
audio triggers — a close port of the C so behavior matches the firmware. The bulky data
tables live in ventilagon_data.py, generated from the C by tools/extract_ventilagon_data.py.

The public API matches what games/alecu/ventilagon_game/code/ventilagon_game.py expects
from the native `ventilagon` C module: enter(), exit(), received(buttons), sending(),
is_idle(), plus tick() which the Scene pumps each frame (the C module loops on its own
rotor task; the emulator has no such task).
"""

try:
    import utime as _time
except ImportError:
    import time as _time

try:
    from random import randrange as _randrange
except ImportError:  # pragma: no cover
    import urandom

    def _randrange(n):
        return urandom.getrandbits(16) % n

from ventilastation import ventilagon_data as _data

# --- constants (ventilagon.h) ---------------------------------------------------------
NUM_COLUMNS = 6
NUM_ROWS = 48
ROW_SHIP = 3
ROW_COLISION = 7
SUBDEGREES = 8192
SUBDEGREES_MASK = 8191
SHIP_COLOR = 0xFF0000FF
HALF_SHIP_WIDTH = 50

# Button bitmask (matches director / ventilagon_rotor.c).
JOY_LEFT = 1
JOY_RIGHT = 2
BUTTON_A = 16

CENTISECONDS = 10 * 1000  # microseconds (state_play.c)
SECTION_DURATIONS = [
    1325 * CENTISECONDS,
    1325 * CENTISECONDS,
    1325 * CENTISECONDS,
    1325 * CENTISECONDS,
    1325 * 2 * CENTISECONDS,
    1325 * 3 * CENTISECONDS,
    1 << 62,  # UINT64_MAX sentinel: the final section never times out by itself
]

# audio.c section_sounds (None where the C had NULL).
SECTION_SOUNDS = [
    None,
    "sound ventilagon/audio/es/linea",
    "sound ventilagon/audio/es/triangulo",
    "sound ventilagon/audio/es/cuadrado",
    "sound ventilagon/audio/es/pentagono",
    "sound ventilagon/audio/es/ventilagono",
    None,
]

# ledbar.c win-state colors (0xRRGGBBAA).
WIN_COLORS = [0x000066FF, 0x006600FF, 0x444400FF, 0x004444FF, 0x440044FF, 0x660000FF]


def _rand(n):
    return _randrange(n)


# --- drift calculators (levels.c) -----------------------------------------------------
def _no_drift(drift_speed):
    return 0


def _slow_drift(drift_speed):
    if _rand(375) < 2:
        if drift_speed == 0:
            drift_speed = -1
    return drift_speed


def _med_drift(drift_speed):
    r = _rand(375)
    if r < 4:
        drift_speed = r - 2
        if drift_speed == 0:
            drift_speed = 2
    return drift_speed


def _high_drift(drift_speed):
    r = _rand(375)
    if r < 6:
        drift_speed = r - 3
        if drift_speed == 0:
            drift_speed = 3
    return drift_speed


def _crazy_drift(drift_speed):
    r = _rand(375)
    if r < 10:
        drift_speed = r - 5
        if drift_speed == 0:
            drift_speed = 5
    return drift_speed


_DRIFT_FNS = {
    "no_drift": _no_drift,
    "slow_drift": _slow_drift,
    "med_drift": _med_drift,
    "high_drift": _high_drift,
    "crazy_drift": _crazy_drift,
}


def _build_levels():
    """Resolve the generated tables into ready-to-use level dicts."""
    levels = []
    for raw in _data.levels:
        pool = [_data.patterns[name] for name in _data.pattern_levels[raw["patterns"]]]
        levels.append(
            {
                "step_delay": raw["step_delay"],
                "block_height": raw["block_height"],
                "rotation_speed": raw["rotation_speed"],
                "song": raw["song"],
                "color": raw["color"],
                "bg1": raw["bg1"],
                "bg2": raw["bg2"],
                "pool": pool,
                "num_patterns": len(pool),
                "drift": _DRIFT_FNS[raw["drift"]],
            }
        )
    return levels


def _now_us():
    ticks_us = getattr(_time, "ticks_us", None)
    if ticks_us is not None:
        return ticks_us()
    return int(_time.perf_counter() * 1000000)


def _ticks_diff(a, b):
    ticks_diff = getattr(_time, "ticks_diff", None)
    if ticks_diff is not None:
        return ticks_diff(a, b)
    return a - b


class _State:
    __slots__ = ("name", "setup", "loop")

    def __init__(self, name, setup, loop):
        self.name = name
        self.setup = setup
        self.loop = loop


class Game:
    """The whole Super Ventilagon simulation, mutable state kept on one object."""

    def __init__(self):
        self.levels = _build_levels()
        self.current_level = self.levels[0]
        self.new_level = 0

        # board (circular buffer of NUM_ROWS 6-bit wall rows)
        self.buffer = [0] * NUM_ROWS
        self.first_row = 0

        # pattern generator
        self.transformation_base = 0
        self.current_height = 0
        self.block_height = 0
        self.row = 0
        self.rows = []
        self.rows_len = 0
        self._value = 0

        # display / ship
        self.nave_pos = 360
        self.nave_calibrate = 0
        self.half_ship_width = HALF_SHIP_WIDTH
        self.drift_pos = 0
        self.drift_speed = 0
        self.calibrating = False
        self.multicolored = False
        self._adjust_n = 0

        # timing (all microseconds on an accumulating monotonic clock)
        self.now = 0
        self._last_ticks = _now_us()
        self.last_step = 0
        self.last_move = 0
        self.last_drift = 0
        self.queued_steps = 0

        # play sections
        self.section = 0
        self.section_init_time = 0
        self.section_duration = 0
        self.paused = False

        # reset / win / credits timers
        self.reset_last_step = 0
        self.counter = 0
        self.win_started = 0
        self.win_last_step = 0
        self.credits_started = 0
        self.creds_last_step = 0
        self.credits_step_delay = 0
        self.step_position = 0

        # input + lifecycle
        self.boton_cw = False
        self.boton_ccw = False
        self.is_idle = False

        # outbound audio/control lines (drained by sending())
        self._send_queue = []

        self._build_states()
        self.current_state = self.resetting_state

    # -- audio / control out (audio.c) -------------------------------------------------
    def serial_send(self, text):
        self._send_queue.append(text if isinstance(text, bytes) else text.encode("latin1"))

    def audio_play(self, command):
        if command is not None:
            self.serial_send(command)

    def audio_play_crash(self):
        self.audio_play("sound ventilagon/audio/die")

    def audio_play_win(self):
        self.audio_play("sound ventilagon/audio/es/buenisimo")

    def audio_play_game_over(self):
        self.audio_play("sound ventilagon/audio/es/perdiste")

    def audio_stop_song(self):
        self.serial_send("music off")

    def audio_begin(self):
        self.serial_send("sound ventilagon/audio/es/empeza")

    def audio_reset(self):
        self.serial_send("music off")

    def audio_stop_servo(self):
        self.serial_send("servo stop")

    # -- circular buffer / board (board.c) ---------------------------------------------
    def circularbuffer_reset(self):
        self.first_row = 0
        for n in range(NUM_ROWS):
            self.buffer[n] = 0

    def push_front(self, row):
        self.buffer[self.first_row] = row
        self.first_row = (self.first_row - 1 + NUM_ROWS) % NUM_ROWS

    def push_back(self, row):
        self.buffer[self.first_row] = row
        self.first_row = (self.first_row + 1) % NUM_ROWS

    def get_row(self, row_num):
        return self.buffer[(row_num + self.first_row) % NUM_ROWS]

    def board_reset(self):
        self.pattern_randomize()
        self.circularbuffer_reset()

    def board_fill_patterns(self):
        row_num = 20
        while row_num != NUM_ROWS:
            self.pattern_randomize()
            while not self.pattern_is_finished():
                self.push_back(self.pattern_next_row())
                row_num += 1
                if row_num == NUM_ROWS:
                    break

    def board_colision(self, pos, num_row):
        real_pos = (pos + self.nave_calibrate) & SUBDEGREES_MASK
        ship_column = (real_pos * NUM_COLUMNS) // SUBDEGREES
        row_ship = self.get_row(num_row)
        return bool(row_ship & (1 << ship_column))

    def board_step(self):
        self.push_back(self.pattern_next_row())
        if self.pattern_is_finished():
            self.pattern_randomize()

    def board_step_back(self):
        self.push_front(0)

    def board_win_step_back(self):
        self.push_front(self.pattern_next_row())
        if self.pattern_is_finished():
            self.pattern_randomize()

    # -- patterns (patterns.c) ---------------------------------------------------------
    def pattern_randomize(self):
        self.current_height = self.block_height = self.current_level["block_height"]
        self.row = 0
        self.transformation_base = (_rand(12) << 6)
        new_pattern = _rand(self.current_level["num_patterns"])
        self.rows = self.current_level["pool"][new_pattern]
        self.rows_len = len(self.rows)

    def pattern_transform(self, b):
        return _data.transformations[self.transformation_base + b]

    def pattern_next_row(self):
        ch = self.current_height
        self.current_height += 1
        if ch >= self.block_height:
            self.current_height = 0
            base = self.rows[self.row]
            self.row += 1
            self._value = self.pattern_transform(base)
        return self._value

    def pattern_is_finished(self):
        return (self.row >= self.rows_len) and (self.current_height >= self.block_height)

    # -- display sim (display.c) -------------------------------------------------------
    def display_reset(self):
        self.drift_pos = 0
        self.drift_speed = 0

    def display_calibrate(self, cal):
        self.calibrating = cal

    def display_ship_rows(self, current_pos):
        if self.calibrating:
            return 2 if self.board_colision(current_pos, ROW_SHIP) else 0
        d1 = abs(self.nave_pos - current_pos)
        d2 = abs(
            ((self.nave_pos + SUBDEGREES // 2) & SUBDEGREES_MASK)
            - ((current_pos + SUBDEGREES // 2) & SUBDEGREES_MASK)
        )
        hw = self.half_ship_width
        if d1 < hw or d2 < hw:
            return 2
        if d1 < (hw * 5) // 2 or d2 < (hw * 5) // 2:
            return 1
        return 0

    def display_adjust_drift(self):
        self._adjust_n = (self._adjust_n + 1) & 0x3FF
        if self._adjust_n == 0:
            self.drift_speed = self.current_level["drift"](self.drift_speed)

    def display_advance(self, now):
        """The non-rendering half of display_tick: advance drift and scroll the board.

        On hardware board_step fires when the spinning column index changes; here we
        consume all steps queued since the last tick, which scrolls the tunnel at the
        same one-row-per-step_delay rate.
        """
        if now > (self.last_drift + self.current_level["step_delay"] // 32):
            self.drift_pos = (self.drift_pos + self.drift_speed) & SUBDEGREES_MASK
            self.last_drift = now
        if self.queued_steps:
            for _ in range(self.queued_steps):
                self.board_step()
            self.queued_steps = 0

    # -- states ------------------------------------------------------------------------
    def _build_states(self):
        self.resetting_state = _State("RESETTING", self.resetting_setup, self.resetting_loop)
        self.play_state = _State("RUNNING GAME", self.play_setup, self.play_loop)
        self.gameover_state = _State("GAME OVER", self.gameover_setup, self.gameover_loop)
        self.win_state = _State("FOR THE WIN!", self.win_setup, self.win_loop)
        self.credits_state = _State("Rolling Credits", self.credits_setup, self.credits_loop)

    def change_state(self, new_state):
        self.current_state = new_state
        new_state.setup()

    # resetting (state_resetting.c)
    def resetting_setup(self):
        self.reset_last_step = self.now
        self.counter = 0
        self.audio_reset()
        self.serial_send("arduino reset")
        self.serial_send("arduino stop")
        self.is_idle = False

    def resetting_loop(self, now):
        reset_step_delay = (10 * 100 * 1000) // NUM_ROWS
        if (now - self.reset_last_step) > reset_step_delay:
            self.board_step_back()
            self.reset_last_step = now
            self.counter += 1
        if self.counter > NUM_ROWS:
            self.change_state(self.play_state)
            return
        self.display_advance(now)

    # play (state_play.c)
    def play_setup(self):
        self.current_level = self.levels[self.new_level]
        self.paused = False
        self.board_reset()
        self.audio_begin()
        self.display_reset()
        self.display_calibrate(False)
        self.audio_play(self.current_level["song"])
        self.serial_send("arduino start")
        self.section = 0
        self.section_init_time = self.now
        self.section_duration = SECTION_DURATIONS[0]
        self.queued_steps = 0

    def advance_section(self, now):
        self.section += 1
        self.section_init_time = now
        self.section_duration = SECTION_DURATIONS[self.section]
        self.audio_play(SECTION_SOUNDS[self.section])
        if self.section >= len(self.levels):
            self.audio_play_win()
            self.audio_stop_servo()
            self.change_state(self.credits_state)
            return
        self.current_level = self.levels[self.section]

    def check_section(self, now):
        if now - self.section_init_time > self.section_duration:
            self.advance_section(now)

    def play_loop(self, now):
        level = self.current_level
        if now > (self.last_move + level["step_delay"] // 32):
            if self.boton_cw != self.boton_ccw:
                if self.boton_cw:
                    new_pos = self.nave_pos + level["rotation_speed"]
                else:
                    new_pos = self.nave_pos - level["rotation_speed"]
                new_pos = (new_pos + SUBDEGREES) & SUBDEGREES_MASK
                if not self.board_colision(new_pos, ROW_SHIP):
                    self.nave_pos = new_pos
            self.last_move = now

        if now > (self.last_step + level["step_delay"]):
            if not self.board_colision(self.nave_pos, ROW_SHIP):
                if not self.paused:
                    self.queued_steps += 1
            else:
                self.multicolored = False  # ledbar_reset
                self.audio_play_crash()
                self.audio_stop_song()
                self.change_state(self.gameover_state)
                self.audio_play_game_over()
            self.last_step = now

        self.display_advance(now)
        self.display_adjust_drift()
        self.check_section(now)

    # game over (state_gameover.c)
    def gameover_setup(self):
        self.display_calibrate(True)
        self.serial_send("arduino attract")
        self.keys_pressed = self.boton_cw or self.boton_ccw
        self.is_idle = True

    def gameover_loop(self, now):
        if not self.boton_cw and not self.boton_ccw:
            self.keys_pressed = False
        if not self.keys_pressed:
            if self.boton_cw and self.boton_ccw:
                self.change_state(self.resetting_state)
                return
        self.display_advance(now)

    # win (state_win.c)
    def win_setup(self):
        self.display_calibrate(True)
        self.board_reset()
        self.multicolored = True  # ledbar_set_win_state
        self.win_started = self.now // 1000
        self.win_last_step = 0

    def win_loop(self, now):
        now_ms = now // 1000
        win_delay_1 = 45000 - 7000
        win_delay_2 = 45000
        if (now_ms - self.win_last_step) > 25:
            self.win_last_step = now_ms
            if (now_ms - self.win_started) > win_delay_1:
                self.board_step_back()
            else:
                self.board_win_step_back()
            self.display_adjust_drift()
        if (now_ms - self.win_started) > win_delay_2:
            self.change_state(self.gameover_state)
            return
        self.display_advance(now)

    # credits (state_win_credits.c) — text scroll is rendered in the render section
    def credits_setup(self):
        self.credits_started = self.now // 1000
        self.credits_reset(self.now)
        self.serial_send("arduino stop")

    def credits_reset(self, now):
        self.credits_step_delay = CREDITS_DURATION_MS * 1000 // (len(CREDITS_TEXT) * CHAR_WIDTH)
        self.step_position = 0
        self.creds_last_step = now

    def credits_loop(self, now):
        now_ms = now // 1000
        if (now_ms - self.credits_started) > CREDITS_DURATION_MS:
            self.change_state(self.win_state)
            return
        if (now - self.creds_last_step) > self.credits_step_delay:
            self.step_position += 1
            self.creds_last_step = now

    # -- lifecycle / pumping -----------------------------------------------------------
    def enter(self):
        # ventilagon_init + ventilagon_enter
        self.pattern_randomize()  # pattern_init
        self.board_reset()
        self.board_fill_patterns()
        self.new_level = 0
        self.multicolored = False  # ledbar_reset
        self._last_ticks = _now_us()
        self.change_state(self.resetting_state)

    def exit(self):
        self.serial_send("arduino stop")

    def received(self, buttons):
        self.boton_ccw = bool(buttons & JOY_LEFT)
        self.boton_cw = bool(buttons & JOY_RIGHT)
        if buttons >= BUTTON_A:
            self.boton_cw = self.boton_ccw = True

    def sending(self):
        if self._send_queue:
            return self._send_queue.pop(0)
        return None

    def advance_clock(self):
        t = _now_us()
        dt = _ticks_diff(t, self._last_ticks)
        if dt < 0:
            dt = 0
        self._last_ticks = t
        self.now += dt
        return self.now

    def tick(self):
        now = self.advance_clock()
        self.current_state.loop(now)


# credits text + font geometry (state_win_credits.c)
CHAR_WIDTH = 6
CREDITS_DURATION_MS = 19750
CREDITS_TEXT = (
    "                     SUPER VENTILAGON - Bits: alecu - Volts: Jorge - "
    "Waves: Cris - Voces: Nessita - (C) 2015 Club de Jaqueo                          "
)


# --- module-level singleton + public API ----------------------------------------------
_game = None


def _get():
    global _game
    if _game is None:
        _game = Game()
    return _game


def enter():
    global _game
    _game = Game()
    _game.enter()


def exit():
    _get().exit()


def received(buttons):
    _get().received(buttons)


def sending():
    return _get().sending()


def is_idle():
    return _get().is_idle


def tick():
    _get().tick()
