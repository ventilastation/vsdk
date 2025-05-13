from os import set_blocking
import sys

pipe=open(r'\\.\pipe\ventilastation-emu', "b+")
set_blocking(pipe.fileno(), False)

def receive(bufsize):
    try:
        got = pipe.read(bufsize)
        # print("UPY GOT:", repr(got))
        return got
    except:
        return ""

counter = 0

def send(line, data=b""):
    global counter
    try:
        pipe.write(line + "\n")
        if data:
            pipe.write(data)
        # print("SENT", line, "+", len(data), "bytes")
        counter += 1
    except Exception as e:
        print("COUNTER, ERROR, line, datalen", counter, e, line, len(data))
        sys.print_exception(e)