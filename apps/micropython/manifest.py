freeze("$(PORT_DIR)/modules")
module("vsdk_board.py")

# Recovery must work with no vfs content at all (a fresh board only has
# factory + NVS), so it and everything it needs are frozen into the
# firmware rather than living on the LittleFS filesystem like the rest of
# ventilastation/, vs2.py, and main.py. All three are flat top-level
# modules, not nested under ventilastation/: a frozen submodule nested
# inside an also-vfs-resident package is NOT reliably reachable once vfs
# has its own copy of that package (see vsdk_recovery.py's docstring for
# why, confirmed on hardware). vsdk_recovery_entry.py is kept separate from
# vsdk_recovery.py specifically so its name never collides with "main.py"
# -- freezing that name would permanently shadow the real, vfs-resident,
# OTA-updatable main.py. updater.py has no ventilastation.* dependencies of
# its own and is genuinely bootstrap-critical, so it moved here too instead
# of staying vfs-only.
freeze(".", "vsdk_recovery_entry.py")
freeze(".", "vsdk_recovery.py")
freeze(".", "vsdk_logo_strip.py")
freeze(".", "updater.py")

# these can go in the filesystem instead of frozen
# package("apps")
# package("libs")
