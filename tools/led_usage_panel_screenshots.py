#!/usr/bin/env python3
"""Render the desktop emulator's toolbar overlays (help, settings, LED
usage) to PNGs, for eyeballing/tuning their pyglet layout without clicking
through the app by hand.

Usage:
    python3 tools/led_usage_panel_screenshots.py [output_dir]

Needs a real display connection (not just pyglet's 1x1 shadow window) --
on a Mac whose screen has gone to sleep, wake it first (e.g. `caffeinate
-u -t 5`) or the window will fail to open.
"""
import os
import pathlib
import sys

REPO_ROOT = pathlib.Path(__file__).resolve().parent.parent
EMULATOR_DIR = REPO_ROOT / "emulator"


def main():
    out_dir = pathlib.Path(sys.argv[1]).resolve() if len(sys.argv) > 1 else pathlib.Path.cwd()
    out_dir.mkdir(parents=True, exist_ok=True)

    # pygletdraw.py loads its assets (logo.png, ...) by a path relative to
    # emulator/, same as running `emu.py` normally would.
    os.chdir(EMULATOR_DIR)
    sys.path.insert(0, str(EMULATOR_DIR))
    sys.path.insert(0, str(EMULATOR_DIR / "pyglet2x"))

    import config  # noqa: E402  local-sim defaults: DISPLAY_ENABLED=True
    import comms  # noqa: E402

    comms.start()

    import pyglet  # noqa: E402
    from pyglet2x import pygletdraw as pd  # noqa: E402

    pd.display_init(54)
    pd.window.set_size(1000, 650)

    def snap(name, overlay):
        pd.active_overlay = overlay
        pd.window.switch_to()
        pd.window.dispatch_events()
        pd.display_draw()
        pyglet.image.get_buffer_manager().get_color_buffer().save(str(out_dir / name))
        pd.window.flip()
        print("saved", out_dir / name)

    snap("panel_base.png", None)
    snap("panel_help.png", pd.OVERLAY_HELP)
    snap("panel_settings.png", pd.OVERLAY_SETTINGS)
    snap("panel_led_usage.png", pd.OVERLAY_LED_USAGE)

    comms.shutdown()
    print("done")


if __name__ == "__main__":
    main()
