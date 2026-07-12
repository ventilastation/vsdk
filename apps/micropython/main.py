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

# Confirm this OTA image is healthy. Must happen at boot before any crash risk.
try:
    import esp32
    esp32.Partition.mark_app_valid_cancel_rollback()
except Exception:
    pass

# If running from factory (first boot after flash_vsdk_image, or after a
# native app set factory as the boot partition), migrate to the updatable
# micropython (ota_2) slot so OTA updates never touch factory.
try:
    import esp32
    if esp32.Partition(esp32.Partition.RUNNING).info()[4] == "factory":
        _mp = esp32.Partition.find(esp32.Partition.TYPE_APP, label="micropython")
        if _mp:
            print("main: running on factory — switching to micropython slot")
            _mp[0].set_boot()
            import machine
            machine.reset()
except Exception as _me:
    print("main: ota migration check failed:", _me)

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

from ventilastation.app_loader import ensure_project_root_on_path
from ventilastation.director import director, ensure_runtime

ensure_runtime()
ensure_project_root_on_path()

from system.launcher.code import setup as setup_launcher

def setup():
    setup_launcher()

def main():
    setup()
    director.run()

if __name__ == '__main__':
    import machine
    try:
        director.sound_play(b"alecu.vyruss/shoot3")
        main()
    except Exception as e:
        # raise
        buf = io.StringIO()
        sys.print_exception(e, buf)
        director.report_traceback(buf.getvalue().encode("utf-8"))
        print(buf.getvalue())
        # machine.reset()
