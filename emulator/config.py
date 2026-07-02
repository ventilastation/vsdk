import sys
FULLSCREEN = False

# --remote / --no-display (see emu.py) mean "talk to a real DUT through the
# hardware workbench" instead of the local simulated MicroPython. In that
# mode comms.py opens two separate links to the workbench:
#   - Wi-Fi (TCP): LED display frames, and "reset"/"rpm" control
#   - Serial: button state out, audio/sound requests in (the same traffic
#     that would normally cross the DUT<->base UART link)
# See vsdk/WORKBENCH.md.
HARDWARE_MODE = "--remote" in sys.argv or "--no-display" in sys.argv

USE_IP = True
SERIAL_DEVICE_RASPI2 = "ttyUSB"
SERIAL_DEVICE_RASPI3 = "ttyACM"

_args = sys.argv[1:]

# Optional explicit serial port for the workbench's USB bridge (see
# comms.py's ConnSerial). Auto-detected if not given.
SERIAL_PORT = None
if "--serial-port" in _args:
    _idx = _args.index("--serial-port")
    SERIAL_PORT = _args[_idx + 1]
    del _args[_idx:_idx + 2]  # don't let the port path be mistaken for the host arg below

# A bare positional arg (not starting with "-") is a host override: either
# an explicit IP/hostname, or the literal "SERIAL" to force the legacy
# serial-only transport (used by the Super Ventilagon base, distinct from
# the workbench's separate button/audio serial link above).
_host_arg = next((a for a in _args if not a.startswith("-")), None)

if _host_arg == "SERIAL":
    USE_IP = False
    SERVER_IP = None
elif _host_arg:
    SERVER_IP = _host_arg
elif HARDWARE_MODE:
    # Found via mDNS (see WORKBENCH.md) instead of a hardcoded IP. .local
    # resolution is built into macOS (Bonjour); Linux needs avahi/nss-mdns,
    # Windows needs Bonjour/iTunes installed. Override with an explicit
    # positional IP if mDNS isn't available on your machine.
    SERVER_IP = "ventilastation-workbench.local"
else:
    SERVER_IP = "127.0.0.1"  # local desktop MicroPython subprocess

SERVER_PORT = 5005
