import asyncio
import os
import platform
import signal
import time
import traceback

import config
import struct
import socket
import threading
from pygletengine import all_strips, set_palettes, spritedata
from audio import playsound, playmusic, playnotes

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
        device = [f for f in os.listdir("/dev/") if f.startswith(config.SERIAL_DEVICE)][0]
        self.sock = self.sockfile = serial.Serial("/dev/" + device, 115200)

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

if platform.system() == "Windows":
    conn = ConnWinNamedPipe()
elif config.USE_IP:
    conn = ConnIP()
else:
    conn = ConnSerial()

def waitconnect():
    while looping:
        try:
            conn.setup()
            return
        except socket.error as err:
            print(err)
            time.sleep(.5)
            print("retry...")


def receive_loop():
    last_time_seen = 0

    waitconnect()
    while looping:
        try:
            l = conn.readline()
            l = l.strip()
            if not l:
                continue

            command, *args = l.split()
            # print("RECEIVED", command, args)

            if command == b"sprites":
                spritedata[:] = conn.read(5*100)

            elif command == b"palette":
                paldata = conn.read(1024 * int(args[0]))
                set_palettes(paldata)

            elif command == b"sound":
                playsound(b" ".join(args))

            elif command == b"notes":
                playnotes(args[0], args[1])

            elif command == b"arduino":
                arduino_send(b" ".join(args))

            elif command == b"music":
                playmusic(b" ".join(args))

            elif command == b"musicstop":
                playmusic("off")

            elif command == b"imagestrip":
                # print("RECEIVED imagestrip", args)
                slot, length = args
                slot_number = int(slot.decode())
                all_strips[slot_number] = conn.read(int(length))

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
                    #send_velocidad(avg_rpm, avg_fps)
                #print(struct.unpack("q"*32*2, data))

            else:
                print(command, *args)



        except socket.error as err:
            print(err)
            waitconnect()

        except Exception as err:
            print(traceback.format_exc())
            conn.close()
            waitconnect()


def shutdown():
    global looping
    looping = False
    conn.close()

receive_thread = threading.Thread(target=receive_loop)
receive_thread.daemon = True
receive_thread.start()

def send(b):
    try:
        conn.send(b)
    except socket.error as err:
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

