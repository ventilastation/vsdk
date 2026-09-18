/* Host tests for the LED Usage diagnostic override (led_usage.c). Checks
 * the count-split math directly, without any ESP-IDF/MicroPython headers --
 * led_usage.c only needs stdbool/stdint. */
#include <stdio.h>

#include "led_usage.h"

static int failures = 0;

#define CHECK(condition, message) \
    do { \
        if (!(condition)) { \
            printf("FAIL %s\n", message); \
            failures++; \
        } \
    } while (0)

static int is_lit(uint32_t word) {
    return word != 0x000000e0 && word != 0;
}

/* Count how many of the LED_USAGE_LEDS_PER_HALF positions are lit on one
 * half, given led==0 is the shared centre (only counted once by the caller,
 * not per-half) and led==1..53 is that half's own outward run. */
static int lit_count_excluding_centre(int second_half) {
    int count = 0;
    for (int led = 1; led < LED_USAGE_LEDS_PER_HALF; led++) {
        if (is_lit(led_usage_encode(second_half, led))) {
            count++;
        }
    }
    return count;
}

int main(void) {
    CHECK(!led_usage_is_active(), "inactive before any set() call");

    CHECK(led_usage_set(true, 0, 10, 20, 30, 5), "activate with count 0");
    CHECK(led_usage_is_active(), "active after set(active=true)");
    CHECK(!is_lit(led_usage_encode(false, 0)), "count 0: centre is off");
    CHECK(!is_lit(led_usage_encode(true, 0)), "count 0: centre is off (other half)");
    CHECK(lit_count_excluding_centre(false) == 0, "count 0: first half has nothing else lit");
    CHECK(lit_count_excluding_centre(true) == 0, "count 0: second half has nothing else lit");

    CHECK(led_usage_set(true, 1, 10, 20, 30, 5), "count 1");
    CHECK(is_lit(led_usage_encode(false, 0)), "count 1: centre is lit");
    CHECK(is_lit(led_usage_encode(true, 0)), "count 1: centre is lit (other half)");
    CHECK(led_usage_encode(false, 0) == led_usage_encode(true, 0),
          "the shared centre LED must agree between halves");
    CHECK(lit_count_excluding_centre(false) == 0, "count 1: nothing beyond the centre, first half");
    CHECK(lit_count_excluding_centre(true) == 0, "count 1: nothing beyond the centre, second half");

    /* count=107 (LED_USAGE_TOTAL_LEDS) -- every LED on the strip lit. */
    CHECK(led_usage_set(true, LED_USAGE_TOTAL_LEDS, 1, 2, 3, 4), "count = every LED");
    CHECK(lit_count_excluding_centre(false) == LED_USAGE_LEDS_PER_HALF - 1,
          "count 107: first half fully lit");
    CHECK(lit_count_excluding_centre(true) == LED_USAGE_LEDS_PER_HALF - 1,
          "count 107: second half fully lit");

    /* An odd `count` splits as evenly as possible between the two halves,
     * plus the shared centre -- 1 (centre) + 53 + 53 == 107. */
    CHECK(led_usage_set(true, 11, 1, 2, 3, 4), "count 11 (1 centre + 5 + 5)");
    CHECK(lit_count_excluding_centre(false) + lit_count_excluding_centre(true) == 10,
          "count 11: 10 LEDs lit beyond the centre, split across both halves");

    CHECK(!led_usage_set(true, LED_USAGE_TOTAL_LEDS + 1, 0, 0, 0, 0),
          "reject a count beyond the physical LED total");
    CHECK(!led_usage_set(true, 0, 0, 0, 0, 32), "reject a global brightness beyond 5 bits");

    CHECK(led_usage_set(true, 107, 200, 150, 50, 17), "set a known colour/brightness");
    uint32_t word = led_usage_encode(false, 5);
    CHECK(is_lit(word), "count 107: LED 5 of the first half is lit");
    CHECK((word & 0xff) == (0xe0 | 17), "GB byte carries the global brightness");
    CHECK((word >> 24 & 0xff) == 200, "byte carries red");
    CHECK((word >> 16 & 0xff) == 150, "byte carries green");
    CHECK((word >> 8 & 0xff) == 50, "byte carries blue");

    CHECK(led_usage_set(false, 0, 0, 0, 0, 0), "deactivate");
    CHECK(!led_usage_is_active(), "inactive after set(active=false)");

    if (failures) {
        return 1;
    }
    printf("led usage host tests passed\n");
    return 0;
}
