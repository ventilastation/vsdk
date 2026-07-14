"""Minimal UART status reporting for the factory/recovery environment.

Recovery runs with vfs potentially completely empty, so it can't depend on
the vfs-resident `ventilastation` package (see vsdk_recovery.py's docstring)
-- including apps/micropython/ventilastation/serialcomms.py, the normal
in-place-OTA path's UART link to the base station. This reimplements just
enough of the same wire protocol (serialcomms.send() plus the `info <len>`
framing from ventilastation/uart_logging.py's InfoWriter) directly against
vs_board's NVS wiring, so recovery's status is visible on the same UART
link a real base station reads, and the desktop emulator's comms.py parses
identically. Frozen at the top level alongside boot.py/vsdk_recovery.py/
updater.py/vsdk_logo_strip.py for the same reason those are.
"""

_uart = None


def _get_uart():
    global _uart
    if _uart is not None:
        return _uart
    try:
        import esp32
        import machine

        nvs = esp32.NVS("vs_board")
        _uart = machine.UART(
            nvs.get_i32("serial_uart"),
            tx=nvs.get_i32("serial_tx"),
            rx=nvs.get_i32("serial_rx"),
            baudrate=nvs.get_i32("serial_baud"),
        )
    except Exception:
        _uart = False  # board not provisioned yet, or no UART -- give up quietly
    return _uart


def send(line, data=b""):
    """Write one raw protocol line (e.g. an `ota_progress ...` line
    forwarded verbatim) -- matches ventilastation/serialcomms.py's send()."""
    uart = _get_uart()
    if not uart:
        return
    try:
        uart.write(line)
        uart.write("\n")
        if data:
            uart.write(data)
    except Exception:
        pass


def info(text):
    """Write a free-form status line as an `info` frame, the same framing
    ventilastation/uart_logging.py's InfoWriter gives to hardware stdout."""
    if not isinstance(text, str):
        text = str(text)
    data = text.encode("utf-8")
    send(b"info %d" % len(data), data)
