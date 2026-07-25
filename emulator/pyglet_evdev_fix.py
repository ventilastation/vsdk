"""Workaround for a pyglet bug: wrong struct input_event size on 32-bit Linux.

pyglet.input.linux.evdev.Timeval hardcodes tv_sec/tv_usec as ctypes.c_int64
(8 bytes each), making its InputEvent ctypes struct 24 bytes on every
platform. The kernel's actual struct input_event embeds a plain C `long`
for each timeval field, which is 4 bytes on a 32-bit userspace (as run on
this project's Base, a Raspberry Pi) -- 16 bytes total there, not 24.

EvdevDevice.select() computes n_events = bytes_read // self._event_size;
with the wrong (24-byte) size on a 32-bit system that's 16 // 24 == 0 on
every single-event read. It silently decides every read holds zero
complete events and never parses any of them, forever, while the
underlying readv() call itself keeps succeeding -- so a gamepad shows up
as connected and opens without error, but no button/stick state ever
changes. Diagnosed on real hardware (Logitech F310 on the Base); a
verified-with-evtest raw event stream was flowing the whole time.

Reported upstream: https://github.com/pyglet/pyglet/issues/<fill in after filing>

Call apply() once, before anything constructs a pyglet ControllerManager or
opens a pyglet.input Controller/Joystick on Linux -- it replaces the two
ctypes.Structure classes EvdevDevice reads InputEvent through by name at
each device's construction time, so timing only needs to be "before that
construction", not "before import".
"""

import ctypes


def apply():
    import pyglet.input.linux.evdev as evdev_backend

    class Timeval(ctypes.Structure):
        _fields_ = (
            ('tv_sec', ctypes.c_long),
            ('tv_usec', ctypes.c_long),
        )

    class InputEvent(ctypes.Structure):
        _fields_ = (
            ('time', Timeval),
            ('type', ctypes.c_uint16),
            ('code', ctypes.c_uint16),
            ('value', ctypes.c_int32),
        )

    evdev_backend.Timeval = Timeval
    evdev_backend.InputEvent = InputEvent
