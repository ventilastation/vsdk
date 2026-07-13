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
from povrender import all_strips, set_palettes, spritedata
from povrender import clear_vs2_scene, set_vs2_scene
from povrender import set_voom_frame_rgb, clear_voom_frame
from audio import playsound, playmusic, playnotes
from emu_audio import emu_audio
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

    elif command == b"sprites":
        clear_voom_frame()
        clear_vs2_scene()
        spritedata[:] = conn.read(5*100)

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
        all_strips[slot_number] = conn.read(int(length))

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


def _receive_loop(conn, label):
    waitconnect(conn, label)
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
            waitconnect(conn, label)

        except Exception:
            print(traceback.format_exc())
            conn.close()
            waitconnect(conn, label)


def start():
    """Create the mode-appropriate connections and start the receive
    threads plus the OTA upgrade server. Call once, after config.configure()."""
    global display_conn, workbench_conn

    upgrade_server.start(port=5653)

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


def send(b):
    """Send raw bytes toward the DUT. In hardware mode these go over the
    workbench serial bridge; otherwise over the main display connection."""
    target = workbench_conn or display_conn
    if target is None:
        return
    try:
        target.send(b)
    except (socket.error, OSError) as err:
        print(err)

def send_joystick(joy1: int, joy2: int = 0, extra: int = 0):
    """Send a 4-byte joystick frame. Call once per game-loop tick."""
    send(bytes([0x2A, joy1 & 0x7F, joy2 & 0x7F, extra & 0x7F]))

def send_command(cmd: str):
    """Send a text command frame in-band on the existing connection."""
    send((cmd + '\n').encode('ascii'))

def trigger_ota():
    """Send ota_start in-band on the existing connection.

    Serial transports do not have a socket or a peer-derived local address, but
    the upgrade server still listens on the host's Wi-Fi/LAN interface. Prefer
    an explicit address, then a TCP connection's address, then the default
    network route so serial and Wi-Fi can be used together.
    """
    try:
        local_ip = _ota_server_ip()
        url = f"http://{local_ip}:5653"
        send_command(f"ota_start {url}")
        print(f"comms: sent ota_start (server at {url})")
    except Exception as e:
        print(f"comms: trigger_ota failed: {e}")


def _ota_server_ip():
    """Return a non-loopback address reachable by the board's Wi-Fi network."""
    if config.OTA_HOST:
        return config.OTA_HOST

    # A TCP display connection already tells us which local interface reaches
    # the board/workbench. This does not apply to pyserial's Serial object.
    sock = getattr(display_conn, "sock", None)
    getsockname = getattr(sock, "getsockname", None)
    if getsockname:
        local_ip = getsockname()[0]
        if local_ip and not local_ip.startswith("127."):
            return local_ip

    # UDP connect chooses the default network route without sending a packet.
    # It is the usual Wi-Fi address when the emulator talks to the board over
    # USB serial but serves the upgrade over the LAN.
    probe = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        probe.connect(("8.8.8.8", 80))
        local_ip = probe.getsockname()[0]
        if local_ip and not local_ip.startswith("127."):
            return local_ip
    finally:
        probe.close()

    # Some isolated LANs do not have a default route. Try host aliases before
    # asking the user to choose an address explicitly.
    for _, _, _, _, sockaddr in socket.getaddrinfo(socket.gethostname(), None, socket.AF_INET):
        local_ip = sockaddr[0]
        if local_ip and not local_ip.startswith("127."):
            return local_ip

    raise RuntimeError("cannot determine a LAN address; pass --ota-host <wifi-ip>")


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
