"""Desktop emulator configuration.

Populated by configure() from emu.py's argparse results; every other module
reads the module-level values at runtime. Importing this module has no side
effects and leaves the defaults below in place (local simulation mode).
"""

FULLSCREEN = False

# --remote / --no-display mean "talk to a real DUT through the hardware
# workbench" instead of the local simulated MicroPython. In that mode
# comms.py opens two separate links to the workbench:
#   - Wi-Fi (TCP): LED display frames, and "reset"/"rpm" control
#   - Serial: button state out, audio/sound requests in (the same traffic
#     that would normally cross the DUT<->base UART link)
# See WORKBENCH.md.
HARDWARE_MODE = False

# False only for the legacy serial-only transport (Super Ventilagon base).
USE_IP = True

# Render the POV window (False = input/audio host only, physical LEDs are
# the display).
DISPLAY_ENABLED = True

# Explicit serial port for the workbench's USB bridge (see comms.ConnSerial).
# Auto-detected when None.
SERIAL_PORT = None

SERIAL_DEVICE_RASPI2 = "ttyUSB"
SERIAL_DEVICE_RASPI3 = "ttyACM"

SERVER_IP = "127.0.0.1"  # local desktop MicroPython subprocess
SERVER_PORT = 5005


def configure(args):
    """Apply parsed command-line arguments (see emu.py)."""
    global HARDWARE_MODE, USE_IP, DISPLAY_ENABLED, SERIAL_PORT, SERVER_IP

    HARDWARE_MODE = args.remote or args.no_display
    DISPLAY_ENABLED = not args.no_display
    SERIAL_PORT = args.serial_port

    # The positional host is either an IP/hostname, or the literal "SERIAL"
    # to force the legacy serial-only transport (Super Ventilagon base,
    # distinct from the workbench's button/audio serial link above).
    if args.host == "SERIAL":
        USE_IP = False
        SERVER_IP = None
    elif args.host:
        SERVER_IP = args.host
    elif HARDWARE_MODE:
        # Found via mDNS (see WORKBENCH.md) instead of a hardcoded IP. .local
        # resolution is built into macOS (Bonjour); Linux needs avahi/nss-mdns,
        # Windows needs Bonjour/iTunes installed. Override with an explicit
        # positional IP if mDNS isn't available on your machine.
        SERVER_IP = "ventilastation-workbench.local"
    else:
        SERVER_IP = "127.0.0.1"
