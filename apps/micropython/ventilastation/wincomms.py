"""Desktop named-pipe transport, using the same v2 parser as TCP."""
from os import set_blocking
import utime
from ventilastation.input_parser import InputParser

pipe = open(r'\\.\pipe\ventilastation-emu', 'b+')
set_blocking(pipe.fileno(), False)
_parser = InputParser()
_new_connection = True


def was_new_connection():
    global _new_connection
    result = _new_connection
    _new_connection = False
    return result


def receive(_bufsize):
    try:
        data = pipe.read(64)
    except OSError as error:
        if error.args[0] not in (11, 35, 232):
            raise
        data = None
    if data:
        _parser.feed(data)
    return bytes((_parser.joy1,))


def next_command():
    return _parser.pop_command()


def next_joy2():
    return _parser.joy2


def next_extra():
    return _parser.extra


def ventilagon_is_idle():
    return _parser.ventilagon_idle


def ventilagon_error():
    return _parser.ventilagon_error


def send(line, data=b''):
    if isinstance(line, str):
        line = line.encode()
    if line.startswith(b'ventilagon enter '):
        _parser.ventilagon_idle = False
        _parser.ventilagon_error = None
    message = memoryview(line + b'\n' + data)
    sent = 0
    while sent < len(message):
        try:
            count = pipe.write(message[sent:])
            if count:
                sent += count
            else:
                utime.sleep_ms(10)
        except OSError as error:
            if error.args[0] not in (11, 35, 232):
                raise
            utime.sleep_ms(10)
