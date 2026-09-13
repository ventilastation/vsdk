#!/usr/bin/env python3
"""Run the VS2 Actions/Behaviors pre-gate on the USB workbench and rotor.

The fixture intentionally measures only the proposed dispatch shapes; it does
not require, or accidentally become, a partial Behaviors implementation.
"""

import argparse
import json
import sys
import time
from pathlib import Path

VSDK_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(VSDK_ROOT / "tools"))

import pov_profile_report as profile  # noqa: E402


MODES = ("inline", "column", "per_sprite", "hybrid")
# T0's two new experiments (docs/vs2-behaviors-implementation.md, "Gate:
# prove the numbers on hardware first"). 90 matches the gate scene's own
# ``behavior_slots`` (SPRITE_COUNT + MULTI_BEHAVIOR_SPRITES); enough passes
# to get a stable microsecond average out of esp_timer_get_time()'s
# resolution without the probe call itself taking long enough to matter.
FLATPROBE_COUNT = 90
FLATPROBE_PASSES = 20000
# `povperf gate stop` formats one reply through the UART bridge.  On the
# ESP32 MicroPython runtime that transient command/report frame accounts for
# a stable 64-160 bytes after collection; larger retained growth is scene
# work and remains a failure.
HEAP_REPORT_ALLOWANCE = 192


def _field(events, prefix):
    value = None
    for kind, text in events:
        if kind == "line":
            # The workbench can finish forwarding a buffered launcher/status
            # preamble immediately before its next line.  Keep the gate
            # result even when that harmless preamble is coalesced with it.
            offset = text.find(prefix)
            if offset >= 0:
                value = profile.parse_kv_line(text[offset:], prefix) or value
    return value


def _integer(fields, name, default=0):
    return profile.to_int(fields or {}, name, default)


def _run_mode(ser, reader, mode, duration):
    profile.send_line(ser, "povperf start")
    reader.read_for(0.25)
    profile.send_line(ser, "povperf gate start " + mode)
    reader.read_for(0.25)
    # Establish the heap baseline after the scene has taken a few real
    # updates, excluding one-time VM/property-cache setup.
    profile.send_line(ser, "povperf gate baseline")
    reader.read_for(0.25)
    time.sleep(duration)
    profile.send_line(ser, "povperf gate stop")
    events = reader.read_for(1.0)
    gate = _field(events, "povperf_gate ")
    profile.send_line(ser, "povperf stop")
    events += reader.read_for(1.0)
    state = _field(events, "povperf_state ")
    timing = _field(events, "povperf_timing ")
    return gate, state, timing


def _run_gpu_idle_row(ser, reader, mode, duration):
    """Same dispatch-mode measurement as ``_run_mode``, with the GPU task's
    own column-serve/render work skipped for the duration. Isolates whether
    the gate's avg_us reflects real CPU cost or cross-core contention with
    that work -- see povdisplay.c's ``gpu_idle_enabled``. The renderer-side
    ``state``/``timing`` fields are meaningless here (nothing calls into
    performance_record_project()/_serve() while idle), so only the gate's
    own avg_us/max_us/samples are meaningful and returned.
    """
    profile.send_line(ser, "povperf gpuidle on")
    reader.read_for(0.2)
    gate, _state, _timing = _run_mode(ser, reader, mode, duration)
    profile.send_line(ser, "povperf gpuidle off")
    reader.read_for(0.2)
    return {
        "mode": mode,
        "avg_us": _integer(gate, "avg_us"),
        "max_us": _integer(gate, "max_us"),
        "samples": _integer(gate, "samples"),
    }


def _run_flattened_probe(ser, reader, count=FLATPROBE_COUNT, passes=FLATPROBE_PASSES):
    """T0's "flattened-record probe": a throwaway native loop over a static
    array shaped like the eventual flattened pool layout, timed while
    whatever scene is currently active keeps rendering -- see
    vs2_native.c's ``flattened_probe()``. Independent of the gate scene's
    own dispatch modes; run once per RPM so cross-core contention with the
    GPU task's own render/DMA work at that RPM is captured too.
    """
    profile.send_line(ser, "povperf flatprobe %d %d" % (count, passes))
    events = reader.read_for(2.0)
    fields = _field(events, "povperf_flatprobe ") or {}
    return {
        "count": count,
        "passes": passes,
        "avg_us": _integer(fields, "avg_us"),
    }


def _failures(rows):
    failures = []
    by_mode = {row["mode"]: row for row in rows}
    if set(by_mode) != set(MODES):
        return ["missing gate result"]
    for mode, row in by_mode.items():
        if row["samples"] < 100:
            failures.append("%s has fewer than 100 samples" % mode)
        if row["heap_delta"] < -HEAP_REPORT_ALLOWANCE:
            failures.append("%s retained %d bytes" % (mode, -row["heap_delta"]))
        if row["overruns"] or row["frame_overruns"] or row["worst_slack_us"] < 0:
            failures.append("%s disturbed renderer timing" % mode)
    inline = by_mode["inline"]["avg_us"]
    if inline <= 0:
        return failures + ["inline benchmark has no timing"]
    if by_mode["column"]["avg_us"] > inline * 1.10:
        failures.append("column Action exceeds inline by more than 10%%")
    if by_mode["hybrid"]["avg_us"] > inline * 1.25:
        failures.append("hybrid dispatch exceeds inline by more than 25%%")
    if by_mode["per_sprite"]["avg_us"] <= by_mode["column"]["avg_us"] * 1.03:
        failures.append("per-sprite dispatch was not measurably slower than column")
    return failures


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--port", help="workbench serial port (default: registered board)")
    parser.add_argument("--baud", type=int, default=115200)
    parser.add_argument("--rpms", type=int, nargs="+", default=(600, 700))
    parser.add_argument("--duration", type=float, default=5.0)
    parser.add_argument("--settle", type=float, default=1.0)
    parser.add_argument("--json-out", type=Path)
    parser.add_argument(
        "--t0-experiments", action="store_true", default=True,
        help="also run T0's GPU-idle comparison and flattened-record probe (default: on)",
    )
    parser.add_argument(
        "--no-t0-experiments", action="store_false", dest="t0_experiments",
        help="skip T0's two new experiments, running only the original ratio gate",
    )
    args = parser.parse_args()

    import serial

    port = args.port or profile.find_workbench_port()
    results = {"port": port, "rpms": args.rpms, "duration": args.duration, "runs": []}
    ser = serial.Serial(port, args.baud, timeout=0.1)
    reader = profile.WireReader(ser)
    try:
        profile.return_to_menu(ser, reader, came_from_native=True, banner_timeout=3)
        for rpm in args.rpms:
            print("\nGate at %d RPM" % rpm)
            profile.set_workbench_rpm_usb(ser, reader, rpm)
            time.sleep(args.settle)
            profile.send_line(ser, "launch vs2_behavior_gate")
            time.sleep(args.settle)
            rpm_rows = []
            for mode in MODES:
                gate, state, timing = _run_mode(ser, reader, mode, args.duration)
                row = {
                    "mode": mode,
                    "avg_us": _integer(gate, "avg_us"),
                    "max_us": _integer(gate, "max_us"),
                    "samples": _integer(gate, "samples"),
                    "heap_delta": _integer(gate, "heap_delta", -1),
                    "overruns": _integer(timing, "overruns"),
                    "frame_overruns": _integer(timing, "frame_overruns"),
                    "worst_slack_us": _integer(timing, "worst_slack_us", -1),
                    "renderer_heap_delta": _integer(state, "heap_delta", -1),
                }
                rpm_rows.append(row)
                print("  %-11s avg=%4dus max=%4dus samples=%d heap=%d" % (
                    mode, row["avg_us"], row["max_us"], row["samples"], row["heap_delta"]
                ))
            run = {"rpm": rpm, "rows": rpm_rows}
            run["failures"] = _failures(rpm_rows)
            if args.t0_experiments:
                print("  GPU-idle comparison:")
                gpu_idle_rows = []
                for mode in MODES:
                    row = _run_gpu_idle_row(ser, reader, mode, args.duration)
                    gpu_idle_rows.append(row)
                    print("    %-11s avg=%4dus max=%4dus samples=%d" % (
                        mode, row["avg_us"], row["max_us"], row["samples"]
                    ))
                run["gpu_idle_rows"] = gpu_idle_rows
                probe = _run_flattened_probe(ser, reader)
                run["flattened_probe"] = probe
                print("  Flattened-record probe: count=%d passes=%d avg_us=%d" % (
                    probe["count"], probe["passes"], probe["avg_us"]
                ))
            results["runs"].append(run)
            for failure in run["failures"]:
                print("  FAIL: " + failure, file=sys.stderr)
        profile.return_to_menu(ser, reader, came_from_native=False)
    finally:
        ser.close()

    results["failures"] = [
        "%d RPM: %s" % (run["rpm"], failure)
        for run in results["runs"] for failure in run["failures"]
    ]
    if args.json_out:
        args.json_out.parent.mkdir(parents=True, exist_ok=True)
        args.json_out.write_text(json.dumps(results, indent=2) + "\n")
        print("Saved", args.json_out)
    return 1 if results["failures"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
