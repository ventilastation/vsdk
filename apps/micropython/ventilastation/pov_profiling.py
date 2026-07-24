"""Control-plane support for the opt-in rotor render profiler.

The timers live in the C GPU task so they include actual DMA overlap. This
module only turns collection on/off and formats a stable, line-oriented report
for the existing board control stream.
"""


def _send_stats(send, display):
    stats = display.get_performance_stats()
    samples = stats.get("samples", 0)
    complete = int(bool(samples) and not stats.get("skipped_updates", 0)
                   and not stats.get("deadline_misses", 0))
    send(("povperf_state enabled=%d encoder=%s scene=%s layers=%d sprites=%d "
          "tilemaps=%d complete=%d" % (
              stats.get("enabled", 0),
              "calibrated" if stats.get("calibrated", 0) else "legacy",
              "vs2" if stats.get("vs2", 0) else "sprites",
              stats.get("layers", 0), stats.get("sprites", 0),
              stats.get("tilemaps", 0), complete)).encode())
    send(("povperf_timing samples=%d deadline_us=%d skipped=%d overruns=%d "
          "avg_total_us=%d max_total_us=%d avg_render_us=%d max_render_us=%d "
          "max_arm_render_us=%d avg_spi_wait_us=%d max_spi_wait_us=%d "
          "avg_copy_us=%d max_copy_us=%d worst_slack_us=%d "
          "diag_hall_revolutions=%d diag_publish_count=%d" % (
              samples, stats.get("deadline_us", 0), stats.get("skipped_updates", 0),
              stats.get("deadline_misses", 0), stats.get("avg_total_us", 0),
              stats.get("max_total_us", 0), stats.get("avg_render_us", 0),
              stats.get("max_render_us", 0), stats.get("max_arm_render_us", 0),
              stats.get("avg_spi_wait_us", 0), stats.get("max_spi_wait_us", 0),
              stats.get("avg_copy_us", 0), stats.get("max_copy_us", 0),
              stats.get("worst_slack_us", 0), stats.get("diag_hall_revolutions", 0),
              stats.get("diag_publish_count", 0))).encode())


def _unsupported(send):
    send(b"povperf_error unsupported")


def handle_command(parts, send, display):
    """Handle ``povperf`` without persisting or otherwise changing a profile.

    Commands are ``status``, ``start``, ``stop``, ``reset``, and
    ``mode legacy|calibrated``. Selecting an encoder resets the sample window
    so a report never silently combines the two implementations.
    """
    get_stats = getattr(display, "get_performance_stats", None)
    set_enabled = getattr(display, "set_performance_profiling", None)
    reset = getattr(display, "reset_performance_stats", None)
    if get_stats is None or set_enabled is None or reset is None:
        _unsupported(send)
        return

    command = parts[0] if parts else "status"
    try:
        if command == "status":
            pass
        elif command == "start":
            reset()
            set_enabled(True)
        elif command == "stop":
            set_enabled(False)
        elif command == "reset":
            reset()
        elif command == "mode" and len(parts) == 2:
            selector = getattr(display, "set_color_pipeline_enabled", None)
            if selector is None:
                _unsupported(send)
                return
            if parts[1] == "legacy":
                selector(False)
            elif parts[1] == "calibrated":
                selector(True)
            else:
                raise ValueError("unknown encoder")
            reset()
        else:
            raise ValueError("invalid command")
    except (AttributeError, RuntimeError, ValueError):
        send(b"povperf_error invalid_command")
        return
    _send_stats(send, display)
