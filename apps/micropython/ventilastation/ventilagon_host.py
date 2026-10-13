"""Scene API for the C game in the desktop host or browser worker.

Frames never pass through the MicroPython heap. The host owns simulation,
rendering, audio/control output and the raw-frame presentation for this scene.
The rotor continues importing its built-in ventilagon module.
"""
from ventilastation.compat import ticks_us, ticks_diff_us
from ventilastation.runtime import get_platform

_buttons = 0
_last_tick = 0


def _host_call(name, *args):
    platform = get_platform()
    if platform.name == "browser":
        # Primitive arguments only. The worker's C memory owns the frame.
        getattr(platform.comms.worker_host, "ventilagon_" + name)(*args)
    else:
        line = b"ventilagon " + name.encode()
        for value in args:
            line += b" %d" % value
        platform.comms.send(line)


def enter():
    global _buttons, _last_tick
    _buttons = 0
    _last_tick = ticks_us()
    _host_call("enter", _last_tick & 0xFFFFFFFF)


def exit():
    _host_call("exit")


def received(buttons):
    global _buttons
    _buttons = buttons & 0xFF


def sending():
    # The host routes C's outbound lines directly through its normal dispatcher.
    return None


def is_idle():
    idle = getattr(get_platform().comms, "ventilagon_is_idle", None)
    return bool(idle()) if idle else False


def tick():
    global _last_tick
    error_status = getattr(get_platform().comms, "ventilagon_error", None)
    error = error_status() if error_status else None
    if error:
        raise RuntimeError("Native Ventilagon: " + error)
    now = ticks_us()
    elapsed = max(0, min(250000, ticks_diff_us(now, _last_tick)))
    _last_tick = now
    _host_call("tick", elapsed, _buttons)
