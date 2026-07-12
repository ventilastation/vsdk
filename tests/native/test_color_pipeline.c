#include <stdint.h>
#include <stdio.h>
#include <string.h>

#include "color_pipeline.h"

#define Q15_ONE 32767
#define HEADER_BYTES 12
#define CONTROLS_BYTES 15
#define MATRIX_BYTES 18
#define PWM_KNOTS 17

static int failures = 0;

#define CHECK(condition, message) \
    do { \
        if (!(condition)) { \
            printf("FAIL %s\n", message); \
            failures++; \
        } \
    } while (0)

static void put_u16(uint8_t *data, uint16_t value) {
    data[0] = value & 0xff;
    data[1] = value >> 8;
}

static uint16_t rounded_fraction(int numerator, int denominator) {
    return (uint16_t)((2 * numerator * Q15_ONE + denominator) / (2 * denominator));
}

static void build_default_profile(uint8_t profile[COLOR_PIPELINE_PROFILE_BYTES]) {
    memset(profile, 0, COLOR_PIPELINE_PROFILE_BYTES);
    memcpy(profile, "PCAL", 4);
    profile[4] = 1;
    put_u16(profile + 6, COLOR_PIPELINE_PROFILE_BYTES);

    size_t offset = HEADER_BYTES;
    profile[offset++] = 0;       // sRGB
    put_u16(profile + offset, 2200); offset += 2;
    put_u16(profile + offset, 1000); offset += 2;
    put_u16(profile + offset, 1000); offset += 2;
    put_u16(profile + offset, 1000); offset += 2;
    put_u16(profile + offset, 1000); offset += 2;
    put_u16(profile + offset, 1000); offset += 2;
    profile[offset++] = 1;
    profile[offset++] = 31;

    // Identity LED-to-preview matrix. The hardware encoder does not consume
    // it yet, but it is part of the canonical wire layout.
    for (int row = 0; row < 3; row++) {
        for (int column = 0; column < 3; column++) {
            put_u16(profile + offset, row == column ? 4096 : 0);
            offset += 2;
        }
    }
    for (int led = 0; led < COLOR_PIPELINE_LEDS; led++) {
        put_u16(profile + offset, 1024);
        offset += 2;
    }
    for (int level = 0; level < 32; level++) {
        put_u16(profile + offset, rounded_fraction(level, 31));
        offset += 2;
    }
    for (int channel = 0; channel < 3; channel++) {
        for (int knot = 0; knot < PWM_KNOTS; knot++) {
            put_u16(profile + offset, rounded_fraction(knot, PWM_KNOTS - 1));
            offset += 2;
        }
    }
    CHECK(offset == COLOR_PIPELINE_PROFILE_BYTES, "default profile length");
}

int main(void) {
    uint8_t profile[COLOR_PIPELINE_PROFILE_BYTES];
    build_default_profile(profile);

    CHECK(color_pipeline_apply(profile, sizeof(profile)), "accept canonical default profile");
    CHECK(color_pipeline_is_active(), "pipeline becomes active");
    CHECK(color_pipeline_encode_rgb(53, 255, 255, 255) == 0xffffffff,
          "outer full white uses APA102 full-scale frame");
    CHECK(color_pipeline_encode_rgb(53, 0, 0, 0) == 0x000000e0,
          "black turns all PWM and global brightness off");

    uint32_t inner_red = color_pipeline_encode_rgb(0, 255, 0, 0);
    CHECK((inner_red & 0x1f) == 1, "inner LED chooses the lowest viable global brightness");
    CHECK((inner_red >> 24) > 0 && ((inner_red >> 16) & 0xff) == 0
          && ((inner_red >> 8) & 0xff) == 0, "red channel remains isolated");

    profile[0] = 'X';
    CHECK(!color_pipeline_apply(profile, sizeof(profile)), "reject invalid profile magic");
    CHECK(color_pipeline_encode_rgb(53, 255, 255, 255) == 0xffffffff,
          "invalid profile does not disturb active state");

    if (failures) {
        return 1;
    }
    printf("color pipeline host tests passed\n");
    return 0;
}
