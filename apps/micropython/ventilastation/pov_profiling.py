"""Control-plane support for the opt-in rotor render profiler.

The timers live in the C GPU task so they include actual DMA overlap. This
module only turns collection on/off and formats a stable, line-oriented report
for the existing board control stream.
"""

import gc

_heap_start_free = -1


def _heap_free():
    try:
        return gc.mem_free()
    except AttributeError:
        return -1


def _send_stats(send, display):
    # Sample the heap before get_performance_stats() allocates its transient
    # result dict. The start baseline is taken at the same point, so a stable
    # scene reports zero instead of a repeatable ~192-byte instrumentation
    # bias caused by measuring while that dict was still live.
    heap_free = _heap_free()
    stats = display.get_performance_stats()
    samples = stats.get("samples", 0)
    frames = stats.get("frames", 0)
    projection_complete = frames if stats.get("vs2", 0) else 1
    # ``complete`` means the report contains a usable physical and projection
    # sample window. Quality gates (skips and deadline misses) stay as numeric
    # fields so callers can apply hardware-appropriate regression ceilings.
    complete = int(bool(samples) and bool(projection_complete))
    heap_delta = heap_free - _heap_start_free if heap_free >= 0 and _heap_start_free >= 0 else -1
    send(("povperf_state enabled=%d encoder=%s scene=%s layers=%d sprites=%d "
          "tilemaps=%d complete=%d heap_start=%d heap_free=%d heap_delta=%d" % (
              stats.get("enabled", 0),
              "calibrated" if stats.get("calibrated", 0) else "legacy",
              "vs2" if stats.get("vs2", 0) else "sprites",
              stats.get("layers", 0), stats.get("sprites", 0),
              stats.get("tilemaps", 0), complete, _heap_start_free,
              heap_free, heap_delta)).encode())
    send(("povperf_timing samples=%d deadline_us=%d skipped=%d overruns=%d "
          "avg_total_us=%d max_total_us=%d avg_render_us=%d max_render_us=%d "
          "max_arm_render_us=%d avg_spi_wait_us=%d max_spi_wait_us=%d "
          "avg_copy_us=%d max_copy_us=%d worst_slack_us=%d "
          "project_samples=%d frames=%d frame_deadline_us=%d frame_overruns=%d "
          "avg_project_us=%d max_project_us=%d avg_frame_render_us=%d "
          "max_frame_render_us=%d" % (
              samples, stats.get("deadline_us", 0), stats.get("skipped_updates", 0),
              stats.get("deadline_misses", 0), stats.get("avg_total_us", 0),
              stats.get("max_total_us", 0), stats.get("avg_render_us", 0),
              stats.get("max_render_us", 0), stats.get("max_arm_render_us", 0),
              stats.get("avg_spi_wait_us", 0), stats.get("max_spi_wait_us", 0),
              stats.get("avg_copy_us", 0), stats.get("max_copy_us", 0),
              stats.get("worst_slack_us", 0), stats.get("project_samples", 0),
              frames, stats.get("frame_deadline_us", 0),
              stats.get("frame_deadline_misses", 0),
              stats.get("avg_project_us", stats.get("avg_render_us", 0)),
              stats.get("max_project_us", stats.get("max_render_us", 0)),
              stats.get("avg_frame_render_us", 0),
              stats.get("max_frame_render_us", 0))).encode())


def _unsupported(send):
    send(b"povperf_error unsupported")


def handle_command(parts, send, display, scene=None):
    """Handle ``povperf`` without persisting or otherwise changing a profile.

    Commands are ``status``, ``start``, ``stop``, ``reset``,
    ``mode legacy|calibrated``, and ``capture``. Selecting an encoder resets
    the sample window so a report never silently combines the two
    implementations. ``capture`` asks an opt-in fixture to restore and freeze
    its deterministic oracle frame.
    """
    get_stats = getattr(display, "get_performance_stats", None)
    set_enabled = getattr(display, "set_performance_profiling", None)
    reset = getattr(display, "reset_performance_stats", None)
    if get_stats is None or set_enabled is None or reset is None:
        _unsupported(send)
        return

    global _heap_start_free
    command = parts[0] if parts else "status"
    try:
        if command == "status":
            pass
        elif command == "start":
            reset()
            set_enabled(True)
            # Warm the reporting path before taking the retained-heap
            # baseline. Its first formatting/send pass leaves a small,
            # one-time runtime allocation; that is profiler setup, not
            # per-frame scene growth.
            _send_stats(send, display)
            gc.collect()
            _heap_start_free = _heap_free()
            return
        elif command == "stop":
            set_enabled(False)
            gc.collect()
        elif command == "reset":
            reset()
        elif command == "capture":
            prepare_capture = getattr(scene, "prepare_capture", None)
            if prepare_capture is None:
                raise ValueError("scene does not support deterministic capture")
            prepare_capture()
            send(b"povperf_capture ready=1")
            return
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
