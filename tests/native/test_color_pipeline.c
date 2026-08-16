#include <stdint.h>
#include <stdio.h>
#include <string.h>

#include "color_pipeline.h"

#define Q15_ONE 32767
#define HEADER_BYTES 12
#define CONTROLS_BYTES 21
#define MATRIX_BYTES 18
#define PWM_KNOTS 17
// Dark white balance sits just past white balance in the controls block.
#define DARK_WHITE_OFFSET (HEADER_BYTES + 1 + 2 + 2 + 6)

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
    profile[4] = 2;
    put_u16(profile + 6, COLOR_PIPELINE_PROFILE_BYTES);

    size_t offset = HEADER_BYTES;
    profile[offset++] = 0;       // sRGB
    put_u16(profile + offset, 2200); offset += 2;
    put_u16(profile + offset, 1000); offset += 2;
    put_u16(profile + offset, 1000); offset += 2;
    put_u16(profile + offset, 1000); offset += 2;
    put_u16(profile + offset, 1000); offset += 2;
    // Dark white balance, neutral.
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

    uint8_t generated[COLOR_PIPELINE_PROFILE_BYTES];
    CHECK(color_pipeline_build_default(generated, sizeof(generated), 0), "build default profile");
    CHECK(memcmp(profile, generated, sizeof(profile)) == 0, "C and fixture defaults match");

    CHECK(color_pipeline_apply(profile, sizeof(profile)), "accept canonical default profile");
    CHECK(color_pipeline_is_active(), "pipeline becomes active");
    CHECK(color_pipeline_set_enabled(false), "temporarily select legacy encoder");
    CHECK(!color_pipeline_is_active(), "disabled pipeline takes the legacy path");
    CHECK(color_pipeline_set_enabled(true), "restore calibrated encoder");
    CHECK(color_pipeline_is_active(), "calibrated pipeline can be restored");
    CHECK(color_pipeline_encode_rgb(53, 255, 255, 255) == 0xffffffff,
          "outer full white uses APA102 full-scale frame");
    CHECK(color_pipeline_encode_rgb(53, 0, 0, 0) == 0x000000e0,
          "black turns all PWM and global brightness off");

    uint32_t outer_mid_red = color_pipeline_encode_rgb(53, 128, 0, 0);
    CHECK((outer_mid_red & 0x1f) == 31 && (outer_mid_red >> 24) >= 32,
          "ordinary dimming keeps APA102 global brightness high and uses RGB PWM");

    uint32_t outer_dark_red = color_pipeline_encode_rgb(53, 64, 0, 0);
    CHECK((outer_dark_red & 0x1f) < 31 && (outer_dark_red >> 24) >= 32,
          "very dark tones lower global brightness only after preserving RGB resolution");

    uint32_t inner_red = color_pipeline_encode_rgb(0, 255, 0, 0);
    CHECK((inner_red & 0x1f) < 31 && (inner_red >> 24) >= 32,
          "inner LED uses global brightness for a dark radial target");
    CHECK((inner_red >> 24) > 0 && ((inner_red >> 16) & 0xff) == 0
          && ((inner_red >> 8) & 0xff) == 0, "red channel remains isolated");

    CHECK(color_pipeline_set_test_pattern(COLOR_TEST_BLUE, 255), "enable blue test pattern");
    uint32_t test_blue = color_pipeline_encode_rgb(53, 255, 0, 0);
    CHECK((test_blue & 0x1f) == 31 && ((test_blue >> 8) & 0xff) == 255
          && ((test_blue >> 16) & 0xff) == 0 && (test_blue >> 24) == 0,
          "test pattern overrides game RGB inside encoder");
    CHECK(color_pipeline_set_test_pattern(COLOR_TEST_OFF, 255), "disable test pattern");

    // Dark white balance. A trimmed channel must lose PWM only where the
    // global-brightness stage is doing the dimming; tones that render at the
    // ceiling are already handled by the ordinary white balance.
    uint8_t tinted[COLOR_PIPELINE_PROFILE_BYTES];
    memcpy(tinted, profile, sizeof(tinted));
    put_u16(tinted + DARK_WHITE_OFFSET + 2, 960);  // green
    CHECK(color_pipeline_apply(tinted, sizeof(tinted)), "accept a dark white balance");

    uint32_t bright_grey = color_pipeline_encode_rgb(53, 200, 200, 200);
    CHECK((bright_grey & 0x1f) == 31
          && ((bright_grey >> 16) & 0xff) == (bright_grey >> 24),
          "dark white balance leaves ceiling-brightness greys neutral");

    uint32_t dark_grey = color_pipeline_encode_rgb(53, 24, 24, 24);
    CHECK((dark_grey & 0x1f) < 31
          && ((dark_grey >> 16) & 0xff) < (dark_grey >> 24)
          && ((dark_grey >> 8) & 0xff) == (dark_grey >> 24),
          "dark white balance trims only green once global brightness engages");

    memcpy(tinted, profile, sizeof(tinted));
    put_u16(tinted + DARK_WHITE_OFFSET + 2, 100);
    CHECK(!color_pipeline_apply(tinted, sizeof(tinted)),
          "reject a dark white balance below its supported range");

    CHECK(color_pipeline_apply(profile, sizeof(profile)), "restore the neutral profile");

    // A board provisioned before the dark white balance keeps its calibration.
    uint8_t v1[COLOR_PIPELINE_PROFILE_V1_BYTES];
    memcpy(v1, profile, DARK_WHITE_OFFSET);
    memcpy(v1 + DARK_WHITE_OFFSET, profile + DARK_WHITE_OFFSET + 6,
           COLOR_PIPELINE_PROFILE_V1_BYTES - DARK_WHITE_OFFSET);
    v1[4] = 1;
    put_u16(v1 + 6, COLOR_PIPELINE_PROFILE_V1_BYTES);

    uint8_t upgraded[COLOR_PIPELINE_PROFILE_BYTES];
    CHECK(color_pipeline_upgrade_v1(v1, sizeof(v1), upgraded, sizeof(upgraded)),
          "upgrade a v1 profile");
    CHECK(memcmp(upgraded, profile, sizeof(profile)) == 0,
          "upgraded v1 profile matches the v2 default");
    CHECK(!color_pipeline_upgrade_v1(profile, sizeof(profile), upgraded, sizeof(upgraded)),
          "reject a v2 payload offered as v1 input");

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
