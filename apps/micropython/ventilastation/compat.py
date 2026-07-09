"""Shims over the differences between MicroPython builds (ESP32, unix, WASM).

Every runtime this package targets is MicroPython, but the WASM build lacks
some of the `utime` niceties, and the unix build exposes them under `time`.
Import time helpers from here instead of repeating the fallback dance.
"""

try:
    import utime as time
except ImportError:
    import time


def ticks_us():
    ticks = getattr(time, "ticks_us", None)
    if ticks is not None:
        return ticks()
    perf_counter = getattr(time, "perf_counter", None)
    if perf_counter is not None:
        return int(perf_counter() * 1000000)
    return 0


def ticks_diff_us(end, start):
    ticks_diff = getattr(time, "ticks_diff", None)
    if ticks_diff is not None:
        return ticks_diff(end, start)
    return end - start
