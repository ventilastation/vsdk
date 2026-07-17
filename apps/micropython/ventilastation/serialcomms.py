import machine
import sys
from ventilastation import board_config, version
from ventilastation.console_resync import ConsoleResyncScanner
from ventilastation.input_parser import InputParser
from ventilastation.uart_logging import InfoWriter

uart = machine.UART(
    board_config.get("serial_uart"),
    tx=board_config.get("serial_tx"),
    rx=board_config.get("serial_rx"),
    baudrate=board_config.get("serial_baud"),
)
_parser = InputParser()
_console_scanner = ConsoleResyncScanner()

# RESYNC identification banner: the first thing this device puts on the wire
# after any reset (including a RESYNC-triggered one), sent to both the
# dedicated base-station UART and the console (UART0-REPL/USB-Serial-JTAG),
# since RESYNC can arrive on either -- see console_resync.py and
# docs/internals/input-protocol-v2.md#resync--device-identification. Written
# raw to the UART rather than via print(), since install_stdout() (below,
# called by main.py right after this module is imported) wraps print()
# output in an "info" command envelope that a RESYNC prober wouldn't
# recognize as the identification line it's looking for; the plain print()
# here runs before that reassignment happens, so it still reaches the real
# console.
_banner = "VENTILASTATION %s %s %s" % (version.NAME, version.VERSION, version.GIT_HASH)
uart.write(_banner + "\n")
print(_banner)

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

def next_resync():
    _drain()
    if _parser.pop_resync():
        return True
    return _console_scanner.poll_pending()

def next_joy2():
    return _parser.joy2

def next_extra():
    return _parser.extra

def send(line, data=b""):
    uart.write(line)
    uart.write("\n")
    if data:
        uart.write(data)


def install_stdout():
    """Send hardware Python ``print`` output to the desktop host over UART."""
    sys.stdout = InfoWriter(send)
