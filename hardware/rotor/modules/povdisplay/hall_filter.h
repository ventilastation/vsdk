#pragma once

#include <stdbool.h>
#include <stdint.h>

// Hall-pulse filter shared by the MicroPython POV renderer (povdisplay.c) and
// the native retro-go POV driver (ventilastation_pov.c), so both binaries
// track rotation speed the same way and get the same protection against a
// noisy or intermittent hall sensor. See hall_filter.c for the model.
//
// This file is intentionally free of ESP-IDF/FreeRTOS dependencies so it
// builds host-side with a plain C compiler (see tests/native/test_hall_filter.c)
// -- the same portability convention as gpu.c and color_pipeline.c in this
// directory. It is also not ISR-safe by itself: hall_filter_submit() does
// 64-bit division, which callers must not perform directly inside a GPIO ISR
// (see the caller-side notes in povdisplay.c / ventilastation_pov.c).
typedef struct {
    int64_t last_turn_us;   // timestamp of the last ACCEPTED edge
    int64_t period_us;      // estimate of one revolution (most recent trustworthy sample, unsmoothed)
    int64_t jitter_us;      // running mean absolute deviation of accepted residuals
    bool initialized;
    uint32_t disagreement_streak;  // consecutive edges that did NOT cleanly fit period_us

    uint32_t accepted_count;
    uint32_t spurious_count;       // rejected: arrived too soon to be a new revolution
    uint32_t missed_count;         // accepted edges that implied >=1 skipped edge
    uint32_t missed_pulses_total;  // sum of skipped-edge counts across all missed_count events
    uint32_t outlier_count;        // accepted (to avoid permanent phase drift), but didn't fit the model
    uint32_t stall_count;          // gap implausibly large -- treated as a stop/restart, filter reseeded
    uint32_t resync_count;         // sustained disagreement (e.g. spin-up from a stale seed) forced a resync
} hall_filter_t;

void hall_filter_init(hall_filter_t* f, int64_t initial_period_us);

// Classify one raw hall-edge timestamp and, if accepted, update last_turn_us/
// period_us/jitter_us. Returns true if the edge was accepted (including the
// outlier/stall cases, which accept the position but not the timing sample),
// false if it was rejected as spurious (state left untouched).
bool hall_filter_submit(hall_filter_t* f, int64_t this_turn_us);
