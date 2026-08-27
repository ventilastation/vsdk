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
# `povperf gate stop` formats one reply through the UART bridge.  On the
# ESP32 MicroPython runtime that transient command/report frame accounts for
# a stable 64-80 bytes after collection; larger retained growth is scene
# work and remains a failure.
HEAP_REPORT_ALLOWANCE = 128


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
    if by_mode["per_sprite"]["avg_us"] <= inline * 1.03:
        failures.append("per-sprite dispatch was not measurably slower than inline")
    return failures


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--port", help="workbench serial port (default: registered board)")
    parser.add_argument("--baud", type=int, default=115200)
    parser.add_argument("--rpms", type=int, nargs="+", default=(600, 700))
    parser.add_argument("--duration", type=float, default=5.0)
    parser.add_argument("--settle", type=float, default=1.0)
    parser.add_argument("--json-out", type=Path)
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
