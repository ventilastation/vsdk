"""Hardware platform: the ESP32-S3 rotor board.

Display and sprites are the vshw_* native C modules linked into the
firmware (hardware/rotor/modules); comms is the UART link to the base.
"""

from ventilastation import board_config
from ventilastation.platforms.base import LazyModule, Platform, optional_attr
from ventilastation.runtime import FileStorage


def create_hardware_platform():
    board_config.load()
    display = LazyModule("vshw_povdisplay")
    display.update = lambda: None  # GPU renders autonomously via hall sensor interrupt
    return Platform(
        name="hardware",
        comms=LazyModule("ventilastation.serialcomms"),
        display=display,
        sprites_backend=LazyModule("vshw_sprites"),
        storage=FileStorage(),
        hw_config=board_config.display_args(),
        disable_gc=True,
        vs2_backend=LazyModule("vshw_vs2"),
        native_launcher=optional_attr("vshw_native_apps", "launch"),
        native_available=optional_attr("vshw_native_apps", "available"),
        native_last_exit_reason=optional_attr("vshw_native_apps", "last_exit_reason"),
    )
