# VS2 real-hardware acceptance

`tools/vs2_hardware_test.py` is the repeatable acceptance test for the VS2
renderer on a real rotor. It uses the USB-attached workbench board for both
stimulus and observation; working Wi-Fi is not required.

The test has two independent parts:

1. **Performance and stability.** At 600 and 700 RPM it runs both
   `vs2_hardware` (exactly 8 layers, 100 sprites, and 16 tilemaps) and the
   moving `demos.povstress` scene three times. The rotor profiler records
   physical-column service time, complete 256-column projection time, skipped
   columns, both kinds of deadline miss, and collected MicroPython heap before
   and after each window.
2. **Physical rendering parity.** At 400 RPM it selects the factory colour
   profile in RAM, launches the static maximum-budget fixture, and asks the
   workbench for three checksummed 55,296-byte APA102 bus captures. Each
   capture is compared with the same `gpu.c` VS2 compositor and
   `color_pipeline.c` encoder compiled for the host. The lower speed is
   deliberate: a 30 MHz APA102 transfer then completes comfortably inside one
   angular bin, isolating byte-for-byte compositor accuracy from the 600/700
   RPM deadline test above. The first capture after the scene/RPM transition
   is treated as a warm-up; the following three are gated. The comparison
   searches circular column offsets so it does not alter the rotor's saved
   alignment setting. LED zero is excluded because it is physically shared by
   the two opposed arms. Every gated capture must match at least 99% of all
   compared pixels and 99% of active pixels exactly, including the APA102
   brightness byte and all three colour bytes.

The run fails if a fixture no longer fills its expected renderer budget, more
than 0.05% of physical columns are skipped, either deadline is missed,
full-frame rendering exceeds one revolution, collected heap is retained, the
capture CRC fails, or rendering falls below the exact-pixel gates. The small
skip allowance is grounded in repeated 700 RPM measurements of the moving
stress scene; it still rejects the approximately 0.075% pre-scheduler result.
Pass `--max-skip-pct 0` when diagnosing a strict zero-skip target.

## Prepare the boards

Use the `impl/vs2-api-rework` checkout and initialize the MicroPython and
Retro-Go sources as described in [building.md](building.md). Both boards must
already be registered (`make list-boards`) and wired as described in
[workbench.md](workbench.md).

Build and flash only through the repository Makefile:

```sh
source ../../esp-idf/esp-5.5.2/export.sh
make workbench-flash PORT=/dev/cu.usbmodemWORKBENCH
make flash-full PORT=/dev/cu.usbmodemROTOR
```

`flash-full` is required when the filesystem does not already contain
`system/vs2_hardware` and the `other`/`demos.povstress` ROM packs. Board wiring,
Wi-Fi credentials, and the persisted colour profile live in NVS and are not
overwritten.

## Run

The normal acceptance run is:

```sh
make vs2-hardware-test
```

Every invocation creates a collision-safe timestamped directory such as
`build/reports/vs2-hardware/20260728-231251-vs2-hardware/`. The directory
contains `report.html`, `results.json`, and a `screenshots/` directory. The
HTML report embeds a representative physical-bus screenshot from every
performance window plus actual/oracle/difference panels for every gated
rendering-parity capture. Performance screenshots are taken after profiling
stops, so collecting them does not affect the timed window. A failure during
setup or execution still produces a report with the failure recorded.

To override discovery or add a convenience copy of the JSON:

```sh
.venv/bin/python tools/vs2_hardware_test.py \
    --port /dev/cu.usbmodemWORKBENCH \
    --json-out /tmp/vs2-hardware-results.json
```

Use `--report-root` to change the report parent and `--report-name` to change
the human-readable suffix in the timestamped directory name.

Useful diagnostic reductions are `--skip-render`, `--skip-performance`,
`--repeats 1`, and `--rpms 600`. They are not substitutes for the default
acceptance run.

## USB workbench control framing

Ordinary bytes on the workbench USB endpoint continue to bridge transparently
to the rotor UART. `0xD3` cannot be emitted by the seven-bit joystick protocol,
so it starts a workbench-local ASCII command terminated by newline:

| Host command | Workbench response |
|---|---|
| `0xD3 rpm <n>\n` | `wb_ok rpm=<clamped-n>\n` |
| `0xD3 capture\n` | `wb_frame 55296 <crc32>\n` followed by 55,296 raw `[GB, B, G, R]` bytes |

The capture is a locked snapshot shared with UDP telemetry. Workbench logging
and DUT forwarding are paused from the binary header through the payload, and
the host validates the CRC before using any pixels.

## Regression coverage

The ordinary host suite checks the fixture budgets, ordered label/sprite
composition, USB framing and CRC parser, circular-alignment comparator,
performance gates, heap/timing report fields, native hardware-oracle entry
points, timestamped artifact directories, screenshot rendering, and HTML/JSON
report generation:

```sh
.venv/bin/python tests/run_tests.py
```

The host suite catches protocol and algorithm regressions without boards. The
default hardware command remains the release gate for timing and electrical
rendering behavior.
