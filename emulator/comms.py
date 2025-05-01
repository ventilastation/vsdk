import asyncio
import os
import signal
import time

import config
import struct
import socket
import threading
from pygletengine import imagenes, palette, spritedata, playsound, playmusic

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
    pass

looping = True

if config.USE_IP:
    conn = ConnIP()
else:
    conn = ConnSerial()

def waitconnect():
    print("conectando...")
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

            if command == b"sprites":
                spritedata[:] = conn.read(5*100)

            if command == b"pal":
                palette[:] = conn.read(1024)

            if command == b"sound":
                playsound(b" ".join(args))

            if command == b"arduino":
                arduino_send(b" ".join(args))

            if command == b"music":
                playmusic(b" ".join(args))

            if command == b"musicstop":
                playmusic("off")

            if command == b"imagestrip":
                length, slot = args
                imagenes.all_strips[int(slot.decode())] = conn.read(int(length))

            if command == b"debug":
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


        except socket.error as err:
            print(err)
            waitconnect()

        except Exception as err:
            print(err)
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
        print("arduino, sending", command)
        arduino.write(arduino_commands.get(command, b" "))

except Exception as e:
    print(e)

    def arduino_send(_):
        pass

