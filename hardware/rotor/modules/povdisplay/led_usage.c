#include "led_usage.h"

// Single writer (the MicroPython binding, povdisplay_set_led_usage), single
// reader (the render task's render() call) -- atomics are enough, no lock
// needed, matching color_pipeline.c's test_pattern/test_level globals.
static bool g_active = false;
static uint8_t g_count = 0;
static uint8_t g_red = 0;
static uint8_t g_green = 0;
static uint8_t g_blue = 0;
static uint8_t g_global = 0;

bool led_usage_set(bool active, uint8_t count, uint8_t red, uint8_t green,
                    uint8_t blue, uint8_t global_brightness) {
    if (count > LED_USAGE_TOTAL_LEDS || global_brightness > 31) {
        return false;
    }
    __atomic_store_n(&g_count, count, __ATOMIC_RELEASE);
    __atomic_store_n(&g_red, red, __ATOMIC_RELEASE);
    __atomic_store_n(&g_green, green, __ATOMIC_RELEASE);
    __atomic_store_n(&g_blue, blue, __ATOMIC_RELEASE);
    __atomic_store_n(&g_global, global_brightness, __ATOMIC_RELEASE);
    __atomic_store_n(&g_active, active, __ATOMIC_RELEASE);
    return true;
}

bool led_usage_is_active(void) {
    return __atomic_load_n(&g_active, __ATOMIC_ACQUIRE);
}

uint32_t led_usage_encode(bool second_half, uint8_t led) {
    uint8_t count = __atomic_load_n(&g_count, __ATOMIC_ACQUIRE);
    if (count == 0) {
        return 0x000000e0;
    }
    // `count` LEDs lit, growing from the shared centre (led == 0) outward.
    // The centre itself is one LED; the remaining count-1 split between
    // this half's outward run (led 1..LED_USAGE_LEDS_PER_HALF-1) and the
    // other half's. An odd remainder favors the first half arbitrarily --
    // both halves already agree on led == 0 (the centre), which is all
    // that has to match between them.
    uint8_t remaining = count - 1;
    uint8_t first_half_extra = (remaining + 1) / 2;
    uint8_t second_half_extra = remaining / 2;
    uint8_t half_extra = second_half ? second_half_extra : first_half_extra;
    bool lit = (led == 0) || (led <= half_extra);
    if (!lit) {
        return 0x000000e0;
    }
    uint8_t global_brightness = __atomic_load_n(&g_global, __ATOMIC_ACQUIRE);
    uint8_t red = __atomic_load_n(&g_red, __ATOMIC_ACQUIRE);
    uint8_t green = __atomic_load_n(&g_green, __ATOMIC_ACQUIRE);
    uint8_t blue = __atomic_load_n(&g_blue, __ATOMIC_ACQUIRE);
    return (uint32_t)(0xe0 | global_brightness)
        | ((uint32_t)blue << 8)
        | ((uint32_t)green << 16)
        | ((uint32_t)red << 24);
}
