import os
import platform
import time
import traceback

import config
import struct
import socket
import threading
from pygletengine import all_strips, set_palettes, spritedata
from vsdk import set_voom_frame, set_voom_frame_rgb, clear_voom_frame
from audio import playsound, playmusic, playnotes
from emu_audio import emu_audio
import upgrade_server

upgrade_server.start(port=8000)

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
    # Lazily-created, reused across setup() calls/retries so we don't spin
    # up a fresh mDNS listener every 0.5s while waiting for the workbench.
    _zc = None

    @staticmethod
    def _resolve_via_dns_sd(hostname, timeout=3.0):
        """macOS only: resolve via the system's own `dns-sd` binary instead
        of opening our own mDNS socket. Some machines silently drop the
        incoming multicast responses a Python-owned socket needs (macOS's
        per-app firewall can block a venv's less-trusted/unsigned
        interpreter from receiving UDP, even though the same interpreter
        can still *send* -- so the query goes out but no reply ever comes
        back); `dns-sd` is an Apple-signed system tool that isn't subject to
        that. Returns an IP string, or None if dns-sd isn't available or
        didn't resolve within timeout.

        dns-sd fully-buffers its stdout when it isn't a tty, so a plain
        subprocess.PIPE would sit empty until the process exits (dns-sd
        itself never exits on its own) -- a pty forces it to line-buffer
        like it would in an interactive terminal."""
        import os
        import pty
        import re
        import select
        import shutil
        import subprocess

        tool = shutil.which("dns-sd")
        if not tool:
            return None

        master_fd, slave_fd = pty.openpty()
        try:
            proc = subprocess.Popen([tool, "-G", "v4", hostname], stdout=slave_fd, stderr=subprocess.DEVNULL)
        except OSError:
            os.close(master_fd)
            os.close(slave_fd)
            return None
        os.close(slave_fd)

        pattern = re.compile(r"Add\s+\S+\s+\S+\s+\S+\s+(\d+\.\d+\.\d+\.\d+)")
        deadline = time.time() + timeout
        result = None
        buf = b""
        try:
            while time.time() < deadline:
                ready, _, _ = select.select([master_fd], [], [], deadline - time.time())
                if not ready:
                    break
                try:
                    chunk = os.read(master_fd, 4096)
                except OSError:
                    break
                if not chunk:
                    break
                buf += chunk
                while b"\n" in buf:
                    line, buf = buf.split(b"\n", 1)
                    m = pattern.search(line.decode(errors="replace"))
                    if m:
                        result = m.group(1)
                        break
                if result:
                    break
        finally:
            proc.kill()
            try:
                proc.wait(timeout=1)
            except Exception:
                pass
            os.close(master_fd)
        return result

    def _resolve_mdns(self, timeout=3.0):
        """Resolve the workbench's address: try the OS's own mDNS tooling
        first where available (see _resolve_via_dns_sd), then fall back to
        resolving the _ventilastation-wb._tcp service directly via
        zeroconf. Both exist because relying on socket.getaddrinfo()'s
        ".local" handling is unreliable -- plenty of Python builds don't get
        the same Bonjour ".local" special-casing macOS CLI tools and the
        system Python get, and fail instantly without even attempting an
        mDNS query. See vsdk/WORKBENCH.md."""
        ip = self._resolve_via_dns_sd(f"{config.MDNS_HOSTNAME}.local", timeout)
        if ip:
            return ip, config.SERVER_PORT

        from zeroconf import Zeroconf

        if ConnIP._zc is None:
            ConnIP._zc = Zeroconf()

        full_name = f"{config.MDNS_INSTANCE_NAME}.{config.MDNS_SERVICE_TYPE}"
        info = ConnIP._zc.get_service_info(config.MDNS_SERVICE_TYPE, full_name, timeout=timeout * 1000)
        if info and info.parsed_addresses():
            return info.parsed_addresses()[0], info.port
        return None

    def setup(self):
        if config.RESOLVE_MDNS:
            resolved = self._resolve_mdns()
            if not resolved:
                raise socket.error(f'mDNS: "{config.MDNS_INSTANCE_NAME}" not found on the network yet')
            host, port = resolved
            print(f"comms: resolved {config.MDNS_INSTANCE_NAME} via mDNS -> {host}:{port}")
        else:
            host, port = config.SERVER_IP, config.SERVER_PORT

        self.sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.sock.connect((host, port))
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
            except:
                data = b""
            self.buffer += data
        ret, self.buffer = self.buffer[:numbytes], self.buffer[numbytes:]
        return ret

    def readline(self):
        import win32file
        while b"\n" not in self.buffer:
            try:
                result, data = win32file.ReadFile(self.pipe, 65536, None)
            except:
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
        except:
            print(traceback.format_exc())
            print("BUFFER WAS:", self.buffer)
            raise

looping = True

# display_conn carries LED display frames plus (in hardware mode)
# reset/rpm control. It's the DUT link in every mode:
#   - Windows: named pipe to the local desktop MicroPython
#   - "SERIAL" positional arg: legacy single-transport serial link (Super
#     Ventilagon base) -- distinct from workbench_conn below
#   - otherwise: TCP, either loopback to the local desktop MicroPython or
#     (in hardware mode) to the workbench over Wi-Fi
if platform.system() == "Windows":
    display_conn = ConnWinNamedPipe()
elif not config.USE_IP:
    display_conn = ConnSerial()
else:
    display_conn = ConnIP()

# workbench_conn carries button state out and audio/sound requests in, over
# the workbench's serial bridge to the DUT's UART -- only relevant when
# actually talking to real hardware.
workbench_conn = ConnSerial() if (config.HARDWARE_MODE and config.USE_IP) else None

last_time_seen = 0

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
    vsdk/WORKBENCH.md)."""
    global last_time_seen

    if command == b"frame":
        data = conn.read(256 * 54)
        set_voom_frame(data)

    elif command == b"frame_rgb":
        data = conn.read(256 * 54 * 3)
        set_voom_frame_rgb(data)

    elif command == b"sprites":
        clear_voom_frame()
        spritedata[:] = conn.read(5*100)

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

    elif command == b"music":
        # "music <track> [loop]" — the optional loop flag repeats the track.
        name = args[0] if args else b"off"
        playmusic(name, b"loop" in args[1:])

    elif command == b"musicstop":
        playmusic(b"off")

    elif command == b"achip":
        # Emulator started on the board: reset the matching host synth.
        emu_audio.start(args[0] if args else b"unknown", args[1:])

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


def shutdown():
    global looping
    looping = False
    display_conn.close()
    if workbench_conn:
        workbench_conn.close()

display_thread = threading.Thread(target=_receive_loop, args=(display_conn, "display"))
display_thread.daemon = True
display_thread.start()

if workbench_conn:
    workbench_thread = threading.Thread(target=_receive_loop, args=(workbench_conn, "workbench-serial"))
    workbench_thread.daemon = True
    workbench_thread.start()

def send(b):
    """Send raw bytes toward the DUT. In hardware mode these go over the
    workbench serial bridge; otherwise over the main display connection."""
    target = workbench_conn or display_conn
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
    """Send ota_start in-band on the existing connection."""
    try:
        local_ip = display_conn.sock.getsockname()[0]
        url = f"http://{local_ip}:8000"
        send_command(f"ota_start {url}")
        print(f"comms: sent ota_start (server at {url})")
    except Exception as e:
        print(f"comms: trigger_ota failed: {e}")


def send_workbench(line):
    """Send a control command line to the workbench over Wi-Fi, e.g.
    b"reset" or b"rpm 650" (see the RPM slider / reset button in
    pyglet2x/pygletdraw.py). No-op if the Wi-Fi link isn't up."""
    try:
        display_conn.send(line + b"\n")
    except (socket.error, OSError) as err:
        print(err)


try:
    import serial
    ARDUINO_DEVICE = "/dev/ttyAMA0"
    arduino = serial.Serial(ARDUINO_DEVICE, 57600)

    arduino_commands = {
        b"start": b"S",
        b"stop": b"r",
        b"reset": b"R",
        b"attract": b"s"
    }

    def arduino_send(command):
        # print("arduino, sending", command)
        arduino.write(arduino_commands.get(command, b" "))

except Exception as e:
    print("NOTE: Super Ventilagon base - Arduino not detected")

    def arduino_send(_):
        pass

arduino_send(b"attract")
