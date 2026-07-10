"""Desktop-platform comms: TCP server on port 5005 that the desktop
emulator (emulator/emu.py) connects to. The board never uses this module;
hardware uses serialcomms (WiFi comes up only for OTA, see updater.py)."""

import uselect
import usocket
from ventilastation.input_parser import InputParser

UDP_THIS = "0.0.0.0", 5005
this_addr = usocket.getaddrinfo(*UDP_THIS)[0][-1]

sock = usocket.socket(usocket.AF_INET, usocket.SOCK_STREAM)
sock.setsockopt(usocket.SOL_SOCKET, usocket.SO_REUSEADDR, 1)
sock.bind(this_addr)
sock.listen(10)
sock.setblocking(0)
print("listening on 5005")

poller = uselect.poll()
poller.register(sock, uselect.POLLIN)
conn = None
_new_connection = False
_parser = InputParser()

def was_new_connection():
    global _new_connection
    if _new_connection:
        _new_connection = False
        return True
    return False

def receive(bufsize):
    global conn, _new_connection
    for obj, event, *more in poller.ipoll(0, 0):
        if obj is sock:
            if conn:
                conn.close()
                poller.unregister(conn)
            conn, addr = sock.accept()
            conn.setblocking(0)
            poller.register(conn, uselect.POLLIN)
            _new_connection = True
            _parser.reset()
            print("comms: new connection from", addr)
        else:
            try:
                chunk = obj.read(64)
            except OSError:
                chunk = None
            if chunk:
                _parser.feed(chunk)
            else:
                obj.close()
                poller.unregister(obj)
                conn = None
                _parser.reset()
    return bytes([_parser.joy1]) if conn else None


def next_command():
    return _parser.pop_command()

def next_joy2():
    return _parser.joy2

def next_extra():
    return _parser.extra

def _drop_conn(reason):
    global conn
    print("comms: drop connection:", reason)
    conn.close()
    poller.unregister(conn)
    conn = None

def send(line, data=b""):
    global conn
    if conn:
        msg = line + b"\n" + data
        view = memoryview(msg)
        sent = 0
        while sent < len(msg):
            try:
                n = conn.write(view[sent:])
                if n is None:
                    n = 0
                sent += n
            except OSError as e:
                if e.args[0] == 11:  # EAGAIN: buffer full, retry
                    continue
                _drop_conn("OSError %d" % e.args[0])
                return
