"""LED Usage: a diagnostic system app for measuring real current draw.

While active it disables the normal per-column POV render entirely (see
hardware/rotor/modules/povdisplay/led_usage.c, hooked at the top of
gpu.c's render()) and holds a static LED pattern controlled live from the
desktop emulator's companion panel (emulator/pyglet2x/pygletdraw.py) over
the "ledusage" console protocol (apps/micropython/ventilastation/led_usage.py).
"""

import vs2
from ventilastation.director import comms
from ventilastation.runtime import get_platform
from ventilastation import led_usage

DEFAULT_COUNT = 0
DEFAULT_RGB = (0, 0, 0)
DEFAULT_GLOBAL = 16


class LedUsage(vs2.Scene):
    # No layers/sprites of our own -- the real "render" is bypassed at the
    # native layer regardless of scene content (see led_usage.c). Reuses the
    # shared "other" asset pack purely because on_enter() always loads one
    # (falling back to this scene's `system.led_usage` API slug otherwise,
    # which has no matching ROM) -- same reasoning as system/vs2_hardware.
    asset_pack = "other"
    # A power-draw measurement is typically taken with a multimeter and no
    # hands anywhere near a joystick for as long as it takes to get a
    # steady reading -- the base Scene's default 30s idle timeout would
    # auto-pop (on_idle()) mid-measurement otherwise. Same reasoning as
    # system/vs2_hardware disabling it for its own long unattended runs.
    idle_timeout = None

    def build(self):
        r, g, b = DEFAULT_RGB
        led_usage.activate(get_platform().display, comms.send,
                            count=DEFAULT_COUNT, r=r, g=g, b=b,
                            global_brightness=DEFAULT_GLOBAL)

    def update(self):
        pass

    def teardown(self):
        led_usage.deactivate(get_platform().display, comms.send)


def main():
    return LedUsage()
