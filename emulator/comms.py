"""Host-side communications for the desktop emulator.

Owns the connection(s) to the frame source (local MicroPython, or a real
board via the workbench), dispatches the wire commands documented in
docs/internals/host-protocol.md, and forwards input. No connections or threads are
created at import time: emu.py calls start() once configuration is done.
"""

import os
import platform
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
from audio import playsound, playmusic, playnotes, rescan_package_sounds
from emu_audio import emu_audio
from ota_controls import OTA_SERVER_URL, ota_start_command
import package_manager
import upgrade_server


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
        self.sock.connect((config.SERVER_IP, config.SERVER_PORT))
        self.sockfile = self.sock.makefile(mode="rb")

    def send(self, b):
        if self.sock:
            self.sock.send(b)

class ConnSerial(ConnectionBase):
    def setup(self):
        import serial

        port = config.SERIAL_PORT or self._autodetect()
        if not port:
            raise socket.error("no serial port found (pass --serial-port /dev/tty... explicitly)")
        self.sock = self.sockfile = serial.Serial(port, 115200)

    @staticmethod
    def _autodetect():
        # Cross-platform: match common USB-serial naming across macOS
        # (cu.usbmodem*/cu.usbserial*) and Linux (ttyACM*/ttyUSB*) for the
        # workbench's USB bridge.
        try:
            from serial.tools import list_ports
            candidates = [
                p.device for p in list_ports.comports()
                if any(tag in p.device for tag in ("usbmodem", "usbserial", "ttyACM", "ttyUSB"))
            ]
            if candidates:
                return sorted(candidates)[0]
        except ImportError:
            pass

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
    while looping:
        try:
            conn.setup()
            print(f"comms: {label} connected")
            return
        except (socket.error, OSError) as err:
            print(f"comms: {label}: {err}")
            time.sleep(.5)
            print(f"comms: {label} retry...")


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
        emu_audio.start(args[0] if args else b"unknown")

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
        display_conn = ConnSerial()
    else:
        display_conn = ConnIP()

    workbench_conn = ConnSerial() if (config.HARDWARE_MODE and config.USE_IP) else None

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

ARDUINO_DEVICE = "/dev/ttyAMA0"
_arduino = None
_arduino_commands = {
    b"start": b"S",
    b"stop": b"r",
    b"reset": b"R",
    b"attract": b"s"
}

def _arduino_init():
    global _arduino
    try:
        import serial
        _arduino = serial.Serial(ARDUINO_DEVICE, 57600)
    except Exception:
        print("NOTE: Super Ventilagon base - Arduino not detected")
        _arduino = None

def arduino_send(command):
    if _arduino is None:
        return
    # New base commands are complete canonical lines. The one-byte map stays
    # only for the Super Ventilagon timer compatibility period.
    _arduino.write(_arduino_commands.get(command, command if command.startswith(b"base ") else b" "))
