freeze("$(PORT_DIR)/modules")
module("vsdk_board.py")

# Recovery must work with no vfs content at all (a fresh board only has
# factory + NVS), so it and everything it needs are frozen into the
# firmware rather than living on the LittleFS filesystem like the rest of
# ventilastation/, vs2.py, and main.py. All are flat top-level modules, not
# nested under ventilastation/: a frozen submodule nested inside an
# also-vfs-resident package is NOT reliably reachable once vfs has its own
# copy of that package (see vsdk_recovery.py's docstring for why, confirmed
# on hardware). boot.py only bootstraps a stub main.py when vfs has none at
# all -- it deliberately does NOT call vsdk_recovery.run() itself, since
# main.c's mp_usbd_init() (which activates the USB CDC device the REPL
# needs for Ctrl-C to work at all) only runs after boot.py returns; see
# boot.py's own docstring. updater.py has no ventilastation.* dependencies
# of its own and is genuinely bootstrap-critical, so it moved here too
# instead of staying vfs-only.
freeze(".", "boot.py")
freeze(".", "vsdk_recovery.py")
freeze(".", "vsdk_logo_strip.py")
freeze(".", "updater.py")
freeze(".", "vsdk_uart_log.py")

# these can go in the filesystem instead of frozen
# package("apps")
# package("libs")
