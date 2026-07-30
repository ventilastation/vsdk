#pragma once

#include <stdint.h>

// Owns the one full-frame staging buffer shared by UDP telemetry and the
// on-demand USB hardware-test capture. Call frame_snapshot_begin() before
// either producer starts.
void frame_snapshot_begin(void);

// Takes the snapshot lock, refreshes the staging buffer from led_capture,
// and returns it. The caller must release it after it has finished sending
// or copying the bytes.
const uint8_t *frame_snapshot_acquire(void);
void frame_snapshot_release(void);
