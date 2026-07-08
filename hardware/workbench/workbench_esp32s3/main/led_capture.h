#pragma once

#include <stdint.h>

// Brings up the LED-bus SPI slave (see WORKBENCH.md "LED bus capture (no
// chip-select)") and starts a background task that continuously decodes
// captured bursts into a 256 x 54 x 3 (WB_FRAME_BYTES) RGB frame buffer.
void led_capture_begin(void);

// Copies the current frame buffer (WB_FRAME_BYTES bytes, R,G,B per LED,
// column-major) into out. Safe to call from another task; internally reads
// from a double-buffered pair so it never contends with the capture task.
void led_capture_snapshot(uint8_t *out);
