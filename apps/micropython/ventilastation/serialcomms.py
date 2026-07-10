import machine
from ventilastation import board_config
from ventilastation.input_parser import InputParser

uart = machine.UART(
    board_config.get("serial_uart"),
    tx=board_config.get("serial_tx"),
    rx=board_config.get("serial_rx"),
    baudrate=board_config.get("serial_baud"),
)
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
