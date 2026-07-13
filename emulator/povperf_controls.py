"""Command sequencing for the desktop POV render-profiler controls."""


def start_capture(encoder, send_command):
    """Select ``encoder`` and start a fresh on-device timing capture."""
    if encoder not in ("legacy", "calibrated"):
        raise ValueError("unknown POV performance encoder: %s" % encoder)
    send_command("povperf mode " + encoder)
    send_command("povperf start")


def stop_capture(send_command):
    """End a capture; the board returns its final report to the console."""
    send_command("povperf stop")
