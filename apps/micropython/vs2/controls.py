"""The two controllers and their buttons.

Designed for a star import, which is why ``__all__`` is exactly the two
controller views and the ten button constants::

    import vs2
    from vs2.controls import *

    if joy1.held(LEFT):
        ...

Qualified access works too, and is how you reach ``idle_ms``, which the
star import deliberately leaves out.

This is a real module rather than a synthetic object so MicroPython's
``IMPORT_STAR`` can safely implement the documented ``from vs2.controls
import *`` form.
"""

import utime

from ventilastation.director import director


#: Joystick left.
LEFT = 0x01
#: Joystick right.
RIGHT = 0x02
#: Joystick up.
UP = 0x04
#: Joystick down.
DOWN = 0x08
#: Face button A.
A = 0x10
#: Face button B.
B = 0x20
#: Face button X.
X = 0x40
# The high bit also mirrors Y for V1 compatibility.  The extra bit keeps the
# semantic V2 value correct for the two independent controllers.
#: Face button Y. Also pops the scene unless ``Scene.back_button`` is false.
Y = (0x80, 0x01, 0x02)
#: Start button.
START = (0, 0x04, 0x10)
#: Back button. Also pops the scene unless ``Scene.back_button`` is false.
BACK = (0, 0x08, 0x20)


class _Controller:
    """One controller's current state, as ``joy1`` or ``joy2``.

    Three methods cover every read, in the Godot idiom: ``held`` is a level
    — the button is down right now — while ``just_pressed`` and
    ``just_released`` are edges that are true for the single tick the
    transition happened on.

    In practice movement reads levels and fire, confirm and menu-stepping read
    edges, but any button works with any of the three. All of them are plain
    bitfield tests: they allocate nothing and are free to call several times per
    tick.
    """

    def __init__(self, player):
        self.player = player

    def _mask(self, button):
        return button[0] if isinstance(button, tuple) else button

    def _extra(self, button):
        if not isinstance(button, tuple):
            return 0
        return button[self.player]

    def held(self, button):
        """Whether ``button`` is down right now.

        Args:
            button: A constant from this module, e.g. ``LEFT``.

        Returns:
            bool: True while the button is held.
        """
        mask = self._mask(button)
        extra = self._extra(button)
        if self.player == 1:
            return bool((director.buttons & mask) or (director.extra_buttons & extra))
        return bool((director.buttons2 & mask) or (director.extra_buttons & extra))

    def just_pressed(self, button):
        """Whether ``button`` went down on this tick.

        True for exactly one tick per press, which is what fire, confirm and
        menu-stepping want.

        Args:
            button: A constant from this module, e.g. ``A``.

        Returns:
            bool: True on the tick the button was pressed.
        """
        mask = self._mask(button)
        extra = self._extra(button)
        if self.player == 1:
            return bool(((director.buttons & mask) and not (director.last_buttons & mask))
                        or ((director.extra_buttons & extra) and not (director.last_extra_buttons & extra)))
        return bool(((director.buttons2 & mask) and not (director.last_buttons2 & mask))
                    or ((director.extra_buttons & extra) and not (director.last_extra_buttons & extra)))

    def just_released(self, button):
        """Whether ``button`` came up on this tick.

        True for exactly one tick per release. Useful for charge-and-release
        mechanics.

        Args:
            button: A constant from this module.

        Returns:
            bool: True on the tick the button was released.
        """
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
    """Integer-like idle duration, evaluated afresh for each operation."""

    def __int__(self):
        return _idle_ms()

    def __index__(self):
        return _idle_ms()

    def __repr__(self):
        return str(_idle_ms())

    def __str__(self):
        return str(_idle_ms())

    def __bool__(self):
        return bool(_idle_ms())

    def __float__(self):
        return float(_idle_ms())

    def __hash__(self):
        return hash(_idle_ms())

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

    def __ne__(self, value):
        return _idle_ms() != value

    def __add__(self, value):
        return _idle_ms() + value

    def __radd__(self, value):
        return value + _idle_ms()

    def __sub__(self, value):
        return _idle_ms() - value

    def __rsub__(self, value):
        return value - _idle_ms()

    def __mul__(self, value):
        return _idle_ms() * value

    def __rmul__(self, value):
        return value * _idle_ms()

    def __floordiv__(self, value):
        return _idle_ms() // value

    def __rfloordiv__(self, value):
        return value // _idle_ms()

    def __mod__(self, value):
        return _idle_ms() % value

    def __rmod__(self, value):
        return value % _idle_ms()

    def __truediv__(self, value):
        return _idle_ms() / value

    def __rtruediv__(self, value):
        return value / _idle_ms()

    def __neg__(self):
        return -_idle_ms()

    def __pos__(self):
        return _idle_ms()


idle_ms = _IdleMs()

__all__ = ("joy1", "joy2", "LEFT", "RIGHT", "UP", "DOWN", "A", "B",
           "X", "Y", "START", "BACK")
