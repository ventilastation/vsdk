"""Frozen boot script: guarantees `main.py` exists on vfs, nothing else.

Picked up automatically by the vendored (unmodified) MicroPython main.c's
own `pyexec_file_if_exists("boot.py")` call, which checks for a frozen
module of this exact name before ever touching the filesystem -- no local
patch to the MicroPython source tree needed. Freezing "boot.py" claims that
name permanently: nothing in this project puts a real boot.py on vfs, so
that's safe, but a frozen module here always wins over any filesystem one.

Deliberately does NOT run recovery directly, even though a fresh board (no
vfs content at all) needs it: this runs *before* main.c's own mp_usbd_init()
call, which is what actually activates the USB CDC device MicroPython's own
REPL/stdout runs over ("called on any soft reset after boot.py runs" -- see
shared/tinyusb/mp_usbd_runtime.c). A long-running blocking call here (like
vsdk_recovery.run()'s retry loop) would starve mp_usbd_init() of ever
running at all, and confirmed on hardware: Ctrl-C-based interruption (which
flash_recovery_image.py and a human at the REPL both depend on) then simply
doesn't work, not even during the loop's otherwise-safe idle backoff sleep.

So all this does is make sure *some* main.py exists -- writing a minimal
bootstrap stub if vfs has none at all (safe: nothing exists yet to
overwrite) -- and returns immediately. Stock main.c then runs mp_usbd_init()
and, after that, main.py normally, exactly as it always has: main.py itself
(not boot.py) is what actually checks whether to run recovery (see its own
top-of-file check), for both this stub and a real, already-installed one
that's merely running from `factory` (bootloader rollback, or a deliberate
hand-off -- see updater._update_partitions()).

Once recovery succeeds, tier-1 OTA file sync (see updater.py) overwrites
this stub with the real, field-updatable main.py -- no separate cleanup
needed here.
"""

try:
    import uos
    uos.stat("main.py")
except OSError:
    with open("main.py", "w") as _f:
        _f.write("import vsdk_recovery\nvsdk_recovery.run()\n")
