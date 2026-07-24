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
    send(("povperf_diag fb_bytes_requested=%d internal_free_before=%d "
          "internal_largest_before=%d internal_free_after=%d "
          "fb_a_addr=%d fb_b_addr=%d fb_a_size=%d fb_b_size=%d "
          "canary_checks=%d canary_corrupt_words=%d canary_first_bad_region=%d "
          "canary_first_bad_offset=%d canary_first_bad_value=%d" % (
              stats.get("diag_fb_bytes_requested", 0),
              stats.get("diag_internal_free_before", 0),
              stats.get("diag_internal_largest_before", 0),
              stats.get("diag_internal_free_after", 0),
              stats.get("diag_fb_a_addr", 0), stats.get("diag_fb_b_addr", 0),
              stats.get("diag_fb_a_size", 0), stats.get("diag_fb_b_size", 0),
              stats.get("diag_canary_checks", 0),
              stats.get("diag_canary_corrupt_words", 0),
              stats.get("diag_canary_first_bad_region", 0),
              stats.get("diag_canary_first_bad_offset", 0),
              stats.get("diag_canary_first_bad_value", 0))).encode())
    send(("povperf_pattern serve_checks=%d mismatch_count=%d "
          "arm0_count=%d arm1_count=%d front_a_count=%d front_b_count=%d "
          "num_pixels_g=%d "
          "first_column=%d first_led=%d first_arm=%d "
          "first_expected=%d first_actual=%d "
          "last_column=%d last_led=%d last_arm=%d "
          "last_expected=%d last_actual=%d" % (
              stats.get("diag_serve_checks", 0), stats.get("diag_mismatch_count", 0),
              stats.get("diag_mismatch_arm0_count", 0),
              stats.get("diag_mismatch_arm1_count", 0),
              stats.get("diag_mismatch_front_a_count", 0),
              stats.get("diag_mismatch_front_b_count", 0),
              stats.get("diag_num_pixels_g", 0),
              stats.get("diag_mismatch_first_column", 0),
              stats.get("diag_mismatch_first_led", 0),
              stats.get("diag_mismatch_first_arm", 0),
              stats.get("diag_mismatch_first_expected", 0),
              stats.get("diag_mismatch_first_actual", 0),
              stats.get("diag_mismatch_last_column", 0),
              stats.get("diag_mismatch_last_led", 0),
              stats.get("diag_mismatch_last_arm", 0),
              stats.get("diag_mismatch_last_expected", 0),
              stats.get("diag_mismatch_last_actual", 0))).encode())


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
        elif command == "testpattern" and len(parts) == 2:
            setter = getattr(display, "set_diag_test_pattern", None)
            if setter is None:
                _unsupported(send)
                return
            if parts[1] == "on":
                setter(True)
            elif parts[1] == "off":
                setter(False)
            else:
                raise ValueError("unknown testpattern state")
        else:
            raise ValueError("invalid command")
    except (AttributeError, RuntimeError, ValueError):
        send(b"povperf_error invalid_command")
        return
    _send_stats(send, display)
