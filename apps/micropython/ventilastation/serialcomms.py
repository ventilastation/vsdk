import machine
from ventilastation.hw_config import serial_rx, serial_tx
from ventilastation.input_parser import InputParser

uart    = machine.UART(2, tx=serial_tx, rx=serial_rx)
_parser = InputParser()

def _drain():
    chunk = uart.read(64)
    if chunk:
        _parser.feed(chunk)

def receive(bufsize):
    _drain()
    return bytes([_parser.joy1])

def next_command():
    _drain()
    return _parser.pop_command()

def next_joy2():
    return _parser.joy2

def next_extra():
    return _parser.extra

def send(line, data=b""):
    uart.write(line)
    uart.write("\n")
    if data:
        uart.write(data)
