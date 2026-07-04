import io
import sys

# Confirm this OTA image is healthy. Must happen at boot before any crash risk.
try:
    import esp32
    esp32.Partition.mark_app_valid_cancel_rollback()
except Exception:
    pass

# OTA boot mode: if /ota_request exists, run OTA before the GPU task starts.
# The GPU task and WiFi both use the SPI bus (PSRAM); running them concurrently
# causes a core crash. OTA runs here, in isolation, before ensure_runtime().
# To trigger: write "http://HOST:8000" to /ota_request and reset the board.
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
    from ventilastation import updater
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
