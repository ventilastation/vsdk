"""Control-plane support for the POV hall-pulse filter diagnostic toggle.

Lets the connected board's gated hall-pulse filter (hardware/rotor/modules/
povdisplay/hall_filter.c) be A/B compared live against the pre-filter raw
passthrough, without reflashing -- see the emulator's F5 key
(comms.toggle_hall_filter()).
"""


def _send_state(send, display):
    get_enabled = getattr(display, "get_hall_filter_enabled", None)
    get_stats = getattr(display, "get_performance_stats", None)
    enabled = bool(get_enabled()) if get_enabled else False
    stats = get_stats() if get_stats else {}
    send(("hallfilter_state enabled=%d period_us=%d jitter_us=%d "
          "accepted=%d spurious=%d missed=%d missed_pulses=%d outlier=%d stall=%d resync=%d" % (
              enabled,
              stats.get("diag_hall_period_us", 0), stats.get("diag_hall_jitter_us", 0),
              stats.get("diag_hall_accepted", 0), stats.get("diag_hall_spurious", 0),
              stats.get("diag_hall_missed", 0), stats.get("diag_hall_missed_pulses", 0),
              stats.get("diag_hall_outlier", 0), stats.get("diag_hall_stall", 0),
              stats.get("diag_hall_resync", 0))).encode())


def _unsupported(send):
    send(b"hallfilter_error unsupported")


def handle_command(parts, send, display):
    """Handle ``hallfilter``. Commands are ``status``, ``on``, ``off``, ``toggle``."""
    set_enabled = getattr(display, "set_hall_filter_enabled", None)
    get_enabled = getattr(display, "get_hall_filter_enabled", None)
    if set_enabled is None or get_enabled is None:
        _unsupported(send)
        return

    command = parts[0] if parts else "status"
    try:
        if command == "status":
            pass
        elif command == "on":
            set_enabled(True)
        elif command == "off":
            set_enabled(False)
        elif command == "toggle":
            set_enabled(not get_enabled())
        else:
            raise ValueError("invalid command")
    except (AttributeError, RuntimeError, ValueError):
        send(b"hallfilter_error invalid_command")
        return
    _send_state(send, display)
