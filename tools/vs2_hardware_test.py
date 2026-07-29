#!/usr/bin/env python3
"""Run repeatable VS2 acceptance checks on the USB-attached rotor/workbench.

The workbench supplies hall pulses and captures the physical APA102 bus. The
rotor's own profiler supplies service and complete-frame projection timings.
Rendering is compared byte-for-byte with the same C renderer and factory
colour pipeline built for the host.
"""

import argparse
import os
import random
import subprocess
import sys
import time
from pathlib import Path

import numpy as np

VSDK_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(VSDK_ROOT / "tools"))

import pov_profile_report as profile  # noqa: E402
import vs2_hardware_report as report  # noqa: E402

FRAME_COLUMNS = 256
FRAME_LEDS = 54
APA102_BYTES = 4
FRAME_BYTES = FRAME_COLUMNS * FRAME_LEDS * APA102_BYTES

PERFORMANCE_SCENES = (
    {
        "label": "vs2max",
        "slug": "vs2_hardware",
        "layers": 8,
        "sprites": 100,
        "tilemaps": 16,
    },
    {
        "label": "povstress",
        "slug": "demos.povstress",
        "layers": 8,
        "sprites": 60,
        "tilemaps": 2,
    },
)


def best_circular_match(captured, expected):
    """Return exact-pixel metrics for the best angular alignment.

    The stored rotor column offset is intentionally not mutated by this test,
    so all 256 circular shifts are considered. LED zero is excluded because
    it is physically shared by the two opposed arms and the last DMA write
    wins there; all other 53 LEDs have a one-to-one oracle value.
    """
    if len(captured) != FRAME_BYTES or len(expected) != FRAME_BYTES:
        raise ValueError("capture/oracle must each contain %d bytes" % FRAME_BYTES)
    captured_array = np.frombuffer(captured, dtype=np.uint8).reshape(
        FRAME_COLUMNS, FRAME_LEDS, APA102_BYTES
    )
    expected_array = np.frombuffer(expected, dtype=np.uint8).reshape(
        FRAME_COLUMNS, FRAME_LEDS, APA102_BYTES
    )
    best = None
    for shift in range(FRAME_COLUMNS):
        aligned = np.roll(expected_array, shift, axis=0)
        exact = np.all(captured_array[:, 1:, :] == aligned[:, 1:, :], axis=2)
        active = np.any(aligned[:, 1:, 1:] != 0, axis=2)
        exact_ratio = float(np.mean(exact))
        active_ratio = float(np.mean(exact[active])) if np.any(active) else exact_ratio
        candidate = {
            "shift": shift,
            "exact_ratio": exact_ratio,
            "active_exact_ratio": active_ratio,
            "different_pixels": int(exact.size - np.count_nonzero(exact)),
            "compared_pixels": int(exact.size),
            "active_pixels": int(np.count_nonzero(active)),
        }
        if best is None or (
            candidate["active_exact_ratio"],
            candidate["exact_ratio"],
        ) > (
            best["active_exact_ratio"],
            best["exact_ratio"],
        ):
            best = candidate
    return best


def performance_failures(row, expected_counts, max_skip_pct=0.05):
    failures = []
    if not row.get("ok"):
        return ["no povperf response"]
    for key in ("layers", "sprites", "tilemaps"):
        if row.get(key) != expected_counts[key]:
            failures.append(
                "%s=%s, expected %s"
                % (key, row.get(key), expected_counts[key])
            )
    if row.get("samples", 0) <= 0:
        failures.append("no physical-column samples")
    if row.get("frames", 0) <= 0:
        failures.append("no complete 256-column render samples")
    if row.get("skip_pct", 0.0) > max_skip_pct:
        failures.append(
            "%.6f%% skipped physical columns exceeds %.6f%%"
            % (row["skip_pct"], max_skip_pct)
        )
    if row.get("overruns", 0):
        failures.append("%d physical-column deadline misses" % row["overruns"])
    if row.get("frame_overruns", 0):
        failures.append("%d full-frame deadline misses" % row["frame_overruns"])
    if row.get("worst_slack_us", -1) < 0:
        failures.append("negative physical-column slack")
    frame_deadline = row.get("frame_deadline_us", 0)
    max_frame = row.get("max_frame_render_us", 0)
    if frame_deadline <= 0:
        failures.append("no full-frame deadline")
    elif max_frame > frame_deadline:
        failures.append(
            "max frame render %dus exceeds %dus revolution budget"
            % (max_frame, frame_deadline)
        )
    if row.get("heap_delta", -1) < 0:
        failures.append(
            "retained MicroPython heap growth (%d free bytes)"
            % row.get("heap_delta", -1)
        )
    return failures


def _install_host_runtime_stubs():
    sys.modules.setdefault("uos", os)
    sys.modules.setdefault("urandom", random)
    if "utime" not in sys.modules:
        class Utime:
            @staticmethod
            def ticks_ms():
                return int(time.time() * 1000)

            @staticmethod
            def ticks_add(value, delta):
                return value + delta

            @staticmethod
            def ticks_diff(end, start):
                return end - start

            @staticmethod
            def sleep_ms(ms):
                time.sleep(ms / 1000.0)

        sys.modules["utime"] = Utime


def build_expected_frame():
    """Build the hardware C oracle for the static maximum-budget fixture."""
    subprocess.run(
        [str(VSDK_ROOT / "emulator/native/build.sh")],
        cwd=VSDK_ROOT,
        check=True,
    )
    _install_host_runtime_stubs()
    sys.path.insert(0, str(VSDK_ROOT / "emulator"))
    sys.path.insert(0, str(VSDK_ROOT / "apps/micropython"))
    sys.path.insert(0, str(VSDK_ROOT))

    import native_render
    import povrender
    import vs2
    from ventilastation import api_guard
    from ventilastation.app_loader import load_app
    from ventilastation.color_calibration import build_default
    from ventilastation.director import configure_runtime, reset_runtime

    if not native_render.available:
        raise RuntimeError("native C renderer was not built")

    reset_runtime()
    api_guard.reset()
    runtime_director = configure_runtime("headless")
    original_load_rom = runtime_director.load_rom

    def load_repo_rom(filename):
        return original_load_rom(str(VSDK_ROOT / "apps/micropython" / filename))

    runtime_director.load_rom = load_repo_rom
    try:
        scene = load_app("vs2_hardware")
        povrender.set_palettes(runtime_director.palette_data)
        for slot, strip in runtime_director._stripe_buffers.items():
            povrender.set_image_strip(slot, strip)
        payload = vs2.export_scene_payload(scene)
        povrender.set_vs2_scene(payload)
        native_render.set_starfield(False)
        if not native_render.set_color_profile(build_default()):
            raise RuntimeError("native C renderer rejected the factory colour profile")
        rendered = native_render.render_frame_apa102()
        if rendered is None:
            raise RuntimeError("native C renderer returned no frame")
        return rendered.astype("<u4", copy=False).tobytes()
    finally:
        reset_runtime()
        api_guard.reset()


def _state_value(state, key, default=0):
    return profile.to_int(state or {}, key, default)


def make_performance_row(rpm, repetition, scene, state, timing):
    row = profile.build_report_row(
        rpm, scene["label"], scene["slug"], state, timing
    )
    row["repetition"] = repetition
    if row.get("ok"):
        row.update(
            {
                "complete": _state_value(state, "complete"),
                "layers": _state_value(state, "layers"),
                "sprites": _state_value(state, "sprites"),
                "tilemaps": _state_value(state, "tilemaps"),
            }
        )
    return row


def wait_for_calibration_state(ser, reader, command, timeout=3.0):
    profile.send_line(ser, command)
    payload = reader.wait_for_event("povcal_state", timeout)
    if payload is None:
        raise RuntimeError("%s returned no calibration state" % command)
    return payload


def prepare_deterministic_capture(ser, reader, timeout=3.0):
    profile.send_line(ser, "povperf capture")
    if not reader.wait_for("povperf_capture ready=1", timeout):
        raise RuntimeError("scene did not acknowledge deterministic capture")


def ensure_scene_ready(
        ser, reader, scene, settle, status_timeout=1.0, launch_attempts=2):
    """Confirm the requested VS2 graph is live before opening a sample window.

    The workbench bridge and rotor share one serial stream. A delayed ``exit``
    from the preceding screenshot can therefore overtake the next launch in a
    sufficiently busy run. Treat the renderer census as the launch
    acknowledgement and retry once instead of silently profiling the launcher.
    """
    expected = {
        key: int(scene[key])
        for key in ("layers", "sprites", "tilemaps")
    }
    last_state = None
    for attempt in range(launch_attempts):
        # Discard any completed start/stop response from the preceding run so
        # only the status requested below can satisfy this handshake.
        reader.read_for(0.1)
        profile.send_line(ser, "povperf status")
        events = reader.read_for(status_timeout)
        for kind, text in events:
            if kind == "line":
                last_state = (
                    profile.parse_kv_line(text, "povperf_state ")
                    or last_state
                )
        if last_state is not None and all(
                profile.to_int(last_state, key, -1) == value
                for key, value in expected.items()):
            return last_state
        if attempt + 1 < launch_attempts:
            profile.send_line(ser, "launch " + scene["slug"])
            profile.wiggle(ser)
            time.sleep(settle)

    actual = {
        key: profile.to_int(last_state or {}, key, -1)
        for key in expected
    }
    raise RuntimeError(
        "%s did not become ready: expected %s, got %s"
        % (scene["label"], expected, actual)
    )


def git_metadata():
    def git_output(*args):
        result = subprocess.run(
            ["git", *args],
            cwd=VSDK_ROOT,
            capture_output=True,
            text=True,
        )
        return result.stdout.strip() if result.returncode == 0 else "unknown"

    return {
        "branch": git_output("branch", "--show-current"),
        "commit": git_output("rev-parse", "HEAD"),
        "dirty": bool(git_output("status", "--porcelain")),
    }


def run_hardware(args):
    import serial

    started = report.timestamp_now()
    report_dir = report.create_run_directory(
        args.report_root, args.report_name, now=started
    ).resolve()
    results = {
        "started_at": started.isoformat(timespec="seconds"),
        "finished_at": None,
        "status": "running",
        "report_directory": str(report_dir),
        "port": args.port or "auto",
        "rpms": args.rpms,
        "repeats": args.repeats,
        "max_skip_pct": args.max_skip_pct,
        "config": {
            "baud": args.baud,
            "settle": args.settle,
            "duration": args.duration,
            "render_rpm": args.render_rpm,
            "capture_warmups": args.capture_warmups,
            "capture_repeats": args.capture_repeats,
            "capture_settle": args.capture_settle,
            "capture_timeout": args.capture_timeout,
            "min_exact": args.min_exact,
            "min_active_exact": args.min_active_exact,
            "skip_performance": args.skip_performance,
            "skip_render": args.skip_render,
        },
        "git": git_metadata(),
        "performance": [],
        "render_warmups": [],
        "rendering": [],
        "failures": [],
    }
    print("Report directory:", report_dir)

    ser = None
    expected_frame = None
    reader = None
    calibration_changed = False
    try:
        if not args.skip_render:
            print("Building native C rendering oracle...")
            expected_frame = build_expected_frame()
            if len(expected_frame) != FRAME_BYTES:
                raise RuntimeError("native oracle returned the wrong frame size")
            oracle_rel = "screenshots/render-oracle.png"
            report.save_frame_screenshot(
                expected_frame, report_dir / oracle_rel
            )
            results["oracle_screenshot"] = oracle_rel

        port = args.port or profile.find_workbench_port()
        results["port"] = port
        print("Using workbench/rotor bridge:", port)
        ser = serial.Serial(port, args.baud, timeout=0.1)
        reader = profile.WireReader(ser)
        profile.return_to_menu(
            ser, reader, came_from_native=True, banner_timeout=3
        )

        if not args.skip_performance:
            for rpm in args.rpms:
                print("\nPerformance at %d RPM" % rpm)
                profile.set_workbench_rpm_usb(ser, reader, rpm)
                time.sleep(1.0)
                for scene in PERFORMANCE_SCENES:
                    for repetition in range(1, args.repeats + 1):
                        print(
                            "  %s repetition %d/%d..."
                            % (scene["label"], repetition, args.repeats)
                        )
                        evidence = {}

                        def capture_performance_evidence():
                            try:
                                captured = profile.capture_workbench_frame(
                                    ser, reader, timeout=args.capture_timeout
                                )
                                screenshot = (
                                    "screenshots/performance-%drpm-%s-r%02d.png"
                                    % (rpm, scene["label"], repetition)
                                )
                                report.save_frame_screenshot(
                                    captured, report_dir / screenshot
                                )
                                evidence["screenshot"] = screenshot
                            except Exception as error:
                                evidence["error"] = str(error)

                        state, timing = profile.profile_run(
                            ser,
                            reader,
                            scene["label"],
                            scene["slug"],
                            False,
                            args.settle,
                            args.duration,
                            keep_awake=False,
                            before_exit=capture_performance_evidence,
                            after_launch=lambda: ensure_scene_ready(
                                ser, reader, scene, args.settle
                            ),
                        )
                        row = make_performance_row(
                            rpm, repetition, scene, state, timing
                        )
                        if evidence.get("screenshot"):
                            row["screenshot"] = evidence["screenshot"]
                        failures = performance_failures(
                            row, scene, max_skip_pct=args.max_skip_pct
                        )
                        if evidence.get("error"):
                            failures.append(
                                "representative screenshot failed: %s"
                                % evidence["error"]
                            )
                        row["failures"] = failures
                        results["performance"].append(row)
                        for failure in failures:
                            results["failures"].append(
                                "%d RPM %s #%d: %s"
                                % (rpm, scene["label"], repetition, failure)
                            )
                        if row.get("ok"):
                            print(
                                "    frames=%d max_frame=%dus slack=%dus heap_delta=%d"
                                % (
                                    row["frames"],
                                    row["max_frame_render_us"],
                                    row["worst_slack_us"],
                                    row["heap_delta"],
                                )
                            )

        if not args.skip_render:
            print("\nPhysical rendering parity")
            profile.set_workbench_rpm_usb(ser, reader, args.render_rpm)
            wait_for_calibration_state(ser, reader, "povcal factory")
            calibration_changed = True
            wait_for_calibration_state(ser, reader, "povcal test off")
            profile.send_line(ser, "launch vs2_hardware")
            time.sleep(args.capture_settle)
            prepare_deterministic_capture(ser, reader)
            # The acknowledgement is sent while the director is processing
            # the control frame. Leave several display loops for the reset
            # state to become the frame captured by the workbench.
            time.sleep(0.15)
            for warmup in range(1, args.capture_warmups + 1):
                captured = profile.capture_workbench_frame(
                    ser, reader, timeout=args.capture_timeout
                )
                metrics = best_circular_match(captured, expected_frame)
                metrics["repetition"] = warmup
                metrics["rpm"] = args.render_rpm
                screenshot = "screenshots/render-warmup-%02d.png" % warmup
                report.save_frame_screenshot(
                    captured, report_dir / screenshot
                )
                metrics["screenshot"] = screenshot
                results["render_warmups"].append(metrics)
                print(
                    "  warm-up %d/%d: shift=%d exact=%.4f%% active=%.4f%%"
                    % (
                        warmup,
                        args.capture_warmups,
                        metrics["shift"],
                        metrics["exact_ratio"] * 100,
                        metrics["active_exact_ratio"] * 100,
                    )
                )
            for repetition in range(1, args.capture_repeats + 1):
                captured = profile.capture_workbench_frame(
                    ser, reader, timeout=args.capture_timeout
                )
                metrics = best_circular_match(captured, expected_frame)
                metrics["repetition"] = repetition
                metrics["rpm"] = args.render_rpm
                screenshot = "screenshots/render-parity-%02d.png" % repetition
                report.save_parity_screenshot(
                    captured,
                    expected_frame,
                    metrics,
                    report_dir / screenshot,
                )
                metrics["screenshot"] = screenshot
                metrics["failures"] = []
                if metrics["exact_ratio"] < args.min_exact:
                    metrics["failures"].append(
                        "exact pixel ratio %.6f below %.6f"
                        % (metrics["exact_ratio"], args.min_exact)
                    )
                if metrics["active_exact_ratio"] < args.min_active_exact:
                    metrics["failures"].append(
                        "active pixel ratio %.6f below %.6f"
                        % (metrics["active_exact_ratio"], args.min_active_exact)
                    )
                results["rendering"].append(metrics)
                for failure in metrics["failures"]:
                    results["failures"].append(
                        "render #%d: %s" % (repetition, failure)
                    )
                print(
                    "  capture %d/%d: shift=%d exact=%.4f%% active=%.4f%%"
                    % (
                        repetition,
                        args.capture_repeats,
                        metrics["shift"],
                        metrics["exact_ratio"] * 100,
                        metrics["active_exact_ratio"] * 100,
                    )
                )
            profile.return_to_menu(ser, reader, came_from_native=False)
    except (Exception, SystemExit) as error:
        failure = "fatal %s: %s" % (type(error).__name__, error)
        results["failures"].append(failure)
        print("\nFAILED:", failure, file=sys.stderr)
    finally:
        if ser is not None and calibration_changed:
            try:
                wait_for_calibration_state(ser, reader, "povcal revert")
            except Exception as error:
                results["failures"].append(
                    "could not restore persisted colour profile: %s" % error
                )
        if ser is not None:
            try:
                profile.set_workbench_rpm_usb(ser, reader, 600)
            except Exception:
                pass
            ser.close()

        results["finished_at"] = report.timestamp_now().isoformat(timespec="seconds")
        results["status"] = "fail" if results["failures"] else "pass"
        html_path, json_path = report.write_report(report_dir, results)
        if args.json_out:
            output = Path(args.json_out)
            output.parent.mkdir(parents=True, exist_ok=True)
            output.write_bytes(json_path.read_bytes())
            print("Additional JSON copy:", output)
        print("\nHTML report:", html_path)
        print("JSON results:", json_path)

    if results["failures"]:
        print("\nFAILED:")
        for failure in results["failures"]:
            print(" -", failure)
        return 1
    print("\nPASS: all VS2 hardware acceptance gates held")
    return 0


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--port", help="workbench USB serial port (auto-detected by default)")
    parser.add_argument("--baud", type=int, default=115200)
    parser.add_argument("--rpms", type=int, nargs="+", default=[600, 700])
    parser.add_argument("--repeats", type=int, default=3)
    parser.add_argument("--settle", type=float, default=2.0)
    parser.add_argument("--duration", type=float, default=5.0)
    # Pixel parity is intentionally isolated from the high-RPM deadline test.
    # At 400 RPM the configured 30 MHz APA102 transaction completes well
    # inside one angular bin, so the workbench can assign the captured row
    # without boundary ambiguity. Performance stays gated at 600/700.
    parser.add_argument("--render-rpm", type=int, default=400)
    parser.add_argument("--capture-warmups", type=int, default=1)
    parser.add_argument("--capture-repeats", type=int, default=3)
    parser.add_argument("--capture-settle", type=float, default=2.0)
    parser.add_argument("--capture-timeout", type=float, default=8.0)
    parser.add_argument(
        "--max-skip-pct",
        type=float,
        default=0.05,
        help="maximum percentage of physical columns that may be skipped",
    )
    parser.add_argument("--min-exact", type=float, default=0.99)
    parser.add_argument("--min-active-exact", type=float, default=0.99)
    parser.add_argument(
        "--report-root",
        default=str(VSDK_ROOT / "build" / "reports" / "vs2-hardware"),
        help="parent directory for timestamped report folders",
    )
    parser.add_argument(
        "--report-name",
        default="vs2-hardware",
        help="name suffix for the timestamped report folder",
    )
    parser.add_argument(
        "--json-out",
        help="optional additional copy of the timestamped folder's results.json",
    )
    parser.add_argument("--skip-performance", action="store_true")
    parser.add_argument("--skip-render", action="store_true")
    args = parser.parse_args()
    if args.repeats < 1 or args.capture_repeats < 1 or args.capture_warmups < 0:
        parser.error("repeat counts must be positive and capture warmups non-negative")
    return run_hardware(args)


if __name__ == "__main__":
    sys.exit(main())
