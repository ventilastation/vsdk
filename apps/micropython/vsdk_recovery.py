"""Recovery: the permanent fallback environment running from `factory`.

Called from `main.py`'s own top-of-file check, whenever the board is
running from the `factory` partition -- a fresh board (where `boot.py`,
frozen and picked up automatically by the vendored, unmodified MicroPython
`main.c`, bootstrapped a minimal stub `main.py` since vfs had none at all --
see boot.py's own docstring for why that hand-off happens through a real
main.py rather than boot.py calling this directly), a bootloader rollback
after a bad `micropython`/ota_2 update that never confirmed itself, or a
deliberate hand-off (see `updater._update_partitions()`).

Recovery's job: show that the board is alive, reconnect to WiFi, and keep
retrying the normal three-tier OTA update (`updater.py`) until it succeeds --
this is what brings a fresh factory-only board up to a full working system,
and what repairs one that fell back here after a bad update.

This module -- and everything it imports -- must work with vfs completely
empty (no `ventilastation` package on disk at all), so it is frozen at the
top level and deliberately has NO dependency on the `ventilastation` package
or `vs2`: those live only on vfs and are meant to stay OTA-updatable there.
(A frozen submodule nested inside an also-vfs-resident package is NOT
reliably reachable -- MicroPython resolves `pkg.sub` relative to wherever
`pkg` itself was found, filesystem or frozen, not by re-checking both for
every submodule. Confirmed on hardware: nesting recovery under
`ventilastation/` raised `ImportError: no module named 'ventilastation.recovery'`
as soon as vfs had its own `ventilastation/__init__.py`, which is the normal
case outside a pristine first boot.) `updater.py` is frozen at the top level
for the same reason -- it already had no `ventilastation.*` dependencies of
its own, so moving it out costs nothing and it's genuinely bootstrap-critical
infrastructure, not something that needs to self-update via its own OTA.

Display setup uses the native `vshw_povdisplay`/`vshw_sprites` modules
directly (always present, compiled into firmware) rather than going through
`ventilastation.platforms`/`Director`/`vs2`, which are vfs-only.
"""

import utime

import updater
import vsdk_logo_strip
import vsdk_uart_log

_OTA_URL = "http://ventilastation-base.local:5653"
_WDT_TIMEOUT_MS = 30000
_BACKOFF_SCHEDULE_MS = (5000, 10000, 20000, 30000)
_PIXELS = 54
_PERSPECTIVE_HUD = 2

# Keys read from NVS namespace "vs_board" -- the same namespace and key
# names as ventilastation/board_config.py, kept in sync by hand rather than
# imported (board_config.py lives on vfs; see the module docstring). Only
# the display-wiring keys here; the serial_* keys for the UART status link
# are read separately by vsdk_uart_log.py.
_DISPLAY_NVS_KEYS = (
    "hall_gpio", "irdiode_gpio", "led_spi_host",
    "led_clk", "led_mosi", "led_cs", "led_freq",
)


def _read_display_args():
    import esp32
    nvs = esp32.NVS("vs_board")
    return tuple(nvs.get_i32(key) for key in _DISPLAY_NVS_KEYS)


def _make_sprite():
    """Best-effort: initialize the display and show the boot frame. Returns
    None (not an exception) if board wiring isn't provisioned -- a missing
    display must not prevent the WiFi/OTA attempts below.
    """
    try:
        import vshw_povdisplay
        import vshw_sprites

        display_args = _read_display_args()
        vshw_povdisplay.init(_PIXELS, *display_args)
        vshw_povdisplay.set_gamma_mode(1)

        strip_number = vsdk_logo_strip.install(vshw_povdisplay, vshw_sprites)
        sprite = vshw_sprites.Sprite()
        sprite.set_strip(strip_number)
        sprite.set_perspective(_PERSPECTIVE_HUD)
        sprite.set_x(0)
        sprite.set_y((_PIXELS - vsdk_logo_strip.HEIGHT) // 2)
        sprite.set_frame(vsdk_logo_strip.FRAME_BOOT)
        return sprite
    except Exception as error:
        print("recovery: display unavailable, continuing without it:", error)
        return None


def _arm_wdt():
    try:
        import machine
    except ImportError:
        return None  # desktop/headless platforms have no machine module at all
    try:
        # machine.WDT's keyword is "timeout" (see extmod/machine_wdt.c), not
        # "timeout_ms" -- this silently never armed on real hardware before
        # (caught below and treated the same as "no WDT support"), which is
        # exactly the failure mode this watchdog exists to catch. Any other
        # construction failure is logged rather than swallowed, so a repeat
        # doesn't go unnoticed again.
        return machine.WDT(timeout=_WDT_TIMEOUT_MS)
    except AttributeError:
        return None  # this machine module has no WDT at all
    except Exception as error:
        vsdk_uart_log.info("recovery: WDT arm failed, continuing without it: %s" % error)
        return None


def _feed(wdt):
    if wdt is not None:
        try:
            wdt.feed()
        except Exception:
            pass


def _set_frame(sprite, frame):
    if sprite is not None:
        try:
            sprite.set_frame(frame)
        except Exception:
            pass


def _make_progress_handler(sprite, wdt):
    outcome = {"ok": None}

    def handle(line):
        _feed(wdt)
        raw = line if isinstance(line, (bytes, bytearray)) else line.encode()
        vsdk_uart_log.send(raw.rstrip(b"\n"))
        try:
            text = (line.decode() if isinstance(line, bytes) else line).strip()
        except Exception:
            return
        if text.startswith("ota_progress start"):
            _set_frame(sprite, vsdk_logo_strip.FRAME_WIFI)
        elif text.startswith("ota_progress downloading") or text.startswith("ota_progress file"):
            _set_frame(sprite, vsdk_logo_strip.FRAME_DOWNLOADING)
        elif text.startswith("ota_progress checking") or text.startswith("ota_progress scan"):
            _set_frame(sprite, vsdk_logo_strip.FRAME_CHECKING)
        elif text.startswith("ota_progress writing") or text.startswith("ota_progress partition"):
            _set_frame(sprite, vsdk_logo_strip.FRAME_WRITING)
        elif text.startswith("ota_error"):
            outcome["ok"] = False
            _set_frame(sprite, vsdk_logo_strip.FRAME_ERROR)
            print("recovery:", text)
        elif text.startswith("ota_done"):
            outcome["ok"] = True
            _set_frame(sprite, vsdk_logo_strip.FRAME_SUCCESS)

    return handle, outcome


def _boot_into_micropython_if_ready():
    """Nothing needed updating this round -- if a real micropython image is
    already installed, hand off to it instead of sitting in recovery forever.
    """
    import esp32
    parts = esp32.Partition.find(esp32.Partition.TYPE_APP, label="micropython")
    if not parts:
        vsdk_uart_log.info("recovery: update complete, but no micropython partition yet; holding in recovery")
        return False
    vsdk_uart_log.info("recovery: update complete, handing off to micropython")
    parts[0].set_boot()
    import machine
    machine.reset()


def _attempt(sprite, wdt):
    handle, outcome = _make_progress_handler(sprite, wdt)
    updater.run(_OTA_URL, handle)
    # updater.run() calls machine.reset() itself on a successful micropython
    # write; reaching here means either nothing needed a firmware write, or
    # something failed before that point.
    return outcome["ok"]


_BOOT_GRACE_MS = 8000


def _boot_grace_period(wdt):
    """Guaranteed-idle window before the first network attempt.

    Once the retry loop below is under way, WiFi connect / mDNS resolution
    are blocking calls that don't yield to a Ctrl-C interrupt (confirmed on
    hardware: a raw Ctrl-C sent mid-attempt can go unanswered for well over
    a minute, spanning several full backoff cycles), so external tools
    (bench flashing scripts, a human dropping to the REPL) need a window
    whose timing is predictable from the outside, not buried somewhere
    inside an ongoing retry cycle. This is that window: pure sleep, no
    network calls, right after boot -- the interrupt-during-idle-sleep path
    is confirmed reliable, it's just a question of knowing when to expect it.
    """
    waited = 0
    while waited < _BOOT_GRACE_MS:
        _feed(wdt)
        utime.sleep_ms(min(500, _BOOT_GRACE_MS - waited))
        waited += 500


def run():
    try:
        sprite = _make_sprite()
        wdt = _arm_wdt()
        vsdk_uart_log.info("recovery: booted from factory, target %s" % _OTA_URL)
        _boot_grace_period(wdt)

        attempt = 0
        while True:
            _feed(wdt)
            vsdk_uart_log.info("recovery: OTA attempt %d" % (attempt + 1))
            ok = _attempt(sprite, wdt)
            if ok:
                vsdk_uart_log.info("recovery: OTA attempt %d succeeded" % (attempt + 1))
                _boot_into_micropython_if_ready()
                # No micropython partition to hand off to (e.g. a bench board
                # mid-bring-up): hold here, fully updated, and keep retrying
                # in case a firmware update lands later. Reset the backoff
                # since this attempt succeeded.
                attempt = 0
            delay = _BACKOFF_SCHEDULE_MS[min(attempt, len(_BACKOFF_SCHEDULE_MS) - 1)]
            attempt += 1
            if not ok:
                vsdk_uart_log.info("recovery: OTA attempt failed, retrying in %dms" % delay)
            waited = 0
            while waited < delay:
                _feed(wdt)
                utime.sleep_ms(min(1000, delay - waited))
                waited += 1000
    except Exception as error:
        vsdk_uart_log.info("recovery: fatal error, resetting: %s" % error)
        print("recovery: fatal error, resetting:", error)
        import machine
        machine.reset()
