import io
import sys

# The rotor's USB REPL is separate from its base-station UART.  Mirror Python
# stdout to the host protocol as early as possible so startup diagnostics show
# in the desktop emulator when it is connected to the real board.
if sys.platform == "esp32":
    try:
        from ventilastation.serialcomms import install_stdout
        install_stdout()
    except Exception:
        # If the board UART cannot be configured yet, retain MicroPython's
        # normal console rather than preventing boot.
        pass


def _running_partition_label():
    try:
        import esp32
        return esp32.Partition(esp32.Partition.RUNNING).info()[4]
    except Exception:
        return None


if _running_partition_label() == "factory":
    # factory is the permanent recovery environment, not a write-once image
    # that migrates to ota_2 on first boot and is never touched again.
    # Reached here for any of: a fresh board that boot.py just bootstrapped
    # a stub main.py for (see boot.py's docstring -- that stub also hits
    # this same branch, since a fresh board's RUNNING partition is
    # "factory"), a bootloader rollback after a bad ota_2 update that never
    # confirmed itself (see the mark_app_valid_cancel_rollback() call
    # below), or a deliberate hand-off from a running ota_2 image that
    # needs to update its own partition (updater.py can never overwrite the
    # partition it's currently executing from -- see
    # updater._update_partitions()).
    # vsdk_recovery is frozen at the top level so this works even with vfs
    # completely empty; see vsdk_recovery.py's docstring for why it and
    # everything it needs avoid the ventilastation package and vs2.
    import vsdk_recovery
    vsdk_recovery.run()
    # run() only returns if it hit an error it couldn't recover from by
    # resetting (shouldn't happen on hardware); nothing below this point
    # would be reachable on a real board in that case either way.

# --- Normal boot: running from micropython (ota_2), or the running
# partition couldn't be determined (e.g. a non-ESP32 test/dev platform). ---

# OTA boot mode: if /ota_request exists, run OTA before the GPU task starts.
# The GPU task and WiFi both use the SPI bus (PSRAM); running them concurrently
# causes a core crash. OTA runs here, in isolation, before ensure_runtime().
# To trigger: write "http://HOST:5653" to /ota_request and reset the board.
# director.py does this automatically when it receives an ota_start command.
def _check_ota_boot():
    try:
        with open("/ota_request") as _f:
            _url = _f.read().strip()
    except OSError:
        return
    if not _url:
        return
    import os
    try:
        os.remove("/ota_request")
    except OSError:
        pass
    print("main: OTA boot mode — url:", _url)
    # updater.py is frozen at the top level (not under ventilastation/):
    # recovery needs it too, and it must work even when vfs has no
    # ventilastation package at all. See vsdk_recovery.py.
    import updater
    updater.run(_url, lambda msg: None)
    print("main: OTA done, rebooting")
    import machine
    machine.reset()

_check_ota_boot()

# A freshly OTA'd ota_2 image boots in the bootloader's "pending verify"
# rollback state (CONFIG_BOOTLOADER_APP_ROLLBACK_ENABLE=y). Only confirm it
# once the main loop has genuinely run for a few seconds -- gated on real
# Director.step_once() ticks below, not a bare wall-clock sleep, so a hang
# counts the same as a crash. If it never confirms, the bootloader reverts
# to factory (recovery) on a later boot and recovery retries. A watchdog
# covers the case where the loop hangs outright rather than raising: fed
# once per tick, armed here (before ensure_runtime()) so a hang inside that
# call is caught too.
_CONFIRM_AFTER_MS = 10000
_wdt = None
try:
    import machine
    _wdt = machine.WDT(timeout_ms=15000)
except Exception:
    pass  # desktop/headless platforms have no machine.WDT

def _feed_wdt():
    if _wdt is not None:
        try:
            _wdt.feed()
        except Exception:
            pass

_feed_wdt()

from ventilastation.app_loader import ensure_project_root_on_path
from ventilastation.director import director, ensure_runtime

try:
    ensure_runtime()
    ensure_project_root_on_path()
except RuntimeError as _re:
    # Most commonly: NVS "vs_board" is missing/incomplete (a board flashed
    # without the provisioning step). Recovery can still attempt WiFi/OTA --
    # it reads NVS directly, independent of ensure_runtime() -- even though
    # the display can't be initialized.
    print("main: ensure_runtime failed, falling back to recovery:", _re)
    import vsdk_recovery
    vsdk_recovery.run()

from system.launcher.code import setup as setup_launcher

def setup():
    setup_launcher()

_confirmed = False
_boot_ticks_start = None

def _on_tick():
    global _confirmed
    _feed_wdt()
    if not _confirmed:
        import utime
        if utime.ticks_diff(utime.ticks_ms(), _boot_ticks_start) >= _CONFIRM_AFTER_MS:
            _confirmed = True
            try:
                import esp32
                esp32.Partition.mark_app_valid_cancel_rollback()
            except Exception:
                pass

def main():
    global _boot_ticks_start
    import utime
    _boot_ticks_start = utime.ticks_ms()
    setup()
    director.run(feed_wdt=_on_tick)

if __name__ == '__main__':
    try:
        director.sound_play(b"alecu.vyruss/shoot3")
        main()
    except Exception as e:
        buf = io.StringIO()
        sys.print_exception(e, buf)
        director.report_traceback(buf.getvalue().encode("utf-8"))
        print(buf.getvalue())
        # Reset unconditionally: if this image already confirmed itself
        # (10s of ticks passed), this is just a clean restart into the same
        # still-valid ota_2 image. If it crashed before confirming, it
        # stays unconfirmed and the bootloader's own rollback state decides
        # what the next boot does -- main.py doesn't need to know which
        # case this is.
        import machine
        machine.reset()
