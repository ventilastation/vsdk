"""Desktop platform: the local MicroPython process spawned by emulator/emu.py.

Comms/display talk TCP (or a named pipe on Windows) to the pyglet host,
which renders the polar frame and plays audio.
"""

import sys

from ventilastation.platforms.base import LazyModule, Platform, optional_attr
from ventilastation.runtime import FileStorage


def _detect_desktop_comms_module():
    if sys.platform == "win32":
        return LazyModule("ventilastation.wincomms")
    return LazyModule("ventilastation.comms")


def create_desktop_platform():
    return Platform(
        name="desktop",
        comms=_detect_desktop_comms_module(),
        display=LazyModule("ventilastation.remotepov"),
        sprites_backend=LazyModule("ventilastation.emu_sprites"),
        storage=FileStorage(),
        native_launcher=optional_attr("vshw_native_apps", "launch"),
        native_available=optional_attr("vshw_native_apps", "available"),
        native_last_exit_reason=optional_attr("vshw_native_apps", "last_exit_reason"),
    )
