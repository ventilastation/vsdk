#pragma once

#include <stdint.h>

// Brings up the LED-bus SPI slave (see docs/internals/workbench.md "LED bus capture (no
// chip-select)") and starts two background tasks, both pinned to core 1 (see
// led_capture.c for why): capture_task (SPI-slave servicing only) and
// decode_task (column bookkeeping + reassembly of captured bursts into a
// 256 x 54 x 4 (WB_FRAME_BYTES) APA102 frame buffer), handed off via a queue.
//
// Columns are assigned from hall_sim_current_column() at the moment each
// burst is captured, not by counting bursts: real POV firmware may only
// send a burst when a colour actually changes (Ventilagon does this
// heavily, sometimes just 9-10 bursts/revolution), relying on the LEDs to
// keep glowing their last colour as the rotor sweeps them onward. decode_task
// reproduces that by holding each burst's colour forward through the
// columns it skips, until a later burst supersedes it.
void led_capture_begin(void);

// Copies the current frame buffer (WB_FRAME_BYTES bytes, [GB,B,G,R] per LED,
// column-major) into out. Every per-LED frame is copied verbatim from the
// captured APA102 bus; only the documented arm/column placement is applied.
// Safe to call from another task; internally reads from a double-buffered pair
// so it never contends with decode_task.
void led_capture_snapshot(uint8_t *out);
