"""Host-side communications for the desktop emulator.

Owns the connection(s) to the frame source (local MicroPython, or a real
board via the workbench), dispatches the wire commands documented in
docs/internals/host-protocol.md, and forwards input. No connections or threads are
created at import time: emu.py calls start() once configuration is done.
"""

import os
import pathlib
import platform
import subprocess
import sys
import time
import traceback

import config
import struct
import socket
import threading
from base_control import BaseControlState
from povcal_state import PovCalibrationState
from povperf_controls import start_capture, stop_capture
from povrender import set_palettes, set_image_strip, set_spritedata
from povrender import clear_vs2_scene, set_vs2_scene
from povrender import (
    set_voom_frame_rgb,
    set_voom_frame_apa102,
    set_apa102_profile_payload,
    clear_voom_frame,
)
from workbench_telemetry import WorkbenchTelemetryClient
from audio import playsound, playmusic, playnotes, rescan_package_sounds
from emu_audio import emu_audio
from ota_controls import OTA_SERVER_URL, ota_start_command
import package_manager
import upgrade_server


# --- USB-id board registry (see docs/internals/building.md#selecting-a-board) ---
# tools/find_board.py keeps a local registry mapping each board's USB serial
# number to its kind (`make register-rotor`/`register-workbench`/
# `register-base`, one-time per board). _autodetect() below asks it via
# subprocess rather than importing find_board.py directly: find_board.py
# unconditionally imports termios (POSIX-only), which would break this
# module's Windows support at import time.
_REGISTER_TARGET = {"ventilastation": "register-rotor", "workbench": "register-workbench", "base": "register-base"}


def _registry_lookup(expected_kind):
    script = pathlib.Path(__file__).resolve().parents[1] / "tools" / "find_board.py"
    try:
        result = subprocess.run(
            [sys.executable, str(script), "--board", expected_kind],
            capture_output=True, text=True, timeout=5,
        )
    except (OSError, subprocess.TimeoutExpired):
        return None
    return result.stdout.strip() if result.returncode == 0 else None


class ConnectionBase:
    def __init__(self):
        self.sock = None
        self.sockfile = None

    def read(self, *args, **kwargs):
        return self.sockfile.read(*args, **kwargs)

    def readline(self):
        return self.sockfile.readline()

    def close(self):
        if self.sock:
            self.sock.close()

class ConnIP(ConnectionBase):
    def setup(self):
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        # Matches the workbench's own TCP_NODELAY (telemetry.c): this link
        # also carries small out-of-band "reset"/"rpm <n>" command lines
        # (see send_workbench()), which Nagle would otherwise hold back
        # waiting to coalesce with whatever's sent next.
        self.sock.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
        self.sock.connect((config.SERVER_IP, config.SERVER_PORT))
        self.sockfile = self.sock.makefile(mode="rb")

    def send(self, b):
        if self.sock:
            self.sock.send(b)

class ConnSerial(ConnectionBase):
    def __init__(self, expected_kind=None):
        super().__init__()
        # "workbench" or "ventilastation" (the rotor's legacy direct-serial
        # transport) -- used to look the right port up in the USB-id
        # registry instead of guessing by name pattern. None keeps the old
        # guess-only behavior.
        self.expected_kind = expected_kind

    def readline(self):
        # Don't rely on io.RawIOBase's built-in readline() here: pyserial's
        # Serial only exposes readinto() (serialutil.py), and on at least
        # some CPython versions (seen on 3.14) the C-level readline()
        # fallback for a peek-less RawIOBase ends up calling read() with
        # size=None instead of an int, crashing inside serialposix.py's
        # `size - len(read)`. Reading one byte at a time ourselves sidesteps
        # that machinery entirely.
        line = bytearray()
        while True:
            byte = self.sockfile.read(1)
            if not byte:
                break
            line += byte
            if byte == b"\n":
                break
        return bytes(line)

    def setup(self):
        import serial

        port = config.SERIAL_PORT or self._autodetect(self.expected_kind)
        if not port:
            raise socket.error("no serial port found (pass --serial-port /dev/tty... explicitly)")
        self.sock = self.sockfile = serial.Serial(port, 115200)

    @staticmethod
    def _autodetect(expected_kind=None):
        # Cross-platform: match common USB-serial naming across macOS
        # (cu.usbmodem*/cu.usbserial*) and Linux (ttyACM*/ttyUSB*) for the
        # workbench's USB bridge (and the rotor's own native USB-JTAG, for
        # the legacy direct-serial transport).
        candidates = []
        try:
            from serial.tools import list_ports
            candidates = [
                p.device for p in list_ports.comports()
                if any(tag in p.device for tag in ("usbmodem", "usbserial", "ttyACM", "ttyUSB"))
            ]
        except ImportError:
            pass

        if expected_kind:
            port = _registry_lookup(expected_kind)
            if port:
                return port
            register_target = _REGISTER_TARGET.get(expected_kind, "register-<kind>")
            print(f"comms: {expected_kind} not in the USB-id registry (run 'make {register_target}' "
                  "to identify it); guessing by port name instead")

        if candidates:
            return sorted(candidates)[0]

        # Legacy /dev scan (Super Ventilagon base on Raspberry Pi).
        try:
            devices = [
                f for f in os.listdir("/dev/")
                if f.startswith(config.SERIAL_DEVICE_RASPI2)
                or f.startswith(config.SERIAL_DEVICE_RASPI3)
            ]
        except FileNotFoundError:
            devices = []
        return "/dev/" + devices[0] if devices else None

    def send(self, b):
        if self.sockfile:
            self.sockfile.write(b)

class ConnWinNamedPipe(ConnectionBase):
    alreadysetup = False
    def setup(self):
        if self.alreadysetup:
            return
        import win32pipe

        self.pipe = win32pipe.CreateNamedPipe(
            r'\\.\pipe\ventilastation-emu',
            win32pipe.PIPE_ACCESS_DUPLEX,
            win32pipe.PIPE_TYPE_MESSAGE | win32pipe.PIPE_READMODE_MESSAGE | win32pipe.PIPE_WAIT,
            1, 65536 * 8, 65536 * 8, 0, None
        )

        self.buffer = b""
        self.alreadysetup = True

    def send(self, b):
        import win32file
        win32file.WriteFile(self.pipe, b)

    def read(self, numbytes):
        import win32file
        while len(self.buffer) < numbytes:
            try:
                result, data = win32file.ReadFile(self.pipe, 65536, None)
            except Exception:
                data = b""
            self.buffer += data
        ret, self.buffer = self.buffer[:numbytes], self.buffer[numbytes:]
        return ret

    def readline(self):
        import win32file
        while b"\n" not in self.buffer:
            try:
                result, data = win32file.ReadFile(self.pipe, 65536, None)
            except Exception:
                data = b""
            if not data:
                break
            self.buffer += data
        try:
            if b"\n" in self.buffer:
                ret, self.buffer = self.buffer.split(b"\n", 1)
                return ret
            else:
                return b""
        except Exception:
            print(traceback.format_exc())
            print("BUFFER WAS:", self.buffer)
            raise


class WorkbenchTelemetryConn:
    """UDP link to the hardware workbench's frame_apa102 telemetry (see
    docs/internals/workbench.md and hardware/workbench/workbench_esp32s3/
    main/telemetry.c for the wire format and the reasoning for UDP over
    TCP here: a live "latest wins" preview is hurt, not helped, by TCP's
    in-order/retransmit guarantee -- one lost segment head-of-line-blocks
    everything behind it instead of just leaving a few columns stale).

    Not a ConnectionBase subclass: the shared dispatch_command()/readline()
    machinery in this module assumes a byte-stream transport (TCP or
    serial). UDP is message-oriented and this link only ever carries one
    thing (frame_apa102 chunks) plus small outgoing control lines, so it
    gets its own minimal run loop (run(), started as its own thread by
    start()) instead of hooking into _receive_loop().
    """

    def __init__(self):
        self.client = WorkbenchTelemetryClient(config.SERVER_IP, config.SERVER_PORT)
        self.sock = None

    def setup(self):
        self.client.setup()
        self.sock = self.client.sock

    def send(self, b):
        try:
            self.client.send(b)
        except (socket.error, OSError) as err:
            print("comms: workbench-telemetry send failed:", err)

    def close(self):
        self.client.close()
        self.sock = None

    def run(self):
        """Receive/keepalive loop. Runs in its own daemon thread (see
        start()) for the lifetime of the process; reconnection isn't
        meaningful for a connectionless socket, so unlike _receive_loop()
        there's no waitconnect()/_connect() cycle -- just keep trying."""
        waitconnect(self, "workbench-telemetry")
        last_decode = 0.0
        announced_failure = False
        while looping:
            try:
                now = time.time()
                self.client.send_hello_if_due(now)

                try:
                    self.client.receive_once()
                except socket.timeout:
                    pass

                now = time.time()
                if now - last_decode >= 1 / 30:
                    # Copy and decode at a fixed pace. Missing UDP chunks
                    # remain stale in the persistent buffer but never block a
                    # newer preview from being shown.
                    set_voom_frame_apa102(self.client.snapshot().apa102)
                    last_decode = now
                announced_failure = False
            except (socket.error, OSError) as err:
                # Announce once per outage, same as waitconnect(): a dropped
                # workbench otherwise reprints this every 0.2s. Re-arms once
                # normal operation resumes above, so a later disconnection
                # still gets its own fresh message.
                if not announced_failure:
                    print("comms: workbench-telemetry:", err)
                    announced_failure = True
                time.sleep(0.2)
            except Exception:
                print(traceback.format_exc())
                time.sleep(0.2)

    def _handle_packet(self, data):
        return self.client.receiver.ingest(data)

looping = True

# Set by start():
# display_conn carries LED display frames plus (in hardware mode) reset/rpm
# control. It's the DUT link in every mode:
#   - Windows: named pipe to the local desktop MicroPython
#   - host arg "SERIAL": legacy single-transport serial link (Super
#     Ventilagon base) -- distinct from workbench_conn below
#   - otherwise: TCP, either loopback to the local desktop MicroPython or
#     (in hardware mode) to the workbench over Wi-Fi
display_conn = None
# workbench_conn carries button state out and audio/sound requests in, over
# the workbench's serial bridge to the DUT's UART -- only relevant when
# actually talking to real hardware.
workbench_conn = None

last_time_seen = 0
base_control = BaseControlState()
povcal_state = PovCalibrationState()

def waitconnect(conn, label):
    """Retry conn.setup() until it succeeds. Announces the failure once per
    outage (not on every 0.5s retry -- that spammed two lines/tick while a
    board was slow to boot or simply off) and always announces success."""
    announced_failure = False
    while looping:
        try:
            conn.setup()
            print(f"comms: {label} connected")
            return
        except (socket.error, OSError) as err:
            if not announced_failure:
                print(f"comms: {label}: {err}")
                announced_failure = True
            time.sleep(.5)


def dispatch_command(conn, command, args):
    """Handle one line command + whatever payload it declares, reading the
    payload from whichever connection (display_conn or workbench_conn) it
    arrived on. Shared between both receive loops so every command is
    understood regardless of which transport it comes in on -- in local
    simulation mode everything (including audio) arrives on display_conn;
    in hardware mode audio/sound arrives on workbench_conn instead (see
    docs/internals/workbench.md)."""
    global last_time_seen

    if command == b"frame_rgb":
        data = conn.read(256 * 54 * 3)
        set_voom_frame_rgb(data)

    elif command == b"frame_apa102":
        # Raw workbench capture: each spatial LED entry is the original
        # APA102 [GB, B, G, R] datum. Its global brightness must survive to
        # the preview decoder; do not reduce this to RGB bytes here.
        data = conn.read(256 * 54 * 4)
        set_voom_frame_apa102(data)

    elif command == b"povcal_state":
        if len(args) != 3:
            print("comms: malformed povcal_state", args)
            return
        schema_version, generation, length = (int(arg) for arg in args)
        payload = conn.read(length)
        try:
            profile = set_apa102_profile_payload(payload, schema_version, generation)
            povcal_state.apply(profile)
            print("comms: POV colour profile generation %d loaded" % profile.generation)
        except ValueError as error:
            povcal_state.reject(error)
            print("comms: rejected POV colour profile:", error)

    elif command == b"povcal_error":
        generation = args[0].decode() if args else "?"
        code = b" ".join(args[1:]).decode() if len(args) > 1 else "unknown"
        message = "board error #%s: %s" % (generation, code)
        povcal_state.reject(message)
        print("comms: POV colour calibration", message)

    elif command == b"sprites":
        clear_voom_frame()
        clear_vs2_scene()
        set_spritedata(conn.read(5*100))

    elif command == b"vs2_scene":
        clear_voom_frame()
        length = int(args[0]) if args else 0
        set_vs2_scene(conn.read(length))

    elif command == b"palette":
        paldata = conn.read(1024 * int(args[0]))
        set_palettes(paldata)
        print(f"DBG comms: palette received ({len(paldata)} bytes)")

    elif command == b"sound":
        playsound(b" ".join(args))

    elif command == b"notes":
        playnotes(args[0], args[1])

    elif command == b"arduino":
        arduino_send(b" ".join(args))

    elif command == b"base":
        line = base_control.apply(args)
        if line is None:
            print("comms: ignored malformed base command", args)
        else:
            arduino_send(line.encode("ascii"))

    elif command == b"music":
        # "music <track> [loop]" — the optional loop flag repeats the track.
        name = args[0] if args else b"off"
        playmusic(name, b"loop" in args[1:])

    elif command == b"musicstop":
        playmusic(b"off")

    elif command == b"achip":
        # Emulator started on the board: reset the matching host synth.
        # "achip <system> [<nbytes>]" + optional <nbytes> ROM filename payload
        # (cores whose fidelity needs actual ROM bytes, e.g. NES DMC).
        system = args[0] if args else b"unknown"
        rom_name = b""
        if len(args) > 1:
            nbytes = int(args[1])
            rom_name = conn.read(nbytes) if nbytes else b""
        emu_audio.start(system, rom_name)

    elif command == b"aframe":
        # One emulated video frame of sound-chip register writes.
        # "aframe <nbytes> <nsamples>" + <nbytes> payload.
        nbytes = int(args[0])
        nsamples = int(args[1]) if len(args) > 1 else 0
        payload = conn.read(nbytes) if nbytes else b""
        emu_audio.frame(payload, nsamples)

    elif command == b"amap":
        nbytes = int(args[0]) if args else 0
        payload = conn.read(nbytes) if nbytes else b""
        emu_audio.mapper_state(payload)

    elif command == b"astop":
        emu_audio.request_stop()

    elif command == b"imagestrip":
        slot, length = args
        slot_number = int(slot.decode())
        set_image_strip(slot_number, conn.read(int(length)))

    elif command == b"ota_progress":
        stage = args[0].decode() if args else "?"
        detail = args[1].decode() if len(args) > 1 else ""
        pct = args[2].decode() if len(args) > 2 else ""
        print(f"OTA [{stage}] {detail} {pct}%")

    elif command == b"ota_done":
        status = args[0].decode() if args else "?"
        print(f"OTA update complete: {status}")

    elif command == b"ota_error":
        msg = b" ".join(args).decode()
        print(f"OTA error: {msg}")

    elif command == b"install_progress":
        stage = args[0].decode() if args else "?"
        detail = args[1].decode() if len(args) > 1 else ""
        pct = args[2].decode() if len(args) > 2 else ""
        print(f"install [{stage}] {detail} {pct}%")
        package_manager.note_install_progress(stage, detail, pct)

    elif command == b"install_done":
        slug = args[0].decode() if args else "?"
        print(f"package install complete: {slug}")
        package_manager.note_install_done(slug)

    elif command == b"install_error":
        msg = b" ".join(args).decode()
        print(f"package install error: {msg}")
        package_manager.note_install_error(msg)

    elif command == b"traceback":
        length = args[0]
        tb = conn.read(int(length))
        print("-------------------------------------")
        print("Rotor traceback")
        print("-------------------------------------")
        print(tb.decode("utf-8"))
        print("-------------------------------------")

    elif command == b"info":
        # Hardware Python stdout is carried as a length-delimited payload so
        # spaces and UTF-8 text cannot be mistaken for protocol arguments.
        length = int(args[0]) if args else 0
        message = conn.read(length).decode("utf-8", "replace")
        print(message)

    elif command == b"debug":
        length = 32 * 16
        data = conn.read(length)

        readings = []
        for now, duration in struct.iter_unpack("qq", data):
            if now < 10000:
                last_time_seen = 0

            if now > last_time_seen:
                last_time_seen = now
                rpm, fps = 1000000 / duration * 60, (1000000/duration)*2
                print(now, duration, "(%.2f rpm, %.2f fps)" % (rpm, fps))
                readings.append(rpm)

        if len(readings):
            avg_rpm = sum(readings) / len(readings)
            avg_fps = avg_rpm / 30
            print("average %.2f rpm %.2f fps" % (avg_rpm, avg_fps))

    else:
        print(command, *args)


def _request_povcal_profile(conn, label):
    if conn is not workbench_conn:
        return
    try:
        conn.send(b"povcal get\n")
        print("comms: requested POV colour profile")
    except (socket.error, OSError) as err:
        print("comms: POV colour profile request failed:", err)


def _connect(conn, label):
    waitconnect(conn, label)
    _request_povcal_profile(conn, label)


def _receive_loop(conn, label):
    _connect(conn, label)
    while looping:
        try:
            l = conn.readline()
            if not l:  # b"" = EOF, connection closed by remote end
                raise socket.error("connection closed")
            l = l.strip()
            if not l:
                continue

            command, *args = l.split()
            dispatch_command(conn, command, args)

        except socket.error as err:
            print(f"comms: {label}: {err}")
            _connect(conn, label)

        except Exception:
            print(traceback.format_exc())
            conn.close()
            _connect(conn, label)


def start():
    """Create the mode-appropriate connections and start the receive
    threads and (unless disabled) the OTA upgrade server. Call once, after
    config.configure()."""
    global display_conn, workbench_conn

    upgrade_server.trigger_install = trigger_install
    upgrade_server.on_package_saved = _on_package_saved
    if config.OTA_SERVER_ENABLED:
        upgrade_server.start(port=5653)
    else:
        print("comms: local OTA server disabled; using ventilastation-base.local")

    if platform.system() == "Windows":
        display_conn = ConnWinNamedPipe()
    elif not config.USE_IP:
        display_conn = ConnSerial(expected_kind="ventilastation")
    elif config.HARDWARE_MODE:
        # Real DUT via the workbench: frame_apa102 arrives over UDP (see
        # WorkbenchTelemetryConn) instead of the shared TCP-framed protocol
        # every other transport uses.
        display_conn = WorkbenchTelemetryConn()
    else:
        display_conn = ConnIP()

    workbench_conn = ConnSerial(expected_kind="workbench") if (config.HARDWARE_MODE and config.USE_IP) else None

    if isinstance(display_conn, WorkbenchTelemetryConn):
        display_thread = threading.Thread(target=display_conn.run)
    else:
        display_thread = threading.Thread(target=_receive_loop, args=(display_conn, "display"))
    display_thread.daemon = True
    display_thread.start()

    if workbench_conn:
        workbench_thread = threading.Thread(target=_receive_loop, args=(workbench_conn, "workbench-serial"))
        workbench_thread.daemon = True
        workbench_thread.start()

    _arduino_init()
    arduino_send(b"attract")


def shutdown():
    global looping
    looping = False
    if display_conn:
        display_conn.close()
    if workbench_conn:
        workbench_conn.close()


# The pyglet thread streams joystick frames while the upgrade server's HTTP
# thread may send install_start; serialize writes so command lines can't
# interleave with a frame mid-transfer.
_send_lock = threading.Lock()


def send(b):
    """Send raw bytes toward the DUT. In hardware mode these go over the
    workbench serial bridge; otherwise over the main display connection."""
    target = workbench_conn or display_conn
    if target is None:
        return
    try:
        with _send_lock:
            target.send(b)
    except (socket.error, OSError) as err:
        print(err)

def send_joystick(joy1: int, joy2: int = 0, extra: int = 0):
    """Send a 4-byte joystick frame. Call once per game-loop tick."""
    send(bytes([0x2A, joy1 & 0x7F, joy2 & 0x7F, extra & 0x7F]))

def send_command(cmd: str):
    """Send a text command frame in-band on the existing connection."""
    send((cmd + '\n').encode('ascii'))


def send_povcal(command: str):
    """Send one calibration command to the connected board/base transport."""
    send_command("povcal " + command)


def start_povperf_capture(encoder: str):
    """Start a fresh on-device POV timing capture for ``encoder``.

    Selecting an encoder clears the board's timing window, so keeping the two
    commands together prevents a UI click from accidentally mixing legacy and
    calibrated samples.
    """
    start_capture(encoder, send_command)


def stop_povperf_capture():
    """End the on-device POV timing capture.

    The board responds to ``povperf stop`` with its final state and timing
    lines, which the emulator's regular command receiver prints to stdout.
    """
    stop_capture(send_command)


_hall_filter_enabled = True  # emulator-side assumption; the device's own state is authoritative


def toggle_hall_filter():
    """Flip the POV hall-pulse filter (see hall_filter.c) vs. the pre-filter
    raw passthrough, live on the connected board -- lets the F5 key A/B
    compare the two without reflashing. The device echoes back a
    ``hallfilter_state ...`` line (printed by the generic fallback in
    dispatch_command()) confirming what actually took effect."""
    global _hall_filter_enabled
    _hall_filter_enabled = not _hall_filter_enabled
    send_command("hallfilter " + ("on" if _hall_filter_enabled else "off"))


def trigger_ota():
    """Request an OTA from the mDNS-advertised Ventilastation base server."""
    try:
        send_command(ota_start_command())
        print(f"comms: sent ota_start (server at {OTA_SERVER_URL})")
    except Exception as e:
        print(f"comms: trigger_ota failed: {e}")


def trigger_install(slug):
    """Ask the board to fetch and install one uploaded package: builds (or
    reuses) the stripped .no-sound.vs2 and names exactly that file in the
    install_start command -- no manifest sync involved."""
    _data, sha, size = package_manager.get_board_file(slug)
    url = f"{OTA_SERVER_URL}/packages/{slug}{package_manager.BOARD_SUFFIX}"
    send_command(f"install_start {url} {sha} {size}")
    package_manager.note_install_triggered(slug)
    print(f"comms: sent install_start for {slug} ({size} bytes)")


def _on_package_saved(slug):
    print(f"comms: package {slug} uploaded")
    rescan_package_sounds(slug)


def send_workbench(line):
    """Send a control command line to the workbench over Wi-Fi, e.g.
    b"reset" or b"rpm 650" (see the RPM slider / reset button in
    pyglet2x/pygletdraw.py). No-op if the Wi-Fi link isn't up."""
    if display_conn is None:
        return
    try:
        display_conn.send(line + b"\n")
    except (socket.error, OSError) as err:
        print(err)


# --- Super Ventilagon base: dedicated Arduino driving the start/stop relay ---

# Fixed GPIO UART on a deployed Raspberry Pi Base -- not USB-enumerable, so
# it can't be in the USB-id registry below. Kept as the fallback for that
# real deployed case; a bench-tested Arduino on its own USB-to-serial
# adapter is found via the registry first, same as the workbench/rotor in
# ConnSerial (register it with `make register-base`).
ARDUINO_DEVICE = "/dev/ttyAMA0"
_arduino = None
_arduino_commands = {
    b"start": b"S",
    b"stop": b"r",
    b"reset": b"R",
    b"attract": b"s"
}

def _find_arduino_port():
    port = _registry_lookup("base")
    if port:
        return port
    if os.path.exists(ARDUINO_DEVICE):
        return ARDUINO_DEVICE
    return None

def _arduino_init():
    global _arduino
    try:
        import serial
        port = _find_arduino_port()
        if not port:
            raise OSError("no base Arduino found")
        _arduino = serial.Serial(port, 57600)
    except Exception:
        print("NOTE: Super Ventilagon base - Arduino not detected")
        _arduino = None

def arduino_send(command):
    if _arduino is None:
        return
    # New base commands are complete canonical lines. The one-byte map stays
    # only for the Super Ventilagon timer compatibility period.
    _arduino.write(_arduino_commands.get(command, command if command.startswith(b"base ") else b" "))
