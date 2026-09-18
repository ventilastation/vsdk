#pragma once

#include <stdbool.h>
#include <stdint.h>

// Raw diagnostic LED override for power/current characterization: bypasses
// the scene renderer and color_pipeline's calibration LUT entirely, so the
// APA102 bytes on the wire are exactly what was requested. Used by the
// "LED Usage" system app (system/led_usage) to hold a static count/colour/
// brightness pattern still while someone measures current draw.
//
// The rotor is one continuous 107-LED strip through a shared centre LED,
// not two independent arms -- see the comment at povdisplay.c's
// dma_pixels0/dma_pixels1 setup. `count` LEDs are lit growing outward from
// that centre toward both ends.
#define LED_USAGE_TOTAL_LEDS 107
#define LED_USAGE_LEDS_PER_HALF 54

bool led_usage_set(bool active, uint8_t count, uint8_t red, uint8_t green,
                    uint8_t blue, uint8_t global_brightness);
bool led_usage_is_active(void);

// `second_half`: which of render()'s two roles this call is filling (see
// povdisplay.c/gpu.c for how one render() sweep is used both directly and
// reversed to cover the two halves of the physical strip). `led`: 0 = the
// shared centre LED .. LED_USAGE_LEDS_PER_HALF-1 = that half's own extreme
// end. Returns the raw little-endian APA102 word ([GB, B, G, R] bytes,
// memory order) for that LED, or the "off" word if it isn't lit.
uint32_t led_usage_encode(bool second_half, uint8_t led);
