from os import set_blocking
import sys, utime

pipe=open(r'\\.\pipe\ventilastation-emu', "b+")
set_blocking(pipe.fileno(), False)

def receive(bufsize):
    try:
        got = pipe.read(bufsize)
        return got
    except:
        return ""

def send(line, data=b""):
    while True:
        try:
            pipe.write(line + "\n" + data)
            return
        except Exception as e:
            print("Buffer full, retrying", line, len(data))
            utime.sleep_ms(10)