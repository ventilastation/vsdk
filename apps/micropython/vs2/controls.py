"""Controller views for the sealed VS2 API.

This is a real module rather than a synthetic object so MicroPython's
``IMPORT_STAR`` can safely implement the documented ``from vs2.controls
import *`` form.
"""

import utime

from ventilastation.director import director


LEFT = 0x01
RIGHT = 0x02
UP = 0x04
DOWN = 0x08
A = 0x10
B = 0x20
X = 0x40
# The high bit also mirrors Y for V1 compatibility.  The extra bit keeps the
# semantic V2 value correct for the two independent controllers.
Y = (0x80, 0x01, 0x02)
START = (0, 0x04, 0x10)
BACK = (0, 0x08, 0x20)


class _Controller:
    def __init__(self, player):
        self.player = player

    def _mask(self, button):
        return button[0] if isinstance(button, tuple) else button

    def _extra(self, button):
        if not isinstance(button, tuple):
            return 0
        return button[self.player]

    def held(self, button):
        mask = self._mask(button)
        extra = self._extra(button)
        if self.player == 1:
            return bool((director.buttons & mask) or (director.extra_buttons & extra))
        return bool((director.buttons2 & mask) or (director.extra_buttons & extra))

    def just_pressed(self, button):
        mask = self._mask(button)
        extra = self._extra(button)
        if self.player == 1:
            return bool(((director.buttons & mask) and not (director.last_buttons & mask))
                        or ((director.extra_buttons & extra) and not (director.last_extra_buttons & extra)))
        return bool(((director.buttons2 & mask) and not (director.last_buttons2 & mask))
                    or ((director.extra_buttons & extra) and not (director.last_extra_buttons & extra)))

    def just_released(self, button):
        mask = self._mask(button)
        extra = self._extra(button)
        if self.player == 1:
            return bool((not (director.buttons & mask) and (director.last_buttons & mask))
                        or (not (director.extra_buttons & extra) and (director.last_extra_buttons & extra)))
        return bool((not (director.buttons2 & mask) and (director.last_buttons2 & mask))
                    or (not (director.extra_buttons & extra) and (director.last_extra_buttons & extra)))


joy1 = _Controller(1)
joy2 = _Controller(2)


def _idle_ms():
    return max(0, utime.ticks_diff(utime.ticks_ms(), director.last_player_action))


class _IdleMs:
    """Readable integer-like idle duration, evaluated when it is compared."""

    def __int__(self):
        return _idle_ms()

    def __index__(self):
        return _idle_ms()

    def __repr__(self):
        return str(_idle_ms())

    def __lt__(self, value):
        return _idle_ms() < value

    def __le__(self, value):
        return _idle_ms() <= value

    def __gt__(self, value):
        return _idle_ms() > value

    def __ge__(self, value):
        return _idle_ms() >= value

    def __eq__(self, value):
        return _idle_ms() == value


idle_ms = _IdleMs()

__all__ = ("joy1", "joy2", "LEFT", "RIGHT", "UP", "DOWN", "A", "B",
           "X", "Y", "START", "BACK")
