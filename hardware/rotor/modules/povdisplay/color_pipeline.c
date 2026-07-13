#include "color_pipeline.h"

#include <math.h>
#include <string.h>

#define COLOR_PROFILE_VERSION 1
#define COLOR_PROFILE_HEADER_BYTES 12
#define COLOR_PROFILE_CONTROLS_BYTES 15
#define COLOR_PROFILE_MATRIX_BYTES 18
#define COLOR_PROFILE_LED_TRIMS_BYTES (COLOR_PIPELINE_LEDS * 2)
#define COLOR_PROFILE_GLOBAL_BYTES (32 * 2)
#define COLOR_PROFILE_PWM_KNOTS 17
#define COLOR_PROFILE_PWM_BYTES (3 * COLOR_PROFILE_PWM_KNOTS * 2)
#define COLOR_Q15_ONE 32767U
// APA102 global brightness is a low-frequency PWM. Keep the RGB channels at
// useful code values before introducing that additional modulation source.
#define COLOR_RGB_PREFERRED_MIN_PWM 32

typedef struct {
    uint16_t source_lut[256];
    uint16_t radial_lut[COLOR_PIPELINE_LEDS];
    uint16_t led_trims[COLOR_PIPELINE_LEDS];
    uint16_t white_balance[3];
    uint16_t master_milli;
    uint16_t global_response[32];
    uint16_t pwm_response[3][COLOR_PROFILE_PWM_KNOTS];
    uint8_t gb_floor;
    uint8_t gb_ceiling;
} color_pipeline_state_t;

static color_pipeline_state_t states[2];
static volatile uint8_t active_index;
static volatile bool active;
static volatile bool enabled = true;
static volatile uint8_t test_pattern;
static volatile uint8_t test_level = 255;

static uint16_t read_u16(const uint8_t *data) {
    return (uint16_t)data[0] | ((uint16_t)data[1] << 8);
}

static void write_u16(uint8_t *data, uint16_t value) {
    data[0] = value & 0xff;
    data[1] = value >> 8;
}

static void write_u32(uint8_t *data, uint32_t value) {
    for (int i = 0; i < 4; i++) {
        data[i] = (value >> (8 * i)) & 0xff;
    }
}

static uint16_t evenly_spaced_q15(int index, int count) {
    return (uint16_t)((2 * index * COLOR_Q15_ONE + (count - 1)) / (2 * (count - 1)));
}

static bool monotonic_q15(const uint16_t *values, size_t count) {
    uint16_t previous = 0;
    for (size_t i = 0; i < count; i++) {
        if (values[i] > COLOR_Q15_ONE || (i && values[i] < previous)) {
            return false;
        }
        previous = values[i];
    }
    return true;
}

static uint16_t srgb_decode(uint8_t value) {
    float encoded = value / 255.0f;
    float linear = encoded <= 0.04045f
        ? encoded / 12.92f
        : powf((encoded + 0.055f) / 1.055f, 2.4f);
    if (linear <= 0.0f) return 0;
    if (linear >= 1.0f) return COLOR_Q15_ONE;
    return (uint16_t)(linear * COLOR_Q15_ONE + 0.5f);
}

static uint16_t power_decode(uint8_t value, uint16_t gamma_milli) {
    float encoded = value / 255.0f;
    float linear = powf(encoded, gamma_milli / 1000.0f);
    if (linear <= 0.0f) return 0;
    if (linear >= 1.0f) return COLOR_Q15_ONE;
    return (uint16_t)(linear * COLOR_Q15_ONE + 0.5f);
}

static uint16_t invert_pwm(const uint16_t *curve, uint16_t target) {
    if (target == 0 || curve[COLOR_PROFILE_PWM_KNOTS - 1] == 0) {
        return 0;
    }
    if (target >= curve[COLOR_PROFILE_PWM_KNOTS - 1]) {
        return 255;
    }
    for (int index = 0; index < COLOR_PROFILE_PWM_KNOTS - 1; index++) {
        uint16_t low = curve[index];
        uint16_t high = curve[index + 1];
        if (target <= high) {
            uint32_t fraction = high == low ? 0 : (uint32_t)(target - low) * 255 / (high - low);
            return (uint16_t)((index * 255 + fraction + 8) / 16);
        }
    }
    return 255;
}

static uint16_t desired_light(const color_pipeline_state_t *state, uint8_t led, uint8_t channel, uint8_t source) {
    uint64_t value = state->source_lut[source];
    value *= state->master_milli;
    value *= state->white_balance[channel];
    value *= state->led_trims[led];
    value *= state->radial_lut[led];
    value /= 1000ULL * 1000ULL * 1024ULL * COLOR_Q15_ONE;
    return value > COLOR_Q15_ONE ? COLOR_Q15_ONE : (uint16_t)value;
}

bool color_pipeline_build_default(uint8_t *profile, size_t length, uint32_t generation) {
    if (profile == NULL || length != COLOR_PIPELINE_PROFILE_BYTES) {
        return false;
    }
    memset(profile, 0, length);
    memcpy(profile, "PCAL", 4);
    profile[4] = COLOR_PROFILE_VERSION;
    write_u16(profile + 6, COLOR_PIPELINE_PROFILE_BYTES);
    write_u32(profile + 8, generation);

    size_t offset = COLOR_PROFILE_HEADER_BYTES;
    profile[offset++] = 0; // sRGB
    write_u16(profile + offset, 2200); offset += 2;
    write_u16(profile + offset, 1000); offset += 2;
    for (int channel = 0; channel < 3; channel++) {
        write_u16(profile + offset, 1000);
        offset += 2;
    }
    write_u16(profile + offset, 1000); offset += 2;
    profile[offset++] = 1;
    profile[offset++] = 31;
    for (int row = 0; row < 3; row++) {
        for (int column = 0; column < 3; column++) {
            write_u16(profile + offset, row == column ? 4096 : 0);
            offset += 2;
        }
    }
    for (int led = 0; led < COLOR_PIPELINE_LEDS; led++) {
        write_u16(profile + offset, 1024);
        offset += 2;
    }
    for (int level = 0; level < 32; level++) {
        write_u16(profile + offset, evenly_spaced_q15(level, 32));
        offset += 2;
    }
    for (int channel = 0; channel < 3; channel++) {
        for (int knot = 0; knot < COLOR_PROFILE_PWM_KNOTS; knot++) {
            write_u16(profile + offset, evenly_spaced_q15(knot, COLOR_PROFILE_PWM_KNOTS));
            offset += 2;
        }
    }
    return offset == length;
}

bool color_pipeline_apply(const uint8_t *profile, size_t length) {
    if (profile == NULL || length != COLOR_PIPELINE_PROFILE_BYTES
        || memcmp(profile, "PCAL", 4) != 0
        || profile[4] != COLOR_PROFILE_VERSION || profile[5] != 0
        || read_u16(profile + 6) != COLOR_PIPELINE_PROFILE_BYTES) {
        return false;
    }

    size_t offset = COLOR_PROFILE_HEADER_BYTES;
    uint8_t source_eotf = profile[offset++];
    uint16_t source_gamma_milli = read_u16(profile + offset); offset += 2;
    uint16_t master_milli = read_u16(profile + offset); offset += 2;
    uint16_t white_balance[3];
    for (int channel = 0; channel < 3; channel++) {
        white_balance[channel] = read_u16(profile + offset);
        offset += 2;
    }
    uint16_t radial_exponent_milli = read_u16(profile + offset); offset += 2;
    uint8_t gb_floor = profile[offset++];
    uint8_t gb_ceiling = profile[offset++];
    // The current encoder uses white balance. The matrix is retained in the
    // canonical payload for the emulator's LED-to-preview conversion.
    offset += COLOR_PROFILE_MATRIX_BYTES;

    if (source_eotf > 1 || source_gamma_milli < 1000 || source_gamma_milli > 4000
        || master_milli > 4000 || radial_exponent_milli > 4000
        || gb_floor > gb_ceiling || gb_ceiling > 31
        || offset + COLOR_PROFILE_LED_TRIMS_BYTES + COLOR_PROFILE_GLOBAL_BYTES + COLOR_PROFILE_PWM_BYTES != length) {
        return false;
    }

    uint8_t inactive_index = 1 - __atomic_load_n(&active_index, __ATOMIC_ACQUIRE);
    color_pipeline_state_t *state = &states[inactive_index];
    memset(state, 0, sizeof(*state));
    state->master_milli = master_milli;
    state->gb_floor = gb_floor;
    state->gb_ceiling = gb_ceiling;
    memcpy(state->white_balance, white_balance, sizeof(white_balance));

    for (int led = 0; led < COLOR_PIPELINE_LEDS; led++) {
        state->led_trims[led] = read_u16(profile + offset);
        if (state->led_trims[led] > 4096) return false;
        offset += 2;
        float radius = (float)(led + 1) / COLOR_PIPELINE_LEDS;
        float radial = powf(radius, radial_exponent_milli / 1000.0f);
        state->radial_lut[led] = (uint16_t)(radial * COLOR_Q15_ONE + 0.5f);
    }
    for (int level = 0; level < 32; level++) {
        state->global_response[level] = read_u16(profile + offset);
        offset += 2;
    }
    if (!monotonic_q15(state->global_response, 32)) return false;
    for (int channel = 0; channel < 3; channel++) {
        for (int knot = 0; knot < COLOR_PROFILE_PWM_KNOTS; knot++) {
            state->pwm_response[channel][knot] = read_u16(profile + offset);
            offset += 2;
        }
        if (!monotonic_q15(state->pwm_response[channel], COLOR_PROFILE_PWM_KNOTS)) return false;
    }
    if (offset != length) return false;

    for (int value = 0; value < 256; value++) {
        state->source_lut[value] = source_eotf == 0
            ? srgb_decode(value)
            : power_decode(value, source_gamma_milli);
    }

    __atomic_store_n(&active_index, inactive_index, __ATOMIC_RELEASE);
    __atomic_store_n(&active, true, __ATOMIC_RELEASE);
    __atomic_store_n(&enabled, true, __ATOMIC_RELEASE);
    return true;
}

bool color_pipeline_set_enabled(bool value) {
    if (value && !__atomic_load_n(&active, __ATOMIC_ACQUIRE)) {
        return false;
    }
    __atomic_store_n(&enabled, value, __ATOMIC_RELEASE);
    return true;
}

bool color_pipeline_is_enabled(void) {
    return __atomic_load_n(&enabled, __ATOMIC_ACQUIRE);
}

bool color_pipeline_is_active(void) {
    return __atomic_load_n(&active, __ATOMIC_ACQUIRE)
        && __atomic_load_n(&enabled, __ATOMIC_ACQUIRE);
}

bool color_pipeline_set_test_pattern(uint8_t pattern, uint8_t level) {
    if (pattern > COLOR_TEST_RADIAL) {
        return false;
    }
    __atomic_store_n(&test_level, level, __ATOMIC_RELEASE);
    __atomic_store_n(&test_pattern, pattern, __ATOMIC_RELEASE);
    return true;
}

static void apply_test_pattern(uint8_t led, uint8_t *red, uint8_t *green, uint8_t *blue) {
    uint8_t pattern = __atomic_load_n(&test_pattern, __ATOMIC_ACQUIRE);
    uint8_t level = __atomic_load_n(&test_level, __ATOMIC_ACQUIRE);
    switch (pattern) {
        case COLOR_TEST_GRAY:
        case COLOR_TEST_WHITE:
            *red = level;
            *green = level;
            *blue = level;
            break;
        case COLOR_TEST_RED:
            *red = level;
            *green = 0;
            *blue = 0;
            break;
        case COLOR_TEST_GREEN:
            *red = 0;
            *green = level;
            *blue = 0;
            break;
        case COLOR_TEST_BLUE:
            *red = 0;
            *green = 0;
            *blue = level;
            break;
        case COLOR_TEST_RADIAL:
            level = (uint16_t)level * led / (COLOR_PIPELINE_LEDS - 1);
            *red = level;
            *green = level;
            *blue = level;
            break;
        default:
            break;
    }
}

uint32_t color_pipeline_encode_rgb(uint8_t led, uint8_t red, uint8_t green, uint8_t blue) {
    if (led >= COLOR_PIPELINE_LEDS || !color_pipeline_is_active()) {
        return 0;
    }
    apply_test_pattern(led, &red, &green, &blue);
    const color_pipeline_state_t *state = &states[__atomic_load_n(&active_index, __ATOMIC_ACQUIRE)];
    uint8_t source[3] = { red, green, blue };
    uint16_t target[3];
    uint16_t maximum = 0;
    uint8_t peak_channel = 0;
    for (int channel = 0; channel < 3; channel++) {
        target[channel] = desired_light(state, led, channel, source[channel]);
        if (target[channel] > maximum) maximum = target[channel];
        if (target[channel] >= target[peak_channel]) peak_channel = channel;
    }
    if (maximum == 0) return 0x000000e0;

    // Start at the highest global-brightness setting. This leaves normal
    // dimming to the 8-bit RGB PWM channels instead of the APA102's ~582 Hz
    // global PWM. Only lower GB when the brightest channel would otherwise
    // have too few RGB code values to represent a dark tone smoothly.
    uint8_t brightness = state->gb_ceiling;
    for (int level = state->gb_ceiling; level >= state->gb_floor; level--) {
        uint16_t global = state->global_response[level];
        if (global == 0 || global < maximum) {
            continue;
        }
        brightness = level; // lowest usable fallback if all RGB values are small
        uint32_t normalized = ((uint32_t)maximum * COLOR_Q15_ONE + global / 2) / global;
        if (normalized > COLOR_Q15_ONE) normalized = COLOR_Q15_ONE;
        if (invert_pwm(state->pwm_response[peak_channel], normalized)
                >= COLOR_RGB_PREFERRED_MIN_PWM) {
            brightness = level;
            break;
        }
    }
    uint16_t global = state->global_response[brightness];
    if (global == 0) return 0x000000e0;
    uint8_t pwm[3];
    for (int channel = 0; channel < 3; channel++) {
        uint32_t normalized = ((uint32_t)target[channel] * COLOR_Q15_ONE + global / 2) / global;
        if (normalized > COLOR_Q15_ONE) normalized = COLOR_Q15_ONE;
        pwm[channel] = invert_pwm(state->pwm_response[channel], normalized);
    }
    return (uint32_t)(0xe0 | brightness)
        | ((uint32_t)pwm[2] << 8)
        | ((uint32_t)pwm[1] << 16)
        | ((uint32_t)pwm[0] << 24);
}
